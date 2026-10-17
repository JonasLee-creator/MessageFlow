from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronoflow_model.config import load_config
from chronoflow_model.records import TaskRecord


def split_for_user(user_id: str) -> str:
    bucket = int.from_bytes(hashlib.sha256(user_id.encode("utf-8")).digest()[:4], "big") % 100
    return "train" if bucket < 70 else "validation" if bucket < 85 else "test"


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate JSONL and split by anonymous user ID without leakage.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "base.json")
    args = parser.parse_args()
    config = load_config(args.config)
    rows: dict[str, list[str]] = {"train": [], "validation": [], "test": []}
    users: dict[str, set[str]] = {name: set() for name in rows}
    with args.input.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            raw = json.loads(line)
            try:
                record = TaskRecord.from_dict(raw, config.features.user_state_dim, config.features.slot_feature_dim)
            except Exception as error:
                raise ValueError(f"invalid input line {line_number}: {error}") from error
            split = split_for_user(record.user_id)
            rows[split].append(json.dumps(raw, ensure_ascii=False))
            users[split].add(record.user_id)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, values in rows.items():
        (args.output / f"{name}.jsonl").write_text("\n".join(values) + ("\n" if values else ""), encoding="utf-8")
    if any(users[left] & users[right] for left, right in (("train", "validation"), ("train", "test"), ("validation", "test"))):
        raise RuntimeError("user leakage detected")
    print({name: {"records": len(rows[name]), "users": len(users[name])} for name in rows})


if __name__ == "__main__":
    main()

