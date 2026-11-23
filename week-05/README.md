# 공개 API 기반 AI Agent 구현 과제

공개 API를 사용하는 단일 AI Agent를 만드세요. 모델이 API 응답을 보고 다음 행동을 고른 과정을 실행 기록으로 보여주세요.

## 1. 개념 조사

자신의 말로 답하고 궁금한 점은 질문으로 남겨주세요.

1. Workflow와 Agent에서는 각각 누가 다음 실행 경로를 정하나요?
2. Agent Loop에서 모델은 무엇을 선택하고, 실행 프로그램은 Tool을 어떻게 실행해 결과를 돌려주나요?
3. ReAct의 판단·행동·관찰은 본인의 구현에서 어디에 해당하나요?
4. 실행이 끝난 뒤 무엇을 근거로 목표 달성 여부를 판단하나요?

- [Stanford CME295 7강 영상 · Agentic LLMs](https://www.youtube.com/watch?v=h-7S6HNq0Vg)
- [Stanford CS329Z 3강 슬라이드 · RAG + Agents](https://web.stanford.edu/class/cs329z/slides/lecture03.pdf)
- [Anthropic · Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)

## 2. Agent 만들기

**언어·모델·프레임워크는 자유입니다.** 수업 예제처럼 OpenAI Agents SDK의 Agent Loop를 그대로 쓸 수 있습니다. 다른 프레임워크를 쓰거나 Loop를 직접 작성해도 됩니다.

1. 목표와 달성 기준을 정합니다. 도서 추천이라면 모델이 검색 결과에서 상세 조회할 책을 고르고 사용자 조건에 맞는 책을 추천합니다.
2. 공식 문서에서 인증·승인, 무료 범위와 호출 제한을 확인한 뒤 **공개 API를 직접 호출**합니다. 원하는 응답을 받으면 API 호출 함수를 Tool로 등록하고 용도와 입력을 적습니다. 인증키는 실행 프로그램에서만 사용합니다.
3. Instructions에 역할·목표·행동 범위를 적고 반복 한도를 설정합니다. 정보가 부족하면 확인하지 못한 조건을 알리고 종료합니다. 한도에 도달하면 목표 미달성으로 기록합니다.

기존 RAG를 추가 Tool로 연결하는 것은 선택입니다. AI 도구도 자유롭게 활용할 수 있습니다.

- [OpenAI Agents SDK · Tool 등록과 첫 실행](https://openai.github.io/openai-agents-python/ko/quickstart/) · [Tool 호출과 결과 확인](https://openai.github.io/openai-agents-python/ko/results/)
- [LangChain · `create_agent`로 Tool을 등록하고 실행하기](https://docs.langchain.com/oss/python/langchain/quickstart)
- 공개 API 목록 · [public-apis-4Kr](https://github.com/yybmion/public-apis-4Kr) · [public-apis](https://github.com/public-apis/public-apis) · [open-apis-korea](https://github.com/dl0312/open-apis-korea)

## 3. 실행과 판정

실제 모델과 공개 API로 세 유형을 **각각 1건 이상, 총 3건 이상** 실행합니다.

| 요청 유형 | 실행 기록에서 확인할 내용 |
|---|---|
| 목표를 달성할 수 있는 요청 | 모델이 API 응답을 보고 후속 Tool 호출과 입력을 선택해 목표에 맞는 결과를 냈는가? |
| API로 확인할 수 없는 조건이 있는 요청 | 어떤 조건을 확인했고 무엇을 확인하지 못했는지 최종 응답에 드러나는가? |
| 앞선 실행과 다른 경로를 택할 수 있는 요청 | 요청이나 응답에 따라 모델이 고른 Tool, 입력 또는 호출 순서가 어떻게 달라졌는가? |

실행마다 사용자 요청, **Tool 호출 순서·입력·결과**, 최종 결과, **종료 지점과 이유**, 모델 호출 수와 실행 시간을 남깁니다. SDK의 실행 기록을 활용해도 됩니다.
사람이 목표 달성 여부와 근거를 적습니다. 같은 요청을 고정 Workflow로 실행해 비교하는 것은 선택입니다.

## 4. 제출과 발표

`week-05/{github-id}/`에 다음 세 가지를 넣어 **PR 하나**로 제출합니다.

- **README.md**에 개념 질문의 답, 목표와 Instructions, API 공식 문서 링크, 설치·실행 방법과 환경변수 이름을 적습니다. 모델이 다음 행동을 고른 지점과 RAG 연결 여부·이유도 설명합니다.
- **실행 코드 또는 노트북**에는 공개 API Tool과 Agent를 실행하는 코드를 담습니다.
- **실행 기록**은 자유 형식입니다. 인증키와 개인정보는 제거하고 `.env` 파일은 제출에서 제외합니다.

외부 데이터를 변경하는 작업은 본인의 테스트 환경과 데이터로 한정합니다. 실제 결제·데이터 삭제·타인에게 메시지 보내기는 제외합니다.
다음 수업에서 **5분 이내**로 Workflow와 Agent의 차이를 설명하고, 대표 실행 한 건으로 모델의 선택과 목표 달성 판정을 보여주세요.

- [GitHub Fork와 PR 제출 가이드](https://github.com/bjc1102/ai-agent-repo2/blob/main/docs/submission-guide.md)
