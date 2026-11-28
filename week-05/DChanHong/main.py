import argparse
import json
from datetime import datetime
from pathlib import Path
from time import perf_counter

from agents import MaxTurnsExceeded, RunHooks, Runner
from pydantic import BaseModel

from ipo_agent.agents.subscription import (
    assessment_agent, format_assessment, format_schedule, subscription_agent,
)
from ipo_agent.schemas import SubscriptionCandidates


MAX_TURNS = 12
LOG_DIR = Path(__file__).resolve().parent / ".cache" / "run-logs"


class RunRecord(RunHooks):
    def __init__(self):
        self.model_calls = 0
        self.events = []
        self.stop_reason = "모델이 최종 답변을 반환했습니다."

    async def on_llm_start(self, context, agent, system_prompt, input_items):
        self.model_calls += 1

    async def on_tool_start(self, context, agent, tool):
        self.events.append({"event": "tool_call", "turn": self.model_calls,
                            "call_id": context.tool_call_id, "name": tool.name,
                            "arguments": context.tool_arguments})

    async def on_tool_end(self, context, agent, tool, result):
        value = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
        self.events.append({"event": "tool_result", "turn": self.model_calls,
                            "call_id": context.tool_call_id, "name": tool.name, "result": value})



def tool_outputs(items):
    outputs = []
    for item in items:
        if item.type == "tool_call_item":
            print(f"[도구 호출] {item.raw_item.name} {item.raw_item.arguments}")
        elif item.type == "tool_call_output_item":
            outputs.append(item.output)
    return outputs


def run_request(request: str, max_turns: int = MAX_TURNS, *, record: RunRecord | None = None) -> str:
    record = record if record is not None else RunRecord()
    targets = []
    outcomes = {}
    completed = 0
    lines = []
    remaining = max_turns
    try:
        result = Runner.run_sync(subscription_agent, request, max_turns=remaining, hooks=record)
        remaining -= len(result.raw_responses)
        outputs = tool_outputs(result.new_items)
        plan = result.final_output.answer
        if isinstance(plan, str):
            return plan

        schedule = next((o for o in reversed(outputs) if isinstance(o, SubscriptionCandidates)), None)
        if plan.include_schedule:
            if schedule is None:
                record.stop_reason = "청약 일정을 확인하지 못해 분석 대상을 정할 수 없습니다."
                return f"목표 미달성 | {record.stop_reason}"
            lines.append(format_schedule(schedule))
            targets = schedule.analysis_companies
        else:
            targets = plan.companies
        targets = list(dict.fromkeys(targets))[:3]
        if not targets:
            record.stop_reason = "분석 대상 종목을 확인하지 못했습니다."
            return "\n".join([*lines, record.stop_reason])

        for company in targets:
            if remaining == 0:
                break
            prompt = f"사용자 요청\n{request}\n\n이번 분석 대상\n{company}"
            if schedule:
                candidate = next((c for c in schedule.candidates if c.company == company), None)
                if candidate:
                    prompt += f"\n조회된 청약 일정과 공시\n{candidate.model_dump_json()}"
            result = Runner.run_sync(assessment_agent, prompt, max_turns=remaining, hooks=record)
            remaining -= len(result.raw_responses)
            evidence = tool_outputs(result.new_items)
            assessment = result.final_output
            if assessment.company != company:
                outcomes[company] = f"{company} | 분석 미완료 · 응답의 종목명이 일치하지 않습니다."
                continue
            outcomes[company] = format_assessment(assessment, evidence)
            completed += 1
    except MaxTurnsExceeded as error:
        record.stop_reason = f"{max_turns}턴 한도 도달"
        if error.run_data:
            partial_outputs = tool_outputs(error.run_data.new_items)
            if not targets:
                lines.extend(format_schedule(o) for o in partial_outputs if isinstance(o, SubscriptionCandidates))

    if not targets:
        return "\n".join([f"목표 미달성 | {max_turns}턴 한도에 도달했습니다. 요청을 마치지 못했습니다.", *lines])

    record.stop_reason = "대상 종목별 판단 정책 적용을 마쳤습니다."
    if completed < len(targets):
        status = f"목표 미달성 · {len(targets)}개 중 {completed}개 완료"
        if len(outcomes) < len(targets):
            status += f" | {max_turns}턴 한도에 도달했습니다."
        record.stop_reason = status
        lines.insert(0, status)
    for company in targets:
        lines.append(outcomes.get(company, f"{company} | 반복 한도 도달로 분석 미완료"))
    return "\n".join(lines)


def run_and_record(question: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now().astimezone()
    path = LOG_DIR / f"{started_at:%Y%m%d-%H%M%S-%f}.json"
    record = RunRecord()
    start = perf_counter()
    answer = None
    try:
        answer = run_request(question, record=record)
        print(answer)
    except (Exception, KeyboardInterrupt) as error:
        record.stop_reason = f"실행 중단 ({type(error).__name__})"
        raise
    finally:
        elapsed = round(perf_counter() - start, 3)
        report = {
            "started_at": started_at.isoformat(), "request": question, "model": subscription_agent.model,
            "max_turns": MAX_TURNS, "model_calls": record.model_calls, "elapsed_seconds": elapsed,
            "events": record.events, "final_answer": answer, "stop_reason": record.stop_reason,
        }
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"모델 호출 {record.model_calls}회 | 실행 시간 {elapsed:.3f}초 | {record.stop_reason}")
        print(f"기록 파일 {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request", nargs="?", help="생략하면 실행 후 질문을 입력합니다.")
    args = parser.parse_args()
    if args.request is not None:
        if not args.request.strip():
            parser.error("질문을 입력해 주세요.")
        run_and_record(args.request.strip())
        return

    print("질문을 한 줄씩 입력하세요. 질문마다 새로 분석하며, 빈 줄을 입력하면 종료합니다.")
    while True:
        try:
            question = input("질문 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not question:
            return
        run_and_record(question)


if __name__ == "__main__":
    main()
