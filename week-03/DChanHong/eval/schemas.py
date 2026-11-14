from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator, AwareDatetime


class StrictModel(BaseModel):
    """정의하지 않은 키를 거부하는 모든 저장 모델의 공통 기반."""

    model_config = ConfigDict(extra="forbid")


class Behavior(StrictModel):
    """Judge가 관찰한 실제 답변 방식과 판단 이유."""

    observed: Literal["answer", "abstain", "partial_answer", "unclear"]
    reason: str


class Assessment(StrictModel):
    """Judge의 한 평가 항목 판정과 실제 답변·근거 참조."""

    verdict: Literal["pass", "fail", "needs_review"]
    reason: str
    response_quotes: list[str]
    basis_refs: list[str]


class JudgeResult(StrictModel):
    """확정한 judge_result_v1 출력 키와 enum을 보존하는 API 모델."""

    behavior: Behavior
    accuracy: Assessment
    citation_appropriateness: Assessment
    answer_scope: Assessment

class GoldenDocument(StrictModel):
    """평가에 사용하는 원본 문서의 식별 정보와 파일 해시."""

    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GoldenCriterion(StrictModel):
    """문항의 정확성·인용·답변 범위를 판단하는 골든 기준."""

    criterion_id: str = Field(min_length=1)
    dimension: Literal[
        "accuracy",
        "citation_appropriateness",
        "answer_scope",
    ]
    kind: Literal["required", "forbidden", "allowed"]
    description: str = Field(min_length=1)
    source_refs: list[str]


class GoldenSource(StrictModel):
    """골든 답변의 근거가 되는 원문 발췌와 문서 내 위치."""

    source_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    pdf_page: int = Field(ge=1, strict=True)
    printed_page: str | None
    revision: Literal["before", "after"] | None
    section: str | None
    excerpt: str = Field(min_length=1)
    role: Literal["answer_evidence", "related_context"]

# 문자열·불리언·NaN·무한대를 제외한 정수와 실수.
Number = StrictInt | Annotated[
    float, Field(strict=True, allow_inf_nan=False)
]


class SourceLocation(StrictModel):
    """정보의 존재 여부를 확인한 문서 위치."""

    document_id: str = Field(min_length=1)
    pdf_page: int = Field(ge=1, strict=True)
    section: str | None


class AbsenceCheck(StrictModel):
    """답변 불가로 판단하기 전에 무엇을 어디서 확인했는지 기록."""

    target: str = Field(min_length=1)
    search_terms: list[str] = Field(min_length=1)
    reviewed_locations: list[SourceLocation] = Field(min_length=1)
    conclusion: str = Field(min_length=1)


class NumericRange(StrictModel):
    """희망 공모가처럼 최솟값과 최댓값이 있는 수치 범위."""

    min: Number
    max: Number

    @model_validator(mode="after")
    def validate_bounds(self) -> "NumericRange":
        """최솟값이 최댓값보다 큰 잘못된 범위를 거부."""
        if self.min > self.max:
            raise ValueError("min은 max보다 클 수 없습니다.")
        return self


class RuleExpectation(StrictModel):
    """수치·범위·계산·인용 라벨 검사에 사용할 기대 조건."""

    rule_id: str = Field(min_length=1)
    kind: Literal[
        "numeric", "numeric_range", "calculation", "citation_labels"
    ]
    target: str = Field(min_length=1)
    revision: Literal["before", "after"] | None
    period: str | None
    expected_value: Number | NumericRange | None
    unit: str | None = Field(min_length=1)
    formula: str | None = Field(min_length=1)
    rounding_digits: int | None = Field(ge=0, strict=True)
    tolerance: Annotated[Number, Field(ge=0)] | None

    @model_validator(mode="after")
    def validate_rule(self) -> "RuleExpectation":
        """규칙 종류와 기대값·계산식의 조합을 확인."""
        if self.kind in ("numeric", "calculation"):
            if not isinstance(self.expected_value, (int, float)):
                raise ValueError("수치·계산 규칙에는 숫자 기대값이 필요합니다.")

        elif self.kind == "numeric_range":
            if not isinstance(self.expected_value, NumericRange):
                raise ValueError("범위 규칙에는 min과 max가 필요합니다.")

        elif self.kind == "citation_labels":
            numeric_fields = (
                self.expected_value,
                self.unit,
                self.rounding_digits,
                self.tolerance,
            )
            if any(value is not None for value in numeric_fields):
                raise ValueError("인용 라벨 규칙의 수치 관련 필드는 null입니다.")

        if self.kind == "calculation":
            if self.formula is None:
                raise ValueError("계산 규칙에는 formula가 필요합니다.")
        elif self.formula is not None:
            raise ValueError("계산 규칙 외에는 formula를 null로 둡니다.")

        return self


