"""고정된 10개 질문의 RAG 실행과 평가 도구."""

import os

# 로컬 검증과 평가 중 프레임워크 분석 이벤트 전송을 비활성화합니다.
os.environ["RAGAS_DO_NOT_TRACK"] = "true"
os.environ["ANONYMIZED_TELEMETRY"] = "False"
