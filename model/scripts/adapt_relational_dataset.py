from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronoflow_model.config import load_config
from chronoflow_model.records import TaskRecord
from chronoflow_model.relational_adapter import adapt_dataset, write_adapted


def main() -> None:
    parser = argparse.ArgumentParser(description="Join the normalized DRP tables into leakage-safe training JSONL.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "base.json")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if not args.check_only and args.output is None:
        parser.error("--output is required unless --check-only is used")
    config = load_config(args.config)
    try:
        splits, manifest = adapt_dataset(args.dataset)
    except ValueError as error:
        print(json.dumps({
            "status": "FAIL",
            "adapted_data_written": False,
            "reason": str(error),
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1) from None
    validated = 0
    for rows in splits.values():
        for row in rows:
            TaskRecord.from_dict(row, config.features.user_state_dim, config.features.slot_feature_dim)
            validated += 1
    manifest["validated_records"] = validated
    if not args.check_only:
        write_adapted(args.output, splits, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

