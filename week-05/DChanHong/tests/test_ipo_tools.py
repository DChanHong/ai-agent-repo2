import json
import unittest
from datetime import date, datetime
from unittest.mock import patch

from agents.tool_context import ToolContext

from ipo_agent.tools.recent_ipo_performance import KST, last_closed_day, recent_performance
from ipo_agent.tools.subscription_candidates import find_subscription_candidates


def offer(name, code, period, listed="2026/11/10"):
    return {"isin_name": name, "sht_cd": code, "subscr_dt": period,
            "list_dt": listed, "fix_subscr_pri": "10000"}


class TestIpoTools(unittest.IsolatedAsyncioTestCase):
    async def test_overlapping_offers_and_tied_deadlines(self):
        rows = [
            offer("나기업", "000002", "2026/11/02 ~ 2026/11/03"),
            offer("가기업", "000001", "2026/11/02 ~ 2026/11/03"),
            offer("다기업", "000003", "2026/11/01 ~ 2026/11/02"),
            offer("라기업", "000004", "2026/11/03 ~ 2026/11/04"),
            offer("테스트스팩1호", "000005", "2026/11/02 ~ 2026/11/03"),
        ]
        tool = find_subscription_candidates
        args = json.dumps({"start": "2026-11-02", "end": "2026-11-03"})
        ctx = ToolContext(None, tool_name=tool.name, tool_call_id="test", tool_arguments=args)
        with patch("ipo_agent.tools.subscription_candidates.kis_client") as client:
            client.return_value.offers.return_value = rows + rows[:1]
            result = await tool.on_invoke_tool(ctx, args)
        self.assertEqual(len(result.candidates), 4)
        self.assertEqual(result.analysis_companies, ["다기업", "가기업", "나기업"])
        self.assertIsNone(result.candidates[0].filing)

    def test_regular_and_delayed_close(self):
        for day, hour in [(16, 15), (19, 16)]:
            self.assertLess(last_closed_day(datetime(2026, 11, day, hour, 29, tzinfo=KST)),
                            date(2026, 11, day))
            self.assertEqual(last_closed_day(datetime(2026, 11, day, hour, 30, tzinfo=KST)),
                             date(2026, 11, day))

    def test_missing_first_day_bar_keeps_the_recent_three(self):
        rows = [offer(f"기업{day}", str(day), "", f"2026/11/{day}")
                for day in [10, 11, 12, 16]]
        with patch("ipo_agent.tools.recent_ipo_performance.kis_client") as factory:
            client = factory.return_value
            client.offers.return_value = rows
            client.stock_info.side_effect = lambda code: {
                "scty_grp_id_cd": "ST", "kosdaq_mket_lstg_dt": f"202611{code}"}
            client.daily_prices.side_effect = lambda code, day: [] if code == "12" else [{
                "stck_bsop_date": f"202611{code}", "stck_oprc": "15000", "stck_clpr": "12000"}]
            result = recent_performance(datetime(2026, 11, 16, 16, tzinfo=KST))
        self.assertEqual([i.stock_code for i in result.items], ["16", "11"])
        self.assertIn("기업12", result.issues[0])
        self.assertEqual(result.items[0].open_to_close_pct, -20)
