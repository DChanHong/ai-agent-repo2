from agents import Agent

from ipo_agent.tools.filing_evidence import read_filing_evidence


subscription_agent = Agent(
    name="공모주 청약 판단 에이전트",
    model="gpt-6-luna",
    instructions=(
        "공시 근거 확인을 요청받으면 접수번호와 확인할 항목을 "
        "read_filing_evidence에 전달합니다. "
        "확인한 수치와 단위, PDF 쪽 번호, DART 링크를 한국어로 제시합니다. "
        "수치를 인용할 때는 그 수치가 적힌 evidence 항목의 page를 PDF 쪽 번호로 사용합니다. "
        "표 제목과 합계가 서로 다른 쪽에 있으면 각각의 쪽 번호를 구분합니다. "
        "계산한 값은 원문 수치와 계산식을 함께 제시합니다. "
        "근거가 부족하면 빠진 항목을 구체화해 한 번 더 조회합니다. "
        "그래도 확인할 수 없으면 해당 항목과 이유를 밝히고 종료합니다."
    ),
    tools=[read_filing_evidence],
)
