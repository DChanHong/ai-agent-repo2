import argparse
import re
from itertools import batched
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from pypdf import PdfReader
from transformers import AutoTokenizer

from ipo_agent.schemas import EvidencePage

PDF_DIR = Path.home() / "Desktop" / "증권신고자료"
DB_DIR = Path(__file__).resolve().parent / ".cache" / "chroma"
COLLECTION_NAME = "ipo_filings_openai_small"
EMBEDDING_MODEL = "text-embedding-3-small"
# 이전 색인과 같은 텍스트 구간을 사용해 검색 결과를 비교합니다.
CHUNK_TOKENIZER = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# PDF 파일명과 DART 접수번호를 한 쌍으로 관리합니다.
FILINGS = {
    "동원파츠": ("[동원파츠][정정]증권신고서(지분증권)(2026.10.30) (1).pdf", "20261030000113"),
    "바로팜": ("[바로팜][정정]증권신고서(지분증권)(2026.10.30).pdf", "20261030000396"),
    "넥스아이": ("[넥스아이][정정]증권신고서(지분증권)(2026.10.30).pdf", "20261030000467"),
}


def split_page(text, tokenizer):
    # 빈 줄로 나눈 문단을 우선 사용합니다. 긴 문단·표는 겹치게 잘라
    # 모델 입력 길이를 넘는 뒷부분도 검색할 수 있게 합니다.
    for block in re.split(r"\n[ \t]*\n", text):
        block = block.strip()
        if not block:
            continue

        offsets = tokenizer(
            block,
            add_special_tokens=False,
            return_offsets_mapping=True,
            verbose=False,
        )["offset_mapping"]

        start = 0
        while start < len(offsets):
            end = min(start + 100, len(offsets))
            yield block[offsets[start][0]:offsets[end - 1][1]]
            if end == len(offsets):
                break
            start = end - 20


def filing_records(path, receipt_no, company, tokenizer):
    reader = PdfReader(path)
    for page_no, page in enumerate(reader.pages, start=1):
        text = page.extract_text(extraction_mode="layout") or ""
        for part, chunk in enumerate(split_page(text, tokenizer), start=1):
            record_id = f"{receipt_no}-{page_no}-{part}"
            metadata = {
                "company": company,
                "receipt_no": receipt_no,
                "page": page_no,
            }
            yield record_id, chunk, metadata


def build(collection):
    tokenizer = AutoTokenizer.from_pretrained(CHUNK_TOKENIZER)
    for company, (filename, receipt_no) in FILINGS.items():
        path = PDF_DIR / filename
        records = filing_records(path, receipt_no, company, tokenizer)
        existing = collection.get(where={"receipt_no": receipt_no}, include=["documents"])
        saved = dict(zip(existing["ids"], existing["documents"]))
        count = 0
        updated = 0

        for batch in batched(records, 64):
            count += len(batch)
            pending = [record for record in batch if saved.get(record[0]) != record[1]]
            if not pending:
                continue
            ids, documents, metadata = zip(*pending)
            collection.upsert(
                ids=list(ids),
                documents=list(documents),
                metadatas=list(metadata),
            )
            updated += len(pending)

        if count == 0:
            raise ValueError(f"{filename}에서 색인할 텍스트를 추출하지 못했습니다.")
        print(f"{company} | 전체 {count}개 구간 | 이번 실행에서 {updated}개 저장")


def search(collection, company: str, question: str) -> list[EvidencePage]:
    filename, receipt_no = FILINGS[company]
    sections = []
    if "확약" in question and "신청" in question:
        hits = collection.get(
            where={"receipt_no": receipt_no},
            where_document={"$contains": "확약기간별 수요예측 참여내역"},
            include=["metadatas"],
        )
        title_pages = {item["page"] for item in hits["metadatas"]}
        if title_pages:
            reader = PdfReader(PDF_DIR / filename)
            pages = title_pages | {
                page + 1 for page in title_pages if page < len(reader.pages)
            }
            for page in sorted(pages):
                text = reader.pages[page - 1].extract_text(extraction_mode="layout")
                if text and text.strip():
                    sections.append(EvidencePage(page=page, text=text))

    if not sections:
        result = collection.query(
            query_texts=[question],
            where={"receipt_no": receipt_no},
            n_results=5,
            include=["documents", "metadatas"],
        )
        for text, metadata in zip(result["documents"][0], result["metadatas"][0]):
            if text and text.strip():
                sections.append(EvidencePage(page=metadata["page"], text=text))

    return sections


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build")
    query = commands.add_parser("search")
    query.add_argument("company", choices=FILINGS)
    query.add_argument("question")
    args = parser.parse_args()

    client = chromadb.PersistentClient(path=str(DB_DIR))
    embedding_function = OpenAIEmbeddingFunction(
        api_key_env_var="OPENAI_API_KEY", model_name=EMBEDDING_MODEL
    )

    if args.command == "build":
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME, embedding_function=embedding_function
        )
        build(collection)
    else:
        collection = client.get_collection(
            name=COLLECTION_NAME, embedding_function=embedding_function
        )
        evidence = search(collection, args.company, args.question)
        if not evidence:
            print(f"{args.company} 공시에서 검색 결과를 찾지 못했습니다.")
        for item in evidence:
            print(f"\n[{args.company} | PDF {item.page}쪽]\n{item.text}")
        _, receipt_no = FILINGS[args.company]
        print(f"\nDART 원문: https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_no}")
