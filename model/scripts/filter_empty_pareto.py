from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path.name}:{line_number} is not a JSON object")
            rows.append(value)
    return rows


def write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def empty_decision_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {
        str(row["decision_id"])
        for row in rows
        if row.get("candidates")
        and all(not candidate.get("block_ids") for candidate in row["candidates"])
    }


def rebuild_checksums(dataset: Path) -> None:
    supported = {".jsonl", ".json", ".py", ".md", ".txt"}
    files = [
        path for path in dataset.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.txt" and path.suffix in supported
    ]
    content = "\n".join(f"{digest(path)}  {path.name}" for path in sorted(files)) + "\n"
    (dataset / "SHA256SUMS.txt").write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove Pareto decisions whose candidates all contain zero blocks."
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Write the filtered dataset")
    args = parser.parse_args()

    choices_path = args.dataset / "pareto_choices.jsonl"
    snapshots_path = args.dataset / "plan_snapshots.jsonl"
    splits_path = args.dataset / "splits.json"
    choices = read_jsonl(choices_path)
    snapshots = read_jsonl(snapshots_path)
    removed = empty_decision_ids(choices)
    filtered_choices = [row for row in choices if str(row.get("decision_id")) not in removed]
    filtered_snapshots = [row for row in snapshots if str(row.get("decision_id")) not in removed]

    snapshot_ids = {
        str(row.get("decision_id")) for row in snapshots if str(row.get("decision_id")) in removed
    }
    if snapshot_ids != removed:
        raise ValueError(
            f"choice/snapshot relation mismatch: choices={sorted(removed)}, snapshots={sorted(snapshot_ids)}"
        )

    summary = {
        "status": "READY" if removed else "NO_CHANGES",
        "apply": args.apply,
        "removed_decision_ids": sorted(removed),
        "pareto_choices": {"before": len(choices), "after": len(filtered_choices)},
        "plan_snapshots": {"before": len(snapshots), "after": len(filtered_snapshots)},
    }
    if args.apply and removed:
        write_jsonl_atomic(choices_path, filtered_choices)
        write_jsonl_atomic(snapshots_path, filtered_snapshots)
        splits = json.loads(splits_path.read_text(encoding="utf-8"))
        splits.setdefault("counts", {})["pareto_choices"] = len(filtered_choices)
        splits.setdefault("counts", {})["plan_snapshots"] = len(filtered_snapshots)
        splits.setdefault("qa", {})["pareto_empty_candidate_groups"] = 0
        splits_path.write_text(
            json.dumps(splits, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        rebuild_checksums(args.dataset)
        summary["status"] = "APPLIED"

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
