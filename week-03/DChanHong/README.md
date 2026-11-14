# RAG 평가 실행 안내

응답 생성 직전까지 준비한 코드다. 골든 10문항, Pydantic 검증, 기존 청크·색인 복사와 로컬 검증을 완료했다. 준비 상태 검증 명령과 로컬 테스트 36개가 통과했다. 모의 10문항 생성→평가→요약은 임시 폴더에서만 검증했으며 실제 응답 생성·자동 평가·사람 검토는 아직 실행하지 않았다.

기준 문서는 [평가 설계](docs/00-plan/EVALUATION_SPEC.md)와 [TODO](docs/00-plan/TODO.md)다. 스키마의 단일 원본은 [schemas/](schemas/)이며, 별도 수작업 JSON Schema 파일은 사용하지 않는다.

실행은 프로젝트 루트의 `main.py`에서 시작한다. 코드는 아래처럼 역할별로 나누며, 프롬프트는 Python 문자열 상수로 관리한다. manifest에는 실제 API에 전달한 프롬프트 전문과 해시를 남긴다. 프롬프트 해시는 `.py` 파일 전체가 아니라 실제 전달 문자열의 SHA-256이다.

| 위치 | 역할 |
|---|---|
| `main.py`, `config.py` | 명령 진입점과 공통 설정 |
| `common/` | API 호출 기록, 파일 처리, 데이터·환경 검증 |
| `schemas/` | 골든·실행·평가·사람 검토의 Pydantic 모델 |
| `rag/` | 기존 색인 검증과 검색·응답 생성 |
| `evaluation/` | 저장된 답변의 Ragas·규칙·Judge 평가 |
| `reporting/` | 사람 검토 이력과 JSON·CSV 요약 |
| `prompts/` | 생성·Judge 프롬프트와 버전 상수 |
| `data/golden/`, `data/rag/` | 골든 데이터와 기존 RAG 자료 |
| `tests/` | 외부 API를 호출하지 않는 로컬 검증 |

## 준비된 환경과 자료

- Python 3.13.2 가상환경 `.venv`, 직접 의존성 `pyproject.toml`, 해석된 전체 의존성 `uv.lock`.
- `ragas==0.4.3`, `openai==2.54.0`, `instructor==1.17.0`, `chromadb==1.5.9`.
- `data/golden/golden_v1.json`: Q01~Q10의 골든 답변·원문·규칙·지표 정책.
- `data/rag/chunks.json`, `data/rag/sections.json`: 2주차 원본 바이트를 유지한 자료. 청크 325개 중 정정 전 155개, 정정 후 165개, 안내 5개.
- `chroma_db/`: 기존 2주차 색인의 독립 복사본. 청크 ID·본문·메타데이터·1,536차원 벡터·해시·cosine 설정을 검증했다. 재임베딩 API 호출은 없었다.
- `data/rag/baseline.json`: 원본 Git 커밋·자료 해시·색인 재사용과 준비 비용 기록.
- `prompts/generation.py`의 `GENERATION_PROMPT`: 기존 생성 지침 전문. `prompts/judge.py`의 `JUDGE_PROMPT`: 확정한 Judge 지침.

설치 호환성 보정으로 `langchain-community==0.4.1`을 고정했다. 0.4.2에서 제거된 VertexAI 모듈을 Ragas 0.4.3이 import하는 문제를 확인했으며, 0.4.1에서는 import와 네 지표의 모의 HTTP 실행을 검증했다. Ragas·OpenAI·Instructor의 합의 버전은 유지한다.

기존 청킹 1,200자·최대 중첩 200자, 정정 전 3개 뒤에 정정 후 3개를 연결하는 검색 순서를 유지한다. 생성 모델은 `gpt-5.4-mini-2026-03-17`, 추론 `none`, 출력 상한 2,000토큰이다. 질문과 검색 근거만 생성 입력으로 전달하며 골든 답변·평가 조건은 포함하지 않는다.

## 1. 로컬 검증

아래 명령은 모두 프로젝트 폴더에서 실행한다.

```sh
cd /Users/root1/Desktop/ai-agent-repo2/week-03/DChanHong
.venv/bin/python main.py validate
.venv/bin/python -m unittest discover -s tests -v
```

검증에는 API 키가 필요하지 않다. 원문 해시·골든 참조·고정 패키지·기존 색인과 모의 입력을 검사하며 유료 모델을 호출하지 않는다. 다른 환경에서 설치를 재현할 때는 이 폴더에서 `uv sync --locked`를 사용한다.

기존 색인에서 다시 준비할 필요가 있을 때만 다음을 실행한다. 대상 색인이 이미 있으면 검증만 하며, 기존 파일을 덮어쓰지 않는다.

```sh
.venv/bin/python main.py prepare-index --source ../../week-02/DChanHong/chroma_db
```

## 2. 응답 생성 — 사용자가 실행

사용자가 `OPENAI_API_KEY` 환경 변수 또는 프로젝트의 `.env`에 키를 설정한다. `.env`를 처음 만들 때는 `cp -n .env.example .env`로 기존 파일을 보존한 뒤 예시 값을 직접 교체한다. 준비 작업에서는 실제 `.env` 내용과 키를 읽거나 확인하지 않았다.

