from agents import Agent
from pydantic import AwareDatetime

from ipo_agent.schemas import EvidenceFound, FilingEvidenceResult, Schema, SubscriptionCandidates
from ipo_agent.subscription_policy import (
    EqualAssessment, FilingEvidence, ProportionalTerms, apply_subscription_policy,
)
from ipo_agent.tools.filing_evidence import read_filing_evidence
from ipo_agent.tools.recent_ipo_performance import KST, get_recent_ipo_performance
from ipo_agent.tools.subscription_candidates import find_subscription_candidates


class CompanyAssessment(Schema):
    company: str
    as_of: AwareDatetime
    equal: EqualAssessment
    terms: ProportionalTerms | None
    terms_evidence: list[FilingEvidence]


class AssessmentPlan(Schema):
    include_schedule: bool
    companies: list[str]


class AgentAnswer(Schema):
    answer: str | AssessmentPlan


subscription_agent = Agent(
    name="공모주 청약 판단 에이전트",
    model="gpt-6-luna",
    instructions=(
        "기간별 청약 일정과 후보는 find_subscription_candidates로 조회합니다. "
        "일정만 요청하면 전체 일정과 상세 분석 대상만 제시하고 종료합니다. "
        "공시가 없는 종목은 PDF 미확보로 표시합니다. "
        "직전 공모주 시장 흐름은 get_recent_ipo_performance에 기준 일시를 전달합니다. "
        "한국 시간 기준 당일 장중에 당일 종가를 사용하지 않습니다. "
        "반환된 두 등락률을 구분해 제시하고, issues에 나온 확인 불가 사유를 명시합니다. "
        "공시 근거 확인을 요청받으면 접수번호와 확인할 항목을 "
        "read_filing_evidence에 전달합니다. "
        "확인한 수치와 단위, PDF 쪽 번호, DART 링크를 한국어로 제시합니다. "
        "수치를 인용할 때는 그 수치가 적힌 evidence 항목의 page를 PDF 쪽 번호로 사용합니다. "
        "표 제목과 합계가 서로 다른 쪽에 있으면 각각의 쪽 번호를 구분합니다. "
        "계산한 값은 원문 수치와 계산식을 함께 제시합니다. "
        "근거가 부족하면 빠진 항목을 구체화해 한 번 더 조회합니다. "
        "기준 시점이 있는 사실 조회는 당시 공개된 자료에서 확인한 조건과 확인하지 못한 조건을 구분합니다. "
        "청약 마감 전의 실제 배정 주수를 묻는 경우 확정 공모가 등 확인한 사실을 제시하고, "
        "실제 배정 결과가 그 시점에 확정되지 않은 이유를 설명합니다. "
        "단순 사실 조회는 배정이나 비례라는 단어가 있어도 answer에 일반 문자열로 답합니다. "
        "참여 여부, 균등·비례, 청약 추천 요청에는 AssessmentPlan을 반환합니다. "
        "기간 전체 요청은 먼저 일정을 조회하고 include_schedule=true로 설정합니다. "
        "특정 종목 요청은 include_schedule=false로 설정하고 사용자가 지정한 종목명을 적습니다. "
        "개별 종목의 근거 조사와 판단은 계획 반환 후 실행합니다."
    ),
    tools=[find_subscription_candidates, read_filing_evidence, get_recent_ipo_performance],
    output_type=AgentAnswer,
)


