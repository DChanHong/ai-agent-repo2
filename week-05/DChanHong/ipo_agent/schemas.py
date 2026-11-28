from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints


# SDK가 만드는 입력 스키마에서도 같은 제약을 사용합니다.
ReceiptNo = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9]{14}$")]
Question = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1),
]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidencePage(Schema):
    page: Annotated[int, Field(strict=True, ge=1)]
    # PDF 표의 들여쓰기와 줄바꿈은 보존하고, 빈 원문만 거부합니다.
    text: Annotated[str, Field(pattern=r"\S")]


class EvidenceFound(Schema):
    status: Literal["found"]
    company: str
    source_url: HttpUrl
    evidence: Annotated[list[EvidencePage], Field(min_length=1)]


class EvidenceNotFound(Schema):
    status: Literal["not_found"]
    reason: Literal["unregistered_filing", "no_evidence"]


class FilingEvidenceResult(Schema):
    receipt_no: ReceiptNo
    result: EvidenceFound | EvidenceNotFound