class MetricPolicy(StrictModel):
    """한 평가 지표의 실행 여부·평가 범위·적용 이유."""

    mode: Literal["run", "conditional", "not_applicable"]
    scope: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class MetricPolicies(StrictModel):
    """문항별 Ragas 네 지표의 적용 정책."""

    context_precision: MetricPolicy
    context_recall: MetricPolicy
    faithfulness: MetricPolicy
    answer_relevancy: MetricPolicy

class GoldenQuestion(StrictModel):
    """평가 질문 하나의 정답·근거·규칙·지표 적용 정책."""

    question_id: str = Field(pattern=r"^Q(?:0[1-9]|10)$")
    topic: Literal["offering_price", "offering_terms", "fund_use"]
    question: str = Field(min_length=1)
    expected_answerability: Literal["answerable", "unanswerable", "partial"]
    golden_answer: str = Field(min_length=1)
    answerable_parts: list[Annotated[str, Field(min_length=1)]]
    unanswerable_parts: list[Annotated[str, Field(min_length=1)]]
    golden_criteria: list[GoldenCriterion]
    golden_sources: list[GoldenSource]
    absence_checks: list[AbsenceCheck]
    retrieval_reference: str | None = Field(min_length=1)
    rule_expectations: list[RuleExpectation]
    metric_policy: MetricPolicies

    @model_validator(mode="after")
    def validate_question_policy(self) -> "GoldenQuestion":
        """문항별 답변 가능 범위와 지표 정책이 합의 내용과 맞는지 확인."""
        number = int(self.question_id[1:])

        if number <= 6:
            expected = "answerable"
        elif number <= 8:
            expected = "unanswerable"
        else:
            expected = "partial"

        if self.expected_answerability != expected:
            raise ValueError(
                f"{self.question_id}의 expected_answerability는 {expected}입니다."
            )

        has_answerable_part = expected != "unanswerable"
        has_unanswerable_part = expected != "answerable"

        if bool(self.answerable_parts) != has_answerable_part:
            raise ValueError("문항 유형에 맞게 answerable_parts를 작성하세요.")

        if bool(self.unanswerable_parts) != has_unanswerable_part:
            raise ValueError("문항 유형에 맞게 unanswerable_parts를 작성하세요.")

        if bool(self.absence_checks) != has_unanswerable_part:
            raise ValueError("Q07~Q10에는 답변 불가 부분의 검토 기록이 필요합니다.")

        if (self.retrieval_reference is not None) != has_answerable_part:
            raise ValueError("retrieval_reference는 Q07·Q08에서만 null입니다.")

        retrieval_mode = "run" if has_answerable_part else "not_applicable"
        expected_modes = {
            "context_precision": retrieval_mode,
            "context_recall": retrieval_mode,
            "faithfulness": "conditional",
            "answer_relevancy": "run" if number <= 6 else "not_applicable",
        }

        for metric_name, expected_mode in expected_modes.items():
            policy = getattr(self.metric_policy, metric_name)
            if policy.mode != expected_mode:
                raise ValueError(
                    f"{self.question_id}의 {metric_name}.mode는 "
                    f"{expected_mode}입니다."
                )

        for items, key in (
            (self.golden_criteria, "criterion_id"),
            (self.golden_sources, "source_id"),
            (self.rule_expectations, "rule_id"),
        ):
            identifiers = [getattr(item, key) for item in items]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{self.question_id}의 {key}가 중복되었습니다.")
        source_ids = {source.source_id for source in self.golden_sources}
        if any(
            reference not in source_ids
            for criterion in self.golden_criteria
            for reference in criterion.source_refs
        ):
            raise ValueError("골든 기준이 존재하지 않는 G 근거를 참조합니다.")

        return self