# 같은 모델과 도구를 사용하되 이번 실행에서 끝낼 종목 하나를 지정합니다.
assessment_agent = subscription_agent.clone(
    output_type=CompanyAssessment,
    instructions=(
        "지정된 한 종목만 분석하고 company에 지정된 회사명을 그대로 반환합니다. "
        "제공된 일정과 공시 접수번호를 사용합니다. 필요한 정보는 등록된 도구로 조회합니다. "
        "시장 흐름은 분석 기준 시점까지의 직전 공모주 자료만 사용합니다. "
        "기관 수요, 기존 주주 유통 물량, 청약 비용은 각각 해당 항목에 맞는 공시 검색어를 사용합니다. "
        "부족한 항목만 한 번 더 조회한 다음 해당 단계를 마칩니다. "
        "분석 기준 시점(as_of)을 명시합니다. 과거 청약에 시각 지정이 없으면 각 청약 마감일 00:00 한국 시간을 사용합니다. "
        "기준 시점 이후 공개된 배정 결과나 상장 시세를 청약 판단에 사용하지 않습니다. "
        "기관 제시가격 분포와 확약 신청, 확정 공모가, 기존 주주의 유통 물량과 취득가, "
        "최소 수량과 수수료를 근거로 균등 참여 여부를 먼저 판단합니다. 가격이나 기존 주주 물량만으로 "
        "패스 근거가 충분하면 청약 안 함입니다. 확인이 부족하면 판단 보류로 남기고 다음 종목을 진행합니다. "
        "equal.reason에는 판단을 가른 수치와 이유를 쓰고, evidence에는 도구가 반환한 접수번호, PDF page, "
        "원문에서 그대로 복사한 짧은 연속 인용문(text)을 넣습니다. 표의 경우 셀 하나의 수치도 가능합니다. "
        "균등 참여 시 비례 손익 계산에 필요한 terms만 채웁니다. 확인하지 못한 값은 null입니다. "
        "terms_evidence에도 실제 조회한 조건의 원문을 인용합니다. 증거금률은 50%면 0.5입니다. "
        "배정 전에는 청약단위에 맞는 신청 수량과 이를 뒷받침할 근거가 있을 때만 "
        "비례 1주 추가 배정 가정을 사용합니다. 균등·비례의 최종 손익 판정은 실행 프로그램에서 계산합니다."
    ),
)


def format_schedule(schedule: SubscriptionCandidates) -> str:
    lines = [f"청약 일정 ({schedule.start} ~ {schedule.end})"]
    lines.extend(f"- {c.company}: {c.opens_on} ~ {c.closes_on}" for c in schedule.candidates)
    lines.extend(schedule.issues)
    return "\n".join(lines)


def format_assessment(item: CompanyAssessment, tool_outputs: list) -> str:
    lines = []
    pages = {}
    for output in tool_outputs:
        if isinstance(output, FilingEvidenceResult) and isinstance(output.result, EvidenceFound):
            for page in output.result.evidence:
                key = (output.result.company, output.receipt_no, page.page)
                pages.setdefault(key, []).append("".join(page.text.split()))

    def verified(ref: FilingEvidence) -> bool:
        texts = pages.get((item.company, ref.receipt_no, ref.page), [])
        return (ref.receipt_no[:8] <= item.as_of.astimezone(KST).strftime("%Y%m%d")
                and any("".join(ref.text.split()) in text for text in texts))

    equal = item.equal
    verified_evidence = [ref for ref in equal.evidence if verified(ref)]
    if len(verified_evidence) != len(equal.evidence):
        reason = "일부 공시 인용을 기준 시점과 원문에서 확인할 수 없습니다."
        if equal.decision == "판단 보류":
            reason = f"{equal.reason} {reason}"
        equal = EqualAssessment(decision="판단 보류", reason=reason, evidence=verified_evidence)
    terms = item.terms
    if not item.terms_evidence or not all(verified(ref) for ref in item.terms_evidence):
        terms = None
    if terms and terms.allocation and terms.allocation.basis == "실제 배정":
        terms = terms.model_copy(update={"allocation": None})
    decision = apply_subscription_policy(equal, terms)
    lines.extend(("", f"{item.company} | {decision.decision} | 기준 {item.as_of.isoformat()}",
                  f"균등 판단: {decision.equal.decision} ({decision.equal.reason})"))
    for ref in decision.equal.evidence + (item.terms_evidence if terms else []):
        lines.append(f"- PDF {ref.page}쪽: {ref.text} (https://dart.fss.or.kr/dsaf001/main.do?rcpNo={ref.receipt_no})")
    if decision.unconfirmed and decision.unconfirmed != [decision.equal.reason]:
        lines.append("확인하지 못한 조건: " + ", ".join(decision.unconfirmed))
    calc = decision.calculation
    if calc:
        lines.append(f"{calc.allocation.basis}: {calc.allocation.reason}")
        lines.append(f"추가 증거금 {calc.extra_deposit:,.2f}원, {calc.calendar_days}일 자금 비용 {calc.funding_cost:,.2f}원 ({calc.cost_note})")
        for row in calc.scenarios:
            lines.append(f"- {row.rise_pct:+d}% 매도가 {row.sale_price:,.2f}원: 추가 손익 {row.extra_profit:+,.2f}원")
        if calc.break_even_sale_price is not None:
            lines.append(f"주당 손익분기 매도가: {calc.break_even_sale_price:,.2f}원")
    return "\n".join(lines).strip()
