"""파일 검증·저장과 실행 환경 기록을 위한 공통 기능."""

import hashlib
import importlib.metadata
import json
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from .config import BASE_DIR, DATASET_PATH, EXPECTED_VERSIONS
from .schemas import GoldenDataset


def now_iso() -> str:
    """한국 시간대가 포함된 현재 시각을 반환."""
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat()


def new_id(prefix: str) -> str:
    """기존 결과와 겹치지 않는 실행 식별자를 생성."""
    return f"{prefix}_{datetime.now(ZoneInfo('Asia/Seoul')):%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"


def sha256_file(path: Path) -> str:
    """파일의 원본 바이트 해시를 계산."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_hash(value: object) -> str:
    """JSON 구조의 고정 직렬화 해시를 계산."""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     allow_nan=False).encode()).hexdigest()


def write_json(path: Path, value: object) -> None:
    """비표준 숫자를 거부하고 같은 폴더에서 원자적으로 JSON을 저장."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(serialized, encoding="utf-8")
    temporary.replace(path)


def load_dataset(path: Path = DATASET_PATH) -> GoldenDataset:
    """골든 JSON의 타입·문항·참조와 원문 해시를 검증하여 반환."""
    dataset = GoldenDataset.model_validate_json(Path(path).read_text(encoding="utf-8"))
    for document in dataset.documents:
        source = Path(document.path)
        if not source.is_file():
            # 다른 기기에서도 파일명과 해시로 같은 원문을 찾습니다.
            source = BASE_DIR / "docs/01-document" / source.name
        if not source.is_file() or sha256_file(source) != document.sha256:
            raise ValueError(f"원문 파일 또는 SHA-256 불일치: {document.document_id}")
    return dataset


def environment_info() -> dict:
    """비밀 환경 변수 없이 코드 버전·작업 상태·설치 버전을 기록."""
    def git(*args: str) -> str:
        """읽기 전용 Git 정보만 조회."""
        result = subprocess.run(["git", *args], cwd=BASE_DIR, text=True,
                                capture_output=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else ""

    packages = {name: importlib.metadata.version(name) for name in EXPECTED_VERSIONS}
    return {"git_commit": git("rev-parse", "HEAD") or None,
            "git_dirty": bool(git("status", "--porcelain", "--", ".")),
            "python": platform.python_version(), "packages": packages}


def validate_versions() -> dict:
    """설치된 주요 패키지가 합의한 고정 버전인지 확인."""
    actual = environment_info()
    for package, version in EXPECTED_VERSIONS.items():
        if actual["packages"][package] != version:
            raise ValueError(f"{package} 버전 불일치: {version} 필요")
    return actual
