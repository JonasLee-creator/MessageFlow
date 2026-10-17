from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModelMetadata:
    model_version: str
    config_schema_version: int
    git_commit: str
    data_version: str
    validation_metrics: dict[str, float]
    input_names: tuple[str, ...] = (
        "hashed_text",
        "category_id",
        "course_id",
        "numeric_features",
        "user_state",
        "slot_features",
        "slot_user_state",
    )
    output_names: tuple[str, ...] = ("duration_parameters", "execution_logits")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_metadata(path: str | Path, metadata: ModelMetadata, artifacts: dict[str, str | Path]) -> None:
    payload: dict[str, Any] = asdict(metadata)
    payload["sha256"] = {name: sha256_file(file_path) for name, file_path in artifacts.items()}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

