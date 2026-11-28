from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, computed_field


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


class IpoFirstDayPerformance(Schema):
    company: str
    stock_code: str
    market: Literal["KOSPI", "KOSDAQ"]
    listing_date: date
    offer_price: Annotated[int, Field(gt=0)]
    open_price: Annotated[int, Field(gt=0)]
    close_price: Annotated[int, Field(gt=0)]

    @computed_field
    @property
    def offer_to_open_pct(self) -> float:
        """공모가 대비 상장일 시가 등락률입니다."""
        return round((self.open_price / self.offer_price - 1) * 100, 2)

    @computed_field
    @property
    def open_to_close_pct(self) -> float:
        """상장일 시가 대비 종가 등락률입니다."""
        return round((self.close_price / self.open_price - 1) * 100, 2)


class FilingReference(Schema):
    receipt_no: ReceiptNo
    report_name: str
    filed_on: date


class SubscriptionCandidate(Schema):
    company: str
    stock_code: str
    opens_on: date
    closes_on: date
    filing: FilingReference | None


class SubscriptionCandidates(Schema):
    start: date
    end: date
    candidates: list[SubscriptionCandidate]
    analysis_companies: list[str]
    first_closing_only: bool = False
    issues: list[str]


class RecentIpoPerformance(Schema):
    as_of: datetime
    calendar_from: date
    items: list[IpoFirstDayPerformance]
    issues: list[str]
