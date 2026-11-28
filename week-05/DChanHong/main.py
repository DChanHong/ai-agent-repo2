import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from time import perf_counter

from agents import MaxTurnsExceeded, RunHooks, Runner
from pydantic import BaseModel

from ipo_agent.agents.subscription import (
    LockupRateAnswer, assessment_agent, format_assessment, format_lockup_rate, format_schedule, subscription_agent,
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
        schedule = next((o for o in reversed(outputs) if isinstance(o, SubscriptionCandidates)), None)
        # 모델이 전체 일정을 조회한 경우에도 사용자가 명시한 최초 마감 조건을 검증합니다.
        first_closing = re.search(r"마감(?:일)?[이가]?\s*(?:가장|제일)\s*(?:빠른|이른|먼저)|"
                                  r"(?:가장|제일)\s*(?:먼저|빨리)\s*마감|최초\s*마감", request)
        rate_question = "확약" in request and ("신청률" in request or "확약률" in request or "비율" in request)
        if (first_closing or (schedule and schedule.first_closing_only)) and (
            isinstance(plan, LockupRateAnswer) or rate_question
        ):
            if not schedule or not schedule.candidates:
                record.stop_reason = "최초 마감 종목을 확인할 일정이 없습니다."
                return f"계산 보류 | {record.stop_reason}"
            # 일정 도구가 마감일, 회사명, 종목코드 순으로 정렬합니다.
            selected = schedule.candidates[0]
            if not selected.filing:
                record.stop_reason = f"{selected.company}의 공시 PDF가 미등록입니다."
                return f"계산 보류 | {record.stop_reason}"
            receipt = selected.filing.receipt_no
            if not isinstance(plan, LockupRateAnswer) or plan.receipt_no != receipt:
                record.stop_reason = f"선정한 {selected.company}의 접수번호 {receipt}와 일치하는 답변이 필요합니다."
                if remaining <= 0:
                    return f"목표 미달성 | {max_turns}턴 한도 도달. {record.stop_reason}"
                prompt = (f"{request}\n일정 조회에서 조건을 충족한 종목은 {selected.company} "
                          f"(마감일 {selected.closes_on}, 접수번호 {receipt})입니다. "
                          "이 접수번호로 공시를 조회하고 LockupRateAnswer를 반환하세요.")
                result = Runner.run_sync(subscription_agent, prompt, max_turns=remaining, hooks=record)
                outputs.extend(tool_outputs(result.new_items))
                plan = result.final_output.answer
                if not isinstance(plan, LockupRateAnswer) or plan.receipt_no != receipt:
                    return f"계산 보류 | {record.stop_reason}"
        if isinstance(plan, LockupRateAnswer):
            answer = format_lockup_rate(plan, outputs)
            record.stop_reason = answer if answer.startswith("계산 보류") else "선택한 공시 원문 수량을 검증하고 계산을 마쳤습니다."
            return answer
        if isinstance(plan, str):
            return plan

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
