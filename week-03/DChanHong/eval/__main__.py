"""검증·생성·평가·사람 검토를 각각 실행하는 명령 진입점."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .common import load_dataset, sha256_file, validate_versions
from .config import BASE_DIR, CHUNKS_PATH, GENERATION_PROMPT_PATH, JUDGE_PROMPT_PATH


def validate() -> None:
    """키·API 없이 데이터·색인·프롬프트·모듈의 준비 상태를 검증."""
    from .index import validate_index
    from .metrics import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness
    from .schemas import JudgeResult

    dataset = load_dataset()
    environment = validate_versions()
    collection = validate_index()
    provenance = json.loads((BASE_DIR / "eval/data/baseline.json").read_text(encoding="utf-8"))
    for key in ("chunks", "sections", "generation_prompt"):
        asset = provenance[key]
        if sha256_file(BASE_DIR / asset["path"]) != asset["sha256"]:
            raise ValueError(f"2주차 기준 자료와 해시가 다릅니다: {key}")
    if not GENERATION_PROMPT_PATH.read_text(encoding="utf-8").strip():
        raise ValueError("생성 프롬프트가 비어 있습니다.")
    if not JUDGE_PROMPT_PATH.read_text(encoding="utf-8").strip():
        raise ValueError("Judge 프롬프트가 비어 있습니다.")
    specification = (BASE_DIR / "docs/00-plan/EVALUATION_SPEC.md").read_text(encoding="utf-8")
    expected_judge = specification.split("### 6.2", 1)[1].split("```text\n", 1)[1].split("```", 1)[0].strip()
    if JUDGE_PROMPT_PATH.read_text(encoding="utf-8").strip() != expected_judge:
        raise ValueError("Judge 프롬프트가 확정 문서와 다릅니다.")
    JudgeResult.model_json_schema()
    print(json.dumps({"validation": "passed", "questions": len(dataset.questions),
        "indexed_chunks": collection.count(), "chunks_sha256": sha256_file(CHUNKS_PATH),
        "generation_prompt_sha256": sha256_file(GENERATION_PROMPT_PATH),
        "judge_prompt_sha256": sha256_file(JUDGE_PROMPT_PATH),
        "python": environment["python"], "packages": environment["packages"],
        "ragas_metrics": [m.__name__ for m in (ContextPrecision, ContextRecall, Faithfulness, AnswerRelevancy)],
        "api_calls": 0, "credentials_checked": False}, ensure_ascii=False, indent=2))


def main() -> int:
    """사용자가 선택한 단계만 실행하고 다음 단계로 자동 진행하지 않음."""
    parser = argparse.ArgumentParser(description="동원파츠 RAG 10문항 실행·평가")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate", help="API 호출 없는 준비 상태 검증")
    prepare = commands.add_parser("prepare-index", help="기존 색인 복사·검증 (API 없음)")
    prepare.add_argument("--source", type=Path)
    generate = commands.add_parser("generate", help="10개 질문의 응답 생성 (유료 API)")
    generate.add_argument("--output-dir", type=Path)
    evaluate = commands.add_parser("evaluate", help="저장한 10개 응답 평가 (유료 API)")
    evaluate.add_argument("rag_run_dir", type=Path)
    evaluate.add_argument("--output-dir", type=Path)
    summary = commands.add_parser("summarize", help="상세 JSON으로 요약 재생성")
    summary.add_argument("eval_run_dir", type=Path)
    for command in ("review-template", "import-review"):
        review = commands.add_parser(command, help="사람 검토 양식 생성" if command == "review-template" else "완료된 사람 검토 이력 추가")
        review.add_argument("eval_run_dir", type=Path)
        review.add_argument("question_id", choices=[f"Q{n:02d}" for n in range(1, 11)])
        review.add_argument("review_file", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            validate()
        elif args.command == "prepare-index":
            from .index import prepare_index
            print(prepare_index(args.source))
        elif args.command == "generate":
            from .rag import run_generation
            path = run_generation(args.output_dir)
            print(path)
            records = [json.loads(p.read_text(encoding="utf-8")) for p in path.glob("Q*.json")]
            return 0 if len(records) == 10 and all(r["execution_status"] == "completed" for r in records) else 1
        elif args.command == "evaluate":
            from .evaluate import run_evaluation
            path = asyncio.run(run_evaluation(args.rag_run_dir, args.output_dir))
            print(path)
            records = [json.loads(p.read_text(encoding="utf-8")) for p in path.glob("Q*.json")]
            return 0 if all(r["judge"]["evaluation_status"] == "completed" and all(m["evaluation_status"] in ("completed", "not_applicable") for m in r["ragas"].values()) for r in records) else 1
        else:
            from .report import import_review, review_template, summarize
            if args.command == "summarize":
                print(summarize(args.eval_run_dir))
            elif args.command == "review-template":
                print(review_template(args.eval_run_dir, args.question_id, args.review_file))
            elif args.command == "import-review":
                print(import_review(args.eval_run_dir, args.question_id, args.review_file))
        return 0
    except (OSError, ValueError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
