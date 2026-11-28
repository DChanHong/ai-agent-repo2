from agents import Agent

from ipo_agent.tools.filing_evidence import read_filing_evidence
from ipo_agent.tools.recent_ipo_performance import get_recent_ipo_performance
from ipo_agent.tools.subscription_candidates import find_subscription_candidates


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
        "그래도 확인할 수 없으면 해당 항목과 이유를 밝히고 종료합니다."
    ),
    tools=[find_subscription_candidates, read_filing_evidence, get_recent_ipo_performance],
)
