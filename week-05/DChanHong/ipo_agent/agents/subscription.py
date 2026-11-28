import re
from decimal import Decimal, ROUND_HALF_UP

from agents import Agent
from pydantic import AwareDatetime, NonNegativeInt, PositiveInt

from ipo_agent.schemas import EvidenceFound, FilingEvidenceResult, ReceiptNo, Schema, SubscriptionCandidates
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


class LockupRateAnswer(Schema):
    receipt_no: ReceiptNo
    page: PositiveInt
    uncommitted_quantity: NonNegativeInt
    total_quantity: PositiveInt


class AgentAnswer(Schema):
    answer: str | LockupRateAnswer | AssessmentPlan


subscription_agent = Agent(
    name="공모주 청약 판단 에이전트",
    model="gpt-6-luna",
    instructions=(
        "기간별 청약 일정과 후보는 find_subscription_candidates로 조회합니다. "
        "마감이 가장 빠른 한 종목(동률이면 가나다순) 요청은 first_closing_only=true로 조회합니다. "
        "반환된 한 후보의 filing.receipt_no를 그대로 후속 공시 조회에 사용합니다. "
        "공시가 없으면 해당 종목의 PDF 미확보로 답합니다. "
        "전체 일정이나 특정 종목을 요청하면 first_closing_only=false로 조회합니다. "
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
        "한 종목의 수량 기준 의무보유확약 신청률을 묻는 요청에는 공시 도구로 '확약기간별 수요예측 참여내역'을 조회합니다. "
        "전체 기관 합계 열의 미확약 수량과 전체 신청 수량을 원문에서 찾으면 LockupRateAnswer에 "
        "접수번호, 그 두 행의 PDF 쪽 번호, 두 수량(주)을 반환합니다. 백분율은 프로그램이 계산합니다. "
        "수량을 확인하지 못하면 누락 항목을 밝히고 계산을 보류합니다. "
        "그 밖의 단순 사실 조회는 배정이나 비례라는 단어가 있어도 answer에 일반 문자열로 답합니다. "
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


def _lockup_quantities_match(answer: LockupRateAnswer, filing: EvidenceFound) -> bool:
    pages = {page.page: page.text for page in filing.evidence}
    # 표 제목은 합계 행과 같은 쪽 또는 바로 앞쪽에 있습니다.
    table = pages.get(answer.page - 1, "") + "\n" + pages.get(answer.page, "")
    _, title, table = table.rpartition("확약기간별 수요예측 참여내역")
    if not title or answer.page not in pages:
        return False
    # 합계 열이 붙은 외국 기관 표에서 마지막 세 칸은 건수, 수량, 신청가격입니다.
    _, header, totals = table.partition("외국 기관투자자")
    if not header or not re.search(r"합\s*계", totals):
        return False
    table_body = re.split(r"(?m)^\s*주1\)|^\s*\(라\)", totals, maxsplit=1)[0]
    rows = []
    for line in table_body.splitlines():
        cells = line.split()
        # 증권신고서 양식은 외국 기관 두 그룹과 전체 합계를 각각 세 칸에 표시합니다.
        if len(cells) < 9 or not all(re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+|-)", c) for c in cells[-9:]):
            continue
        rows.append((line, "".join(cells[:-9]), cells[-2]))
    # 6개월, 3개월, 1개월, 15일, 미확약, 계 순서이며, 일부 PDF에는 행 이름이 생략됩니다.
    expected_labels = ("6개월확약", "3개월확약", "1개월확약", "15일확약", "미확약", "계")
    if len(rows) != len(expected_labels):
        return False
    for (_, label, _), expected in zip(rows, expected_labels):
        if label and label.removeprefix("합") != expected:
            return False
    values = [0 if cell == "-" else int(cell.replace(",", "")) for _, _, cell in rows]
    return (
        values[-2:] == [answer.uncommitted_quantity, answer.total_quantity]
        and sum(values[:-1]) == answer.total_quantity
        and all(line in pages[answer.page] for line, _, _ in rows[-2:])
    )


def format_lockup_rate(answer: LockupRateAnswer, outputs: list) -> str:
    """전체 기관 합계 열의 수량을 대조한 뒤 (전체 - 미확약) / 전체를 계산합니다."""
    for output in outputs:
        if not isinstance(output, FilingEvidenceResult) or output.receipt_no != answer.receipt_no:
            continue
        filing = output.result
        if not isinstance(filing, EvidenceFound) or not _lockup_quantities_match(answer, filing):
            continue
        committed = answer.total_quantity - answer.uncommitted_quantity
        percent = (Decimal(committed) * 100 / answer.total_quantity).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        lines = [f"{filing.company}의 수량 기준 의무보유확약 신청률은 {percent:.2f}%입니다."]
        for schedule in outputs:
            if isinstance(schedule, SubscriptionCandidates):
                selected = next((c for c in schedule.candidates
                                 if c.filing and c.filing.receipt_no == answer.receipt_no), None)
                if selected:
                    if schedule.first_closing_only:
                        lines.append(f"최초 마감일 {selected.closes_on}, 동률 시 회사명 가나다순으로 선정했습니다.")
                        break
                    tied = [c.company for c in schedule.candidates if c.closes_on == selected.closes_on]
                    lines.append(f"{selected.closes_on} 마감 종목(가나다순): {', '.join(sorted(tied))}")
                    break
        lines.extend([
            f"확약 신청 수량: 전체 {answer.total_quantity:,}주 − 미확약 {answer.uncommitted_quantity:,}주 = {committed:,}주",
            f"신청률: {committed:,} ÷ {answer.total_quantity:,} × 100 = {percent:.2f}% (소수점 둘째 자리까지 표시)",
            f"근거: 의무보유확약기간별 수요예측 참여내역, PDF {answer.page}쪽. {filing.source_url}",
        ])
        return "\n".join(lines)
    return "계산 보류 | 조회한 공시의 의무보유확약 표에서 미확약 수량과 전체 신청 수량을 검증하지 못했습니다."


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
