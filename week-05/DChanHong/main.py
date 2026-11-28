import argparse

from agents import MaxTurnsExceeded, Runner

from ipo_agent.agents.subscription import (
    assessment_agent, format_assessment, format_schedule, subscription_agent,
)
from ipo_agent.schemas import SubscriptionCandidates


MAX_TURNS = 12


def tool_outputs(items):
    outputs = []
    for item in items:
        if item.type == "tool_call_item":
            print(f"[도구 호출] {item.raw_item.name} {item.raw_item.arguments}")
        elif item.type == "tool_call_output_item":
            outputs.append(item.output)
    return outputs


def run_request(request: str, max_turns: int = MAX_TURNS) -> str:
    targets = []
    outcomes = {}
    completed = 0
    lines = []
    remaining = max_turns
    try:
        result = Runner.run_sync(subscription_agent, request, max_turns=remaining)
        remaining -= len(result.raw_responses)
        outputs = tool_outputs(result.new_items)
        plan = result.final_output.answer
        if isinstance(plan, str):
            return plan

        schedule = next((o for o in reversed(outputs) if isinstance(o, SubscriptionCandidates)), None)
        if plan.include_schedule:
            if schedule is None:
                return "목표 미달성 | 청약 일정을 확인하지 못해 분석 대상을 정할 수 없습니다."
            lines.append(format_schedule(schedule))
            targets = schedule.analysis_companies
        else:
            targets = plan.companies
        targets = list(dict.fromkeys(targets))[:3]
        if not targets:
            return "\n".join([*lines, "분석 대상 종목을 확인하지 못했습니다."])

        for company in targets:
            if remaining == 0:
                break
            prompt = f"사용자 요청\n{request}\n\n이번 분석 대상\n{company}"
            if schedule:
                candidate = next((c for c in schedule.candidates if c.company == company), None)
                if candidate:
                    prompt += f"\n조회된 청약 일정과 공시\n{candidate.model_dump_json()}"
            result = Runner.run_sync(assessment_agent, prompt, max_turns=remaining)
            remaining -= len(result.raw_responses)
            evidence = tool_outputs(result.new_items)
            assessment = result.final_output
            if assessment.company != company:
                outcomes[company] = f"{company} | 분석 미완료 · 응답의 종목명이 일치하지 않습니다."
                continue
            outcomes[company] = format_assessment(assessment, evidence)
            completed += 1
    except MaxTurnsExceeded as error:
        if error.run_data:
            partial_outputs = tool_outputs(error.run_data.new_items)
            if not targets:
                lines.extend(format_schedule(o) for o in partial_outputs if isinstance(o, SubscriptionCandidates))

    if not targets:
        return "\n".join([f"목표 미달성 | {max_turns}턴 한도에 도달했습니다. 요청을 마치지 못했습니다.", *lines])

    if completed < len(targets):
        status = f"목표 미달성 · {len(targets)}개 중 {completed}개 완료"
        if len(outcomes) < len(targets):
            status += f" | {max_turns}턴 한도에 도달했습니다."
        lines.insert(0, status)
    for company in targets:
        lines.append(outcomes.get(company, f"{company} | 반복 한도 도달로 분석 미완료"))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request", help="에이전트에 전달할 요청입니다.")
    args = parser.parse_args()
    print(run_request(args.request))


if __name__ == "__main__":
    main()
