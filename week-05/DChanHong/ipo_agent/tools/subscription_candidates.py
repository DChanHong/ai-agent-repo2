from datetime import date, timedelta

from agents import function_tool

from filing_index import FILINGS, PDF_DIR
from ipo_agent.lib.kis import KisError, is_regular_offer, kis_client, kis_date
from ipo_agent.schemas import FilingReference, SubscriptionCandidate, SubscriptionCandidates


@function_tool(output_type=SubscriptionCandidates)
def find_subscription_candidates(
    start: date, end: date, first_closing_only: bool = False,
) -> SubscriptionCandidates:
    """조회 기간과 겹치는 일반기업 IPO 청약 일정, 로컬 공시와 상세 분석 대상 최대 3곳을 조회합니다.

    Args:
        start: 조회 시작일입니다.
        end: 조회 종료일입니다. 시작일과 종료일 모두 포함합니다.
        first_closing_only: 가장 먼저 마감하는 한 종목을 요청하면 True입니다. 같은 날이면 회사명 가나다순 첫 종목을 반환합니다.
    """
    candidates = {}
    issues = []
    try:
        if start > end:
            raise ValueError("조회 시작일이 종료일보다 늦습니다.")
        # KIS 기준일은 청약 시작일입니다. 기간을 걸치는 청약도 가져옵니다.
        rows = kis_client().offers(start - timedelta(days=31), end)
        for row in rows:
            name = row["isin_name"].strip()
            if not is_regular_offer(name):
                continue
            dates = row["subscr_dt"].split("~")
            try:
                opens = kis_date(dates[0])
                closes = kis_date(dates[-1])
                if not opens or not closes or opens > closes:
                    raise ValueError
            except ValueError:
                issues.append(f"{name} 청약 기간 확인 불가")
                continue
            if opens > end or closes < start:
                continue
            filing = None
            if name in FILINGS:
                filename, number = FILINGS[name]
                if (PDF_DIR / filename).is_file():
                    filing = FilingReference(receipt_no=number, filed_on=kis_date(number[:8]),
                                             report_name="증권신고서(지분증권) · 증권발행조건확정")
            code = row["sht_cd"].strip()
            candidates[code, opens] = SubscriptionCandidate(
                company=name, stock_code=code, opens_on=opens, closes_on=closes, filing=filing,
            )
    except (ValueError, KisError) as exc:
        issues.append(str(exc))
    ordered = sorted(candidates.values(), key=lambda item: (item.closes_on, item.company, item.stock_code))
    if first_closing_only:
        ordered = ordered[:1]
    return SubscriptionCandidates(start=start, end=end, candidates=ordered, first_closing_only=first_closing_only,
                                  analysis_companies=[item.company for item in ordered[:3]], issues=issues)