class GoldenDataset(StrictModel):
    """원본 문서 정보와 확정한 평가 질문 10개를 묶은 데이터셋."""

    schema_version: Literal["golden_dataset_v1"]
    dataset_id: str = Field(min_length=1)
    created_at: AwareDatetime = Field(strict=True)
    documents: list[GoldenDocument] = Field(min_length=1)
    questions: list[GoldenQuestion] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def validate_question_ids(self) -> "GoldenDataset":
        """Q01부터 Q10까지 누락·중복 없이 포함됐는지 확인."""
        expected_ids = {f"Q{number:02d}" for number in range(1, 11)}
        actual_ids = {question.question_id for question in self.questions}

        if actual_ids != expected_ids:
            raise ValueError("Q01~Q10이 각각 한 번씩 있어야 합니다.")

        document_ids = [document.document_id for document in self.documents]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document_id가 중복되었습니다.")
        for question in self.questions:
            locations = list(question.golden_sources) + [
                location
                for check in question.absence_checks
                for location in check.reviewed_locations
            ]
            if any(location.document_id not in document_ids for location in locations):
                raise ValueError("근거가 존재하지 않는 문서를 참조합니다.")

        return self


# 정규화한 기록에는 유한 숫자·실제 bool·시간대가 있는 시각만 허용한다.
NonEmpty = Annotated[str, Field(min_length=1)]
NonNegative = Annotated[Number, Field(ge=0)]
Count = Annotated[int, Field(ge=0, strict=True)]
Position = Annotated[int, Field(ge=1, strict=True)]
Timestamp = Annotated[AwareDatetime, Field(strict=True)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
EvaluationStatus = Literal["pending", "completed", "not_applicable", "skipped", "error"]


class ErrorInfo(StrictModel):
    """실행 오류의 식별 코드와 사람이 읽을 수 있는 설명."""

    code: NonEmpty
    message: NonEmpty


class RetrievalHit(StrictModel):
    """반환 순서와 당시 원문 메타데이터를 보존하는 검색 청크."""

    label: NonEmpty
    chunk_id: NonEmpty
    returned_order: Position
    rank_in_revision: Position
    distance: Number
    metadata: dict[str, Any]
    text: str


class RetrievalResult(StrictModel):
    """질문 임베딩부터 검색 컨텍스트 구성까지의 결과."""

    execution_status: Literal["pending", "running", "completed", "skipped", "error"]
    results: list[RetrievalHit]
    elapsed_ms: NonNegative | None
    error: ErrorInfo | None

    @model_validator(mode="after")
    def validate_status(self) -> "RetrievalResult":
        """검색 오류·미실행 상태와 측정값의 조합을 확인."""
        _validate_stage(self.execution_status, self.error, self.elapsed_ms)
        return self


class GenerationResult(StrictModel):
    """실제로 보낸 생성 입력과 수신한 답변·원본 API 응답."""

    execution_status: Literal[
        "pending", "running", "completed", "needs_check", "skipped", "error"
    ]
    instructions: str | None
    input: str | None
    contexts: list[RetrievalHit]
    response: str | None
    api_response: dict[str, Any] | None
    elapsed_ms: NonNegative | None
    error: ErrorInfo | None

    @model_validator(mode="after")
    def validate_status(self) -> "GenerationResult":
        """빈 답변을 정상 완료로 저장하지 않고 원래 입력을 요구."""
        _validate_stage(self.execution_status, self.error, self.elapsed_ms)
        if self.execution_status == "completed":
            if self.response is None or not self.response.strip():
                raise ValueError("빈 생성 답변은 completed가 될 수 없습니다.")
            if self.instructions is None or self.input is None or self.api_response is None:
                raise ValueError("정상 생성 기록에는 실제 요청과 API 응답이 필요합니다.")
        return self


def _validate_stage(status: str, error: ErrorInfo | None, elapsed_ms: Number | None) -> None:
    """실행 단계 공통의 오류와 경과 시간 상태 규칙을 확인."""
    if (status == "error") != (error is not None):
        raise ValueError("error 상태에서만 오류 객체가 필요합니다.")
    if status in ("pending", "running") and elapsed_ms is not None:
        raise ValueError("미완료 단계의 경과 시간은 null입니다.")
    if status in ("not_applicable", "skipped") and elapsed_ms != 0:
        raise ValueError("실행하지 않은 확정 단계의 경과 시간은 0입니다.")


class RagRecord(StrictModel):
    """한 질문의 검색·실제 생성 요청·답변과 호출 기록."""

    schema_version: Literal["rag_record_v1"]
    rag_run_id: NonEmpty
    question_id: Annotated[str, Field(pattern=r"^Q(?:0[1-9]|10)$")]
    question: NonEmpty
    execution_status: Literal["pending", "running", "completed", "needs_check", "error"]
    stage: NonEmpty
    retrieval: RetrievalResult
    generation: GenerationResult
    api_calls: list[dict[str, Any]]
    started_at: Timestamp | None
    finished_at: Timestamp | None
    elapsed_ms: NonNegative | None

    @model_validator(mode="after")
    def validate_record(self) -> "RagRecord":
        """종료 시각·완료 상태와 반환 순서의 일관성을 확인."""
        if self.execution_status == "pending":
            if any(value is not None for value in (self.started_at, self.finished_at, self.elapsed_ms)):
                raise ValueError("실행 전 시간 필드는 모두 null입니다.")
        elif self.execution_status == "running":
            if self.started_at is None or self.finished_at is not None or self.elapsed_ms is not None:
                raise ValueError("실행 중에는 시작 시각만 존재해야 합니다.")
        elif self.started_at is None or self.finished_at is None:
            raise ValueError("종료 기록에는 시작·종료 시각이 필요합니다.")
        if self.started_at is not None and self.finished_at is not None:
            if self.finished_at < self.started_at:
                raise ValueError("종료 시각은 시작 시각보다 빠를 수 없습니다.")
        if self.execution_status == "completed" and (
            self.retrieval.execution_status != "completed"
            or self.generation.execution_status != "completed"
        ):
            raise ValueError("RAG 정상 완료에는 검색·생성 완료가 필요합니다.")
        for hits in (self.retrieval.results, self.generation.contexts):
            if [hit.returned_order for hit in hits] != list(range(1, len(hits) + 1)):
                raise ValueError("검색 결과 순위는 실제 반환 순서대로 1부터 이어져야 합니다.")
            if len({hit.label for hit in hits}) != len(hits):
                raise ValueError("한 컨텍스트 목록의 E 라벨은 중복될 수 없습니다.")
        return self


class MetricResult(StrictModel):
    """한 Ragas 지표의 실제 입력·점수·상세 근거·적용 상태."""

    evaluation_status: EvaluationStatus
    score: Annotated[Number, Field(ge=-1, le=1)] | None
    reason_code: NonEmpty | None
    reason: NonEmpty | None
    inputs: dict[str, Any] | None
    details: dict[str, Any] | None
    call_ids: list[NonEmpty]
    elapsed_ms: NonNegative | None
    error: ErrorInfo | None

    @model_validator(mode="after")
    def validate_result(self) -> "MetricResult":
        """적용 불가·오류를 점수로 치환하지 못하도록 검증."""
        _validate_stage(self.evaluation_status, self.error, self.elapsed_ms)
        if self.evaluation_status == "completed":
            if self.score is None or self.inputs is None:
                raise ValueError("완료한 지표에는 점수와 실제 입력이 필요합니다.")
        elif self.score is not None:
            raise ValueError("미완료 지표의 점수는 null입니다.")
        if self.evaluation_status in ("not_applicable", "skipped", "error"):
            if self.reason_code is None or self.reason is None:
                raise ValueError("적용 불가·건너뜀·오류에는 사유가 필요합니다.")
        return self


class RagasResults(StrictModel):
    """적용 여부에 관계없이 네 지표를 모두 포함하는 결과 묶음."""

    context_precision: MetricResult
    context_recall: MetricResult
    faithfulness: MetricResult
    answer_relevancy: MetricResult

    @model_validator(mode="after")
    def validate_score_ranges(self) -> "RagasResults":
        """코사인 지표 이외의 점수는 0부터 1까지로 검증."""
        for metric in (self.context_precision, self.context_recall, self.faithfulness):
            if metric.score is not None and metric.score < 0:
                raise ValueError("검색 지표와 Faithfulness는 음수일 수 없습니다.")
        return self


class RuleResult(StrictModel):
    """기계적으로 확정 가능한 규칙의 기대값·관찰값·판정."""

    rule_id: NonEmpty
    evaluation_status: EvaluationStatus
    verdict: Literal["pass", "fail", "undetermined"] | None
    expected: RuleExpectation
    observed: Any | None
    response_quotes: list[str]
    reason: NonEmpty | None
    error: ErrorInfo | None

    @model_validator(mode="after")
    def validate_result(self) -> "RuleResult":
        """추출 불확실성과 실행 오류를 서로 구분해 저장."""
        if (self.evaluation_status == "error") != (self.error is not None):
            raise ValueError("규칙의 error 상태에만 오류 객체가 필요합니다.")
        if (self.evaluation_status == "completed") != (self.verdict is not None):
            raise ValueError("완료한 규칙에만 판정이 존재해야 합니다.")
        if self.evaluation_status != "pending" and self.reason is None:
            raise ValueError("검사한 규칙에는 판단 또는 미실행 이유가 필요합니다.")
        if self.rule_id != self.expected.rule_id:
            raise ValueError("규칙 결과와 기대 조건의 ID가 다릅니다.")
        return self


class JudgeEvaluation(StrictModel):
    """Judge의 원래 출력과 출력 검증 후 확정한 결과."""

    evaluation_status: EvaluationStatus
    result: JudgeResult | None
    raw_response: str | None
    call_ids: list[NonEmpty]
    elapsed_ms: NonNegative | None
    error: ErrorInfo | None

    @model_validator(mode="after")
    def validate_result(self) -> "JudgeEvaluation":
        """출력 오류를 품질 실패로 바꾸지 않고 원문을 보존."""
        _validate_stage(self.evaluation_status, self.error, self.elapsed_ms)
        if (self.evaluation_status == "completed") != (self.result is not None):
            raise ValueError("완료된 Judge에만 검증한 result가 존재합니다.")
        if self.evaluation_status == "completed" and self.raw_response is None:
            raise ValueError("Judge 완료 기록에는 원래 출력 문자열이 필요합니다.")
        return self


class HumanAssessment(StrictModel):
    """사람이 원문과 답변을 대조한 한 항목의 완료 판정."""

    verdict: Literal["pass", "fail"]
    reason: NonEmpty
    basis_refs: list[NonEmpty]


class SourceCheck(StrictModel):
    """사람이 직접 대조한 문서 페이지와 해당 구절."""

    document_id: NonEmpty
    pdf_page: Position
    excerpt: NonEmpty


class Disagreement(StrictModel):
    """자동 평가와 사람 판정이 다른 항목의 비교와 이유."""

    component: NonEmpty
    item: NonEmpty
    automatic_value: Any
    human_value: Any
    reason: NonEmpty


class HumanReview(StrictModel):
    """덮어쓰지 않고 누적하는 한 번의 완료된 사람 검토."""

    review_id: NonEmpty
    reviewer: NonEmpty
    reviewed_at: Timestamp
    accuracy: HumanAssessment
    citation_appropriateness: HumanAssessment
    answer_scope: HumanAssessment
    source_checks: list[SourceCheck] = Field(min_length=1)
    disagreements: list[Disagreement]
    notes: str


class DerivedResult(StrictModel):
    """자동·사람 판정 및 중복 없이 합산한 비용·시간 요약."""

    behavior_matches_expected: StrictBool | None
    judge_overall: Literal["pass", "fail", "needs_review"] | None
    rule_counts: dict[str, Count]
    latest_human_review_id: NonEmpty | None
    human_final: Literal["pass", "fail"] | None
    disagreement_summary: str
    rag_cost_usd: NonNegative | None
    rag_known_cost_usd: NonNegative
    rag_cost_complete: StrictBool
    rag_elapsed_ms: NonNegative | None
    eval_cost_usd: NonNegative | None
    eval_known_cost_usd: NonNegative
    eval_cost_complete: StrictBool
    eval_elapsed_ms: NonNegative | None
    performed_metric_count: Count

    @model_validator(mode="after")
    def validate_completeness(self) -> "DerivedResult":
        """미확보 비용을 0으로 채우거나 사람 판정을 미리 만들지 못하게 검증."""
        for prefix in ("rag", "eval"):
            complete = getattr(self, f"{prefix}_cost_complete")
            total = getattr(self, f"{prefix}_cost_usd")
            known = getattr(self, f"{prefix}_known_cost_usd")
            if complete != (total is not None):
                raise ValueError("비용 집계가 불완전하면 총비용은 null이어야 합니다.")
            if total is not None and abs(total - known) > 1e-12:
                raise ValueError("완전한 총비용과 확인된 비용 합계가 다릅니다.")
        if (self.latest_human_review_id is None) != (self.human_final is None):
            raise ValueError("사람 최종 판정과 최신 검토 ID는 함께 존재해야 합니다.")
        return self


class EvaluationRecord(StrictModel):
    """하나의 고정 RAG 답변에 대한 골든·자동 평가·사람 검토 전체."""

    schema_version: Literal["evaluation_record_v1"]
    eval_run_id: NonEmpty
    rag_run_id: NonEmpty
    question_id: Annotated[str, Field(pattern=r"^Q(?:0[1-9]|10)$")]
    golden: GoldenQuestion
    rag: RagRecord
    ragas: RagasResults
    rules: list[RuleResult]
    judge: JudgeEvaluation
    human_reviews: list[HumanReview]
    api_calls: list[dict[str, Any]]
    derived: DerivedResult

    @model_validator(mode="after")
    def validate_references(self) -> "EvaluationRecord":
        """복사본의 질문·실행 ID와 검토 이력 참조를 확인."""
        if self.rag_run_id != self.rag.rag_run_id:
            raise ValueError("평가와 RAG 복사본의 실행 ID가 다릅니다.")
        if self.question_id != self.golden.question_id or self.question_id != self.rag.question_id:
            raise ValueError("평가·골든·RAG의 문항 ID가 다릅니다.")
        if self.golden.question != self.rag.question:
            raise ValueError("골든과 RAG에 기록한 실제 질문이 다릅니다.")
        review_ids = [review.review_id for review in self.human_reviews]
        if len(review_ids) != len(set(review_ids)):
            raise ValueError("사람 검토 이력 ID가 중복되었습니다.")
        if self.human_reviews:
            latest = self.human_reviews[-1]
            if self.derived.latest_human_review_id != latest.review_id:
                raise ValueError("최신 사람 검토 ID는 마지막 추가 이력을 가리켜야 합니다.")
            final = "pass" if all(
                getattr(latest, dimension).verdict == "pass"
                for dimension in ("accuracy", "citation_appropriateness", "answer_scope")
            ) else "fail"
            if self.derived.human_final != final:
                raise ValueError("사람 최종 판정은 세 항목이 모두 통과할 때만 pass입니다.")
        elif self.derived.latest_human_review_id is not None:
            raise ValueError("미검토 문항에는 사람 판정이 존재할 수 없습니다.")
        return self


class FileRef(StrictModel):
    """입력 파일의 당시 위치와 내용 해시."""

    path: NonEmpty
    sha256: Sha256


class DatasetRef(FileRef):
    """사용한 골든 파일과 논리 데이터셋 식별자."""

    dataset_id: NonEmpty


class CodeInfo(StrictModel):
    """실제 실행 코드와 Python·패키지 환경의 식별 정보."""

    git_commit: NonEmpty | None
    git_dirty: StrictBool
    python: NonEmpty
    packages: dict[NonEmpty, NonEmpty]


class ChunkingConfig(FileRef):
    """기존 청크 파일과 크기·중첩·분할 방식."""

    max_chars: Position
    overlap_chars: Count
    split_strategy: NonEmpty


class RetrievalConfig(StrictModel):
    """정정 구분별 개수와 결합 순서를 포함한 검색 설정."""

    collection: NonEmpty
    distance_metric: Literal["cosine"]
    top_k_per_revision: Position
    revision_order: list[Literal["before", "after"]]
    index_path: NonEmpty


class ModelConfig(StrictModel):
    """모델의 고정 이름과 실제 요청에 쓰는 설정 원본."""

    model: NonEmpty
    settings: dict[str, Any]


class RagModels(StrictModel):
    """검색 임베딩과 답변 생성 모델을 구분한 설정."""

    embedding: ModelConfig
    generation: ModelConfig


class EvaluationModels(StrictModel):
    """Ragas·평가 임베딩·별도 Judge 모델의 설정."""

    ragas_llm: ModelConfig
    embedding: ModelConfig
    judge: ModelConfig


class PromptSnapshot(StrictModel):
    """실행 당시 프롬프트 전문과 버전·해시."""

    version: NonEmpty
    text: NonEmpty
    sha256: Sha256


class SchemaSnapshot(StrictModel):
    """API에 사용한 출력 스키마와 그 내용 해시."""

    version: NonEmpty
    json_schema: dict[str, Any]
    sha256: Sha256


class PriceRate(StrictModel):
    """100만 토큰 기준 USD 단가이며 비적용 항목은 null."""

    input: NonNegative
    cached_input: NonNegative | None
    output: NonNegative | None
    source: NonEmpty


class PricingSnapshot(StrictModel):
    """비용 계산에 사용한 단가의 확인 시각·출처·모델별 값."""

    checked_at: Timestamp
    currency: Literal["USD"]
    unit: Literal["per_million_tokens"]
    conditions: NonEmpty
    models: dict[NonEmpty, PriceRate]


class RagManifest(StrictModel):
    """한 RAG 실행의 입력·검색·생성 설정과 환경 기록."""

    schema_version: Literal["rag_manifest_v1"]
    rag_run_id: NonEmpty
    dataset: DatasetRef
    question_ids: list[Annotated[str, Field(pattern=r"^Q(?:0[1-9]|10)$")]]
    started_at: Timestamp
    finished_at: Timestamp | None
    code: CodeInfo
    documents: list[GoldenDocument]
    chunking: ChunkingConfig
    retrieval: RetrievalConfig
    models: RagModels
    prompt: PromptSnapshot
    pricing: PricingSnapshot

    @model_validator(mode="after")
    def validate_manifest(self) -> "RagManifest":
        """실행 목록의 중복과 시간 역전을 검증."""
        if len(self.question_ids) != len(set(self.question_ids)) or not self.question_ids:
            raise ValueError("실행 질문 목록은 비어 있거나 중복될 수 없습니다.")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("실행 종료 시각이 시작 시각보다 빠릅니다.")
        return self


class EvaluationSettings(StrictModel):
    """프레임워크·규칙 버전과 지표에 실제 넘기는 설정."""

    ragas_version: NonEmpty
    metric_settings: dict[str, Any]
    rules_version: NonEmpty


class EvaluationManifest(StrictModel):
    """저장된 RAG 답변에 적용한 평가 환경·기준의 실행 기록."""

    schema_version: Literal["evaluation_manifest_v1"]
    eval_run_id: NonEmpty
    rag_run_id: NonEmpty
    started_at: Timestamp
    finished_at: Timestamp | None
    code: CodeInfo
    dataset: DatasetRef
    rag_inputs: list[FileRef]
    settings: EvaluationSettings
    models: EvaluationModels
    judge_prompt: PromptSnapshot
    judge_schema: SchemaSnapshot
    pricing: PricingSnapshot

    @model_validator(mode="after")
    def validate_manifest(self) -> "EvaluationManifest":
        """평가 실행의 시작·종료 시각 순서를 확인."""
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("평가 종료 시각이 시작 시각보다 빠릅니다.")
        return self
