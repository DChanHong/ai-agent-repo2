from datetime import date
from typing import Literal

from ipo_agent.schemas import IpoFirstDayPerformance


def read_first_day_performance(
    *,
    company: str,
    stock_code: str,
    market: Literal["KOSPI", "KOSDAQ"],
    listing_date: date,
    offer_price: int,
    daily_prices: list[dict],
) -> IpoFirstDayPerformance | None:
    """KIS 일별시세 응답의 output2에서 상장 당일 일봉을 읽습니다."""
    listing_day = listing_date.strftime("%Y%m%d")
    for row in daily_prices:
        if row.get("stck_bsop_date") != listing_day:
            continue

        try:
            open_price = int(row["stck_oprc"])
            close_price = int(row["stck_clpr"])
        except (KeyError, TypeError, ValueError):
            return None

        if min(offer_price, open_price, close_price) <= 0:
            return None

        return IpoFirstDayPerformance(
            company=company,
            stock_code=stock_code,
            market=market,
            listing_date=listing_date,
            offer_price=offer_price,
            open_price=open_price,
            close_price=close_price,
        )

    return None
