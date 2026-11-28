"""공시 근거로 내린 균등 판단에 비례 청약의 추가 손익 정책을 적용합니다."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, PositiveInt

from ipo_agent.schemas import EvidencePage, Question, ReceiptNo, Schema


ANNUAL_RATE = Decimal("0.03")
DECISION_RISE_PCT = 20


class FilingEvidence(EvidencePage):
    receipt_no: ReceiptNo


class EqualAssessment(Schema):
    decision: Literal["균등 참여", "청약 안 함", "판단 보류"]
    reason: Question
    evidence: list[FilingEvidence]


class Allocation(Schema):
    basis: Literal["비례 1주 추가 배정 가정", "실제 배정"]
    extra_shares: NonNegativeInt
    # 신청 수량을 선택한 근거 또는 배정 후 확인한 결과를 기록합니다.
    reason: Question


class ProportionalTerms(Schema):
    offer_price: PositiveInt | None = None
    minimum_quantity: PositiveInt | None = None
    # 해당 증권사의 청약단위에 맞는 총 신청 수량입니다.
    application_quantity: PositiveInt | None = None
    deposit_rate: Annotated[Decimal, Field(gt=0, le=1)] | None = None
    closing_date: date | None = None
    refund_date: date | None = None
    allocation: Allocation | None = None


class ProfitScenario(Schema):
    rise_pct: int
    sale_price: Decimal
    extra_profit: Decimal


class ProportionalCalculation(Schema):
    allocation: Allocation
    extra_deposit: Decimal
    calendar_days: int
    funding_cost: Decimal
    break_even_sale_price: Decimal | None
    scenarios: list[ProfitScenario]
    cost_note: Literal["매도 비용 제외"] = "매도 비용 제외"


class SubscriptionDecision(Schema):
    equal: EqualAssessment
    decision: Literal["청약 안 함", "균등만", "비례까지", "판단 보류"]
    unconfirmed: list[str] = Field(default_factory=list)
    calculation: ProportionalCalculation | None = None


def apply_subscription_policy(
    equal: EqualAssessment, terms: ProportionalTerms | None = None
) -> SubscriptionDecision:
    """한 종목을 판정합니다. 균등 판단의 근거는 비례 단계의 보류 여부와 함께 반환합니다."""
    if equal.decision == "판단 보류":
        return SubscriptionDecision(equal=equal, decision="판단 보류", unconfirmed=[equal.reason])
    if not equal.evidence:
        pending = EqualAssessment(decision="판단 보류", reason="균등 판단의 공시 근거 미확인", evidence=[])
        return SubscriptionDecision(equal=pending, decision="판단 보류", unconfirmed=[pending.reason])
    if equal.decision == "청약 안 함":
        return SubscriptionDecision(equal=equal, decision="청약 안 함")

    terms = terms or ProportionalTerms()
    required = {
        "공모가": terms.offer_price,
        "최소 청약 수량": terms.minimum_quantity,
        "비례 포함 신청 수량": terms.application_quantity,
        "증거금률": terms.deposit_rate,
        "청약 마감일": terms.closing_date,
        "환불일": terms.refund_date,
        "비례 추가 배정 주수와 근거": terms.allocation,
    }
    issues = [label for label, value in required.items() if value is None]
    if terms.refund_date and terms.closing_date and terms.refund_date < terms.closing_date:
        issues.append("환불일이 마감일보다 이릅니다.")
    if terms.application_quantity and terms.minimum_quantity and terms.application_quantity <= terms.minimum_quantity:
        issues.append("비례 포함 신청 수량이 최소 청약 수량을 초과해야 합니다.")
    allocation = terms.allocation
    if allocation and allocation.basis == "비례 1주 추가 배정 가정" and allocation.extra_shares != 1:
        issues.append("비례 1주 가정과 추가 배정 주수가 일치하지 않습니다.")
    if issues:
        return SubscriptionDecision(equal=equal, decision="판단 보류", unconfirmed=issues)

    extra_deposit = (terms.application_quantity - terms.minimum_quantity) * terms.offer_price * terms.deposit_rate
    days = (terms.refund_date - terms.closing_date).days
    cost = extra_deposit * ANNUAL_RATE * days / 365
    scenarios = []
    for rise_pct in (0, DECISION_RISE_PCT, 50):
        gain_per_share = Decimal(terms.offer_price) * rise_pct / 100
        scenarios.append(ProfitScenario(
            rise_pct=rise_pct,
            sale_price=terms.offer_price + gain_per_share,
            extra_profit=gain_per_share * allocation.extra_shares - cost,
        ))
    baseline = next(row for row in scenarios if row.rise_pct == DECISION_RISE_PCT)
    break_even = terms.offer_price + cost / allocation.extra_shares if allocation.extra_shares else None
    return SubscriptionDecision(
        equal=equal,
        decision="비례까지" if baseline.extra_profit > 0 else "균등만",
        calculation=ProportionalCalculation(
            allocation=allocation, extra_deposit=extra_deposit, calendar_days=days,
            funding_cost=cost, break_even_sale_price=break_even, scenarios=scenarios,
        ),
    )
