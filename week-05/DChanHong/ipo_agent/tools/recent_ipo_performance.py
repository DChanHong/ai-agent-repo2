from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from agents import function_tool
from exchange_calendars import get_calendar
from pydantic import AwareDatetime

from ipo_agent.lib.kis import KisError, is_regular_offer, kis_client, kis_date
from ipo_agent.schemas import IpoFirstDayPerformance, RecentIpoPerformance


KST = ZoneInfo("Asia/Seoul")


def last_closed_day(as_of: datetime) -> date:
    day = as_of.date()
    previous = day - timedelta(days=1)
    calendar = get_calendar("XKRX", start=day - timedelta(days=7), end=day + timedelta(days=7))
    if not calendar.is_session(day):
        return previous
    close = calendar.session_close(day).to_pydatetime()
    # KRX 2026-11-05 공지: 11월 19일은 수능으로 16:30에 마감합니다.
    # https://kind.krx.co.kr/external/2026/11/05/000141/20261105000216/99303.htm
    if day == date(2026, 11, 19):
        close = datetime.combine(day, time(16, 30), KST)
    return day if as_of >= close else previous


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


def recent_performance(as_of: datetime) -> RecentIpoPerformance:
    as_of = as_of.astimezone(KST)
    start = as_of.date() - timedelta(days=180)
    result = RecentIpoPerformance(as_of=as_of, calendar_from=start, items=[], issues=[])
    if as_of > datetime.now(KST):
        result.issues.append("기준 시점이 현재보다 늦습니다.")
        return result
    try:
        cutoff = last_closed_day(as_of)
        client = kis_client()
        rows = client.offers(start, cutoff)
        info_by_code = {}
        candidates = {}
        for row in rows:
            code = row["sht_cd"].strip()
            name = row["isin_name"].strip()
            if not is_regular_offer(name):
                continue
            listed = kis_date(row["list_dt"])
            if not listed:
                # 청약 일정에 상장일이 빈 종목은 주식기본조회의 상장일로 보완합니다.
                info = client.stock_info(code)
                info_by_code[code] = info
                listed = kis_date(info.get("scts_mket_lstg_dt")) or kis_date(info.get("kosdaq_mket_lstg_dt"))
            if listed and start <= listed <= cutoff:
                candidates[code] = (listed, name, row)

        ranked = sorted(candidates.items(), key=lambda pair: (-pair[1][0].toordinal(), pair[1][1], pair[0]))
        selected = 0
        for code, (listed, name, row) in ranked:
            info = info_by_code[code] if code in info_by_code else client.stock_info(code)
            if not info:
                result.issues.append(f"{name} 시장 및 신규 상장 여부 확인 불가")
                continue
            if info.get("scty_grp_id_cd") not in ("ST", "DR") or info.get("reits_kind_cd", "").strip(" 0"):
                continue
            if listed == kis_date(info.get("scts_mket_lstg_dt")):
                market = "KOSPI"
            elif listed == kis_date(info.get("kosdaq_mket_lstg_dt")):
                market = "KOSDAQ"
            else:
                continue
            selected += 1
            price = str(row["fix_subscr_pri"]).strip().replace(",", "")
            try:
                prices = client.daily_prices(code, listed)
            except KisError as exc:
                result.issues.append(f"{name}({code}) 일별시세 확인 불가: {exc}")
            else:
                item = read_first_day_performance(
                    company=name, stock_code=code, market=market, listing_date=listed,
                    offer_price=int(price) if price.isdigit() else 0, daily_prices=prices,
                )
                if item:
                    result.items.append(item)
                else:
                    result.issues.append(f"{name}({code})의 확정 공모가 또는 상장일 시가·종가 확인 불가")
            if selected == 3:
                break
        if selected < 3:
            result.issues.append(f"{start} 이후 조회한 청약 일정에서 일반기업 IPO {selected}곳을 확인했습니다.")
    except (KisError, ValueError) as exc:
        result.issues.append(str(exc))
    return result


@function_tool(output_type=RecentIpoPerformance)
def get_recent_ipo_performance(as_of: AwareDatetime) -> RecentIpoPerformance:
    """기준 시점에 상장일 종가가 공개된 최근 일반기업 IPO 3곳의 시가·종가와 등락률을 조회합니다.

    Args:
        as_of: 시간대가 있는 분석 기준 일시입니다. 한국 시간은 +09:00입니다.
    """
    return recent_performance(as_of)
