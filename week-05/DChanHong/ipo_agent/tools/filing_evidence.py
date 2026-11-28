from functools import cache

import chromadb
from agents import function_tool
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from filing_index import COLLECTION_NAME, DB_DIR, EMBEDDING_MODEL, FILINGS, search
from ipo_agent.schemas import (
    EvidenceFound,
    EvidenceNotFound,
    FilingEvidenceResult,
    Question,
    ReceiptNo,
)


@cache
def get_collection():
    client = chromadb.PersistentClient(path=str(DB_DIR))
    return client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=OpenAIEmbeddingFunction(
            api_key_env_var="OPENAI_API_KEY",
            model_name=EMBEDDING_MODEL,
        ),
    )


@function_tool(output_type=FilingEvidenceResult)
def read_filing_evidence(receipt_no: ReceiptNo, question: Question) -> FilingEvidenceResult:
    """공시 한 건에서 질문에 관련된 원문, PDF 쪽 번호와 DART 링크를 찾습니다.

    Args:
        receipt_no: 조회할 공시의 14자리 DART 접수번호입니다.
        question: 해당 공시에서 확인하려는 항목이나 질문입니다.
    """
    for company, (_, registered_no) in FILINGS.items():
        if registered_no != receipt_no:
            continue
        pages = search(get_collection(), company, question)
        if pages:
            result = EvidenceFound(
                status="found", company=company,
                source_url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_no}",
                evidence=pages,
            )
        else:
            result = EvidenceNotFound(status="not_found", reason="no_evidence")
        return FilingEvidenceResult(receipt_no=receipt_no, result=result)

    return FilingEvidenceResult(
        receipt_no=receipt_no,
        result=EvidenceNotFound(status="not_found", reason="unregistered_filing"),
    )
