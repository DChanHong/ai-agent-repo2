import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from threading import Barrier
from time import sleep
from types import SimpleNamespace
from unittest.mock import patch

from agents import MaxTurnsExceeded
from agents.tool_context import ToolContext

from main import run_request
from ipo_agent.agents.subscription import AgentAnswer, AssessmentPlan, CompanyAssessment
from ipo_agent.schemas import FilingEvidenceResult, SubscriptionCandidates
from ipo_agent.tools import filing_evidence
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

    def test_parallel_first_filing_queries_open_one_collection(self):
        barrier = Barrier(4)
        filing_evidence._open_collection.cache_clear()
        self.addCleanup(filing_evidence._open_collection.cache_clear)

        def query():
            barrier.wait(timeout=5)
            return filing_evidence.get_collection()

        with patch.object(filing_evidence.chromadb, "PersistentClient") as client, \
             patch.object(filing_evidence, "OpenAIEmbeddingFunction"):
            def open_collection(**kwargs):
                sleep(0.02)  # 다른 스레드가 아직 초기화 중인 컬렉션에 접근하는 상황입니다.
                return object()

            client.return_value.get_collection.side_effect = open_collection
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(query) for _ in range(4)]
                collections = [future.result() for future in futures]
            client.assert_called_once()
            self.assertTrue(all(c is collections[0] for c in collections))

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



class TestRequestTurnLimit(unittest.TestCase):
    def run_result(self, final_output, turns, *outputs):
        items = [SimpleNamespace(type="tool_call_output_item", output=o) for o in outputs]
        return SimpleNamespace(final_output=final_output, new_items=items, raw_responses=[None] * turns)

    def setUp(self):
        self.targets = ["가기업", "나기업", "다기업"]
        schedule = SubscriptionCandidates(
            start=date(2026, 11, 2), end=date(2026, 11, 6), candidates=[],
            analysis_companies=self.targets, issues=[],
        )
        plan = AgentAnswer(answer=AssessmentPlan(include_schedule=True, companies=[]))
        self.plan_result = self.run_result(plan, 2, schedule)

    def assessment(self, company, turns):
        receipt = "20261030000113"
        quote = {"page": 33, "text": "확약 신청 0주"}
        evidence = FilingEvidenceResult.model_validate({
            "receipt_no": receipt,
            "result": {"status": "found", "company": company, "evidence": [quote],
                       "source_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"},
        })
        assessment = CompanyAssessment.model_validate({
            "company": company, "as_of": "2026-11-03T10:00:00+09:00",
            "equal": {"decision": "청약 안 함", "reason": "확약 신청 0주",
                      "evidence": [dict(quote, receipt_no=receipt)]},
            "terms": None, "terms_evidence": [],
        })
        return self.run_result(assessment, turns, evidence)

    def test_interruption_preserves_two_assessments_and_their_citations(self):
        interruption = MaxTurnsExceeded("limit")
        # 세 번째 종목의 도구가 근거를 찾아도 모델의 종목별 판단이 반환되기 전입니다.
        interruption.run_data = SimpleNamespace(new_items=self.assessment("다기업", 1).new_items)
        results = [self.plan_result, self.assessment("가기업", 4), self.assessment("나기업", 5), interruption]
        with patch("main.Runner.run_sync", side_effect=results) as run:
            report = run_request("세 종목을 분석해 주세요")
        self.assertEqual([call.kwargs["max_turns"] for call in run.call_args_list], [12, 10, 6, 1])
        self.assertIn("목표 미달성 · 3개 중 2개 완료", report)
        self.assertIn("가기업 | 청약 안 함", report)
        self.assertIn("나기업 | 청약 안 함", report)
        self.assertEqual(report.count("PDF 33쪽"), 2)
        self.assertIn("다기업 | 반복 한도 도달로 분석 미완료", report)

    def test_last_allowed_turn_can_finish_or_leave_the_next_company_pending(self):
        for targets, expected in [(self.targets, "3개 중 2개 완료"), (self.targets[:2], "나기업 | 청약 안 함")]:
            with self.subTest(targets=targets):
                plan = AgentAnswer(answer=AssessmentPlan(include_schedule=False, companies=targets))
                results = [self.run_result(plan, 2), self.assessment("가기업", 5), self.assessment("나기업", 5)]
                with patch("main.Runner.run_sync", side_effect=results) as run:
                    report = run_request("지정한 종목을 판단해 주세요")
                self.assertIn(expected, report)
                self.assertEqual("목표 미달성" in report, len(targets) == 3)
                self.assertEqual(run.call_count, 3)

    def test_simple_answer_finishes_without_company_assessment(self):
        result = self.run_result(AgentAnswer(answer="조회한 일정입니다."), 2)
        with patch("main.Runner.run_sync", return_value=result) as run:
            self.assertEqual(run_request("일정만 조회"), "조회한 일정입니다.")
        self.assertEqual(run.call_count, 1)