```sh
.venv/bin/python main.py generate
```

이 명령부터 질문 임베딩·응답 생성 API를 호출한다. Q01~Q10을 각각 한 번 실행하고 새 `output/rag_runs/<rag_run_id>/` 경로를 출력한다. 키가 없으면 API 호출 전에 중단한다. 새 실행은 새 폴더를 사용하므로 기존 결과를 덮어쓰지 않는다.

- `manifest.json`: 문서·청킹·검색 개수와 순서·모델·프롬프트·버전·단가.
- `Q01.json`~`Q10.json`: 검색 결과, 실제 전달한 지침·입력·컨텍스트, 최종 답변, 상태·시간·원본 API 호출과 usage.

API가 끝났어도 빈 답변이나 출력 잘림은 `needs_check`다. 오류는 `error`로 보존하며 품질 통과를 뜻하지 않는다. 중단된 실행의 미실행 문항은 `pending`으로 남는다.

## 3. 저장된 답변 평가

응답 생성에서 출력된 실제 경로를 사용한다. 평가 명령은 새 답변을 생성하지 않고 저장된 RAG 결과를 읽으며, 평가용 API를 호출한다.

```sh
.venv/bin/python main.py evaluate "output/rag_runs/<rag_run_id>"
```

| 지표 | 무엇을 평가하는가 | 입력 | 적용 문항 |
|---|---|---|---|
| Context Precision | 검색 순서에서 필요한 근거의 적절한 배치 | 질문, 반환 순서의 검색 컨텍스트, 검색용 reference | Q01~Q06·Q09~Q10 |
| Context Recall | 정답의 근거 사실을 얼마나 찾았는가 | 질문, 검색 컨텍스트, 검색용 reference | Q01~Q06·Q09~Q10 |
| Faithfulness | 답변의 사실 주장이 실제 제공 근거로 뒷받침되는가 | 질문, 답변 전체, 실제 제공 컨텍스트 | 사실 주장이 있는 답변 |
| Answer Relevancy | 답변이 원래 질문과 얼마나 관련되는가 | 질문, 답변 전체, 평가 LLM·임베딩 | Q01~Q06 |

Q09·Q10의 검색 reference에는 답변 가능한 부분만 포함한다. 순수한 확인 불가 안내는 Faithfulness 적용 불가이며, 사실 주장 추출 실패와 구분한다. 지표의 낮은 점수는 숨기지 않고 `not_applicable`, `skipped`, `error`와 별도로 보존한다.

Ragas와 Judge는 `gpt-5.4-2026-03-05`, 평가 임베딩은 `text-embedding-3-large` 3,072차원을 사용한다. 검색 임베딩 `text-embedding-3-small` 1,536차원과 구분한다. Ragas 4개 지표, 규칙 검사, Judge의 정확성·인용 적절성·답변 범위 판정과 각각의 이유를 `output/eval_runs/<eval_run_id>/`에 기록한다. 수치의 대상·기간·정정 구분이 불명확한 규칙 결과는 `undetermined`로 남긴다.

Ragas의 실제 내부 근거를 보존한다. 근거 미확보를 점수만으로 완료 처리하거나 Judge 이유로 대체하지 않는다. 필요한 경우 사람이 확인한 설명을 지표 이름·작성자·출처와 함께 사람 검토의 `notes`에 남긴다.

## 4. 사람 검토와 요약

사람이 원문·질문·실제 답변을 대조해 10문항을 모두 검토한다. 문항별 빈 검토 양식을 만들고 내용을 직접 채운 뒤 가져온다.

```sh
.venv/bin/python main.py review-template "output/eval_runs/<eval_run_id>" Q01 /tmp/Q01-review.json
.venv/bin/python main.py import-review "output/eval_runs/<eval_run_id>" Q01 /tmp/Q01-review.json
.venv/bin/python main.py summarize "output/eval_runs/<eval_run_id>"
```

정확성·인용 적절성·답변 범위가 모두 `pass`일 때만 사람의 최종 판정을 통과로 계산한다. 사람 검토 이력은 추가하며 자동 결과를 수정하지 않는다. 요약 명령은 상세 JSON에서 `summary.json`과 문항별 `summary.csv`를 다시 만든다.

## 기록 해석

- SDK timeout은 요청당 120초, SDK 재시도는 2회다. 재시도를 포함한 물리 요청별 원문·usage·시간을 기록한다. 인증 헤더는 저장하지 않는다.
- 알 수 없는 비용을 0으로 만들지 않는다. 총비용 `null`, `cost_complete=false`와 확인된 소계를 구분한다. 기존 색인의 과거 비용과 재평가 시 이전 RAG 비용을 다시 합산하지 않는다.
- 시간은 단조 시계로 측정하며 파일 저장·색인 로딩·사람 검토 시간을 문항 처리 시간에서 제외한다.
- 현재 완료한 검증은 로컬·모의 검증이다. 실제 모델 접근 권한과 API 응답 호환성은 사용자가 정식 명령을 실행할 때 확인한다. 실제 점수나 사람 판정은 아직 없다.
