from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable


CATEGORY_MAP = {
    "实验": "EXPERIMENT",
    "报告": "REPORT",
    "编程": "PROGRAMMING",
    "复习": "REVIEW",
    "背诵": "MEMORIZATION",
    "阅读": "READING",
    "考试准备": "EXAM_PREPARATION",
    "其他": "OTHER",
}
TIME_BUCKETS = {"morning": 0, "afternoon": 1, "evening": 2, "night": 3}
QUANTILES = {"p50": 0.50, "p65": 0.65, "p80": 0.80, "p95": 0.95}

USER_STATE_ORDER = (
    "recent_7_day_completion_rate",
    "completed_blocks",
    "skipped_blocks",
    "delayed_blocks",
    "actual_to_planned_ratio",
    "actual_work_minutes",
    "planned_work_minutes",
    "task_backlog",
    "overdue_task_count",
    "average_estimation_error",
    "average_start_delay",
    "consecutive_work_minutes",
)

SLOT_FEATURE_ORDER = (
    "is_morning",
    "is_afternoon",
    "is_evening",
    "is_night",
    "weekday_sin",
    "weekday_cos",
    "planned_duration",
    "daily_workload_before",
    "continuous_work_before",
    "deadline_distance",
    "task_release_age",
    "duration_quantile",
)


def parse_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp has no timezone: {value}")
    return parsed


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


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def encode_user_day(row: dict[str, Any] | None) -> list[float]:
    """Fixed, documented scaling. Missing history is the zero-vector cold-start state."""
    if row is None:
        return [0.0] * len(USER_STATE_ORDER)
    planned = float(row.get("planned_work_minutes") or 0.0)
    actual = float(row.get("actual_work_minutes") or 0.0)
    estimation_error = float(row.get("average_estimation_error") or 0.0)
    return [
        clamp(float(row.get("recent_7_day_completion_rate") or 0.0)),
        clamp(float(row.get("completed_blocks") or 0.0) / 10.0),
        clamp(float(row.get("skipped_blocks") or 0.0) / 5.0),
        clamp(float(row.get("delayed_blocks") or 0.0) / 5.0),
        clamp((actual / planned if planned > 0 else 0.0) / 2.0),
        clamp(actual / 600.0),
        clamp(planned / 720.0),
        clamp(float(row.get("task_backlog") or 0.0) / 10.0),
        clamp(float(row.get("overdue_task_count") or 0.0) / 5.0),
        math.tanh(estimation_error),
        clamp(float(row.get("average_start_delay") or 0.0) / 2880.0),
        clamp(float(row.get("consecutive_work_minutes") or 0.0) / 240.0),
    ]


class CausalUserHistory:
    def __init__(self, rows: Iterable[dict[str, Any]]) -> None:
        self.rows: dict[str, list[tuple[date, dict[str, Any]]]] = defaultdict(list)
        for row in rows:
            self.rows[str(row["anonymous_user_id"])].append((date.fromisoformat(str(row["date"])), row))
        for values in self.rows.values():
            values.sort(key=lambda item: item[0])

    def state_before(self, user_id: str, instant: datetime) -> list[float]:
        target_date = instant.date()
        previous: dict[str, Any] | None = None
        for row_date, row in self.rows.get(user_id, []):
            if row_date >= target_date:
                break
            previous = row
        return encode_user_day(previous)


def encode_slot(row: dict[str, Any]) -> list[float]:
    start = parse_instant(str(row["planned_start"]))
    end = parse_instant(str(row["planned_end"]))
    if end <= start:
        raise ValueError(f"block {row.get('block_id')} has invalid planned interval")
    bucket_name = str(row["time_bucket"])
    bucket = TIME_BUCKETS.get(bucket_name)
    if bucket is None:
        raise ValueError(f"unsupported time bucket: {bucket_name}")
    one_hot = [1.0 if index == bucket else 0.0 for index in range(4)]
    weekday_angle = 2.0 * math.pi * start.weekday() / 7.0
    duration = (end - start).total_seconds() / 60.0
    quantile = QUANTILES.get(str(row.get("predicted_duration_quantile")))
    if quantile is None:
        raise ValueError(f"unsupported predicted duration quantile: {row.get('predicted_duration_quantile')}")
    deadline_distance = row.get("deadline_distance_minutes")
    # A missing deadline means "no deadline pressure", not "deadline is now".
    deadline_feature = 1.0 if deadline_distance is None else clamp(
        float(deadline_distance) / (14.0 * 24.0 * 60.0), -1.0, 1.0
    )
    return one_hot + [
        math.sin(weekday_angle),
        math.cos(weekday_angle),
        clamp(duration / 180.0),
        clamp(float(row.get("daily_workload_before_block") or 0.0) / 600.0),
        clamp(float(row.get("continuous_work_minutes_before_block") or 0.0) / 240.0),
        deadline_feature,
        clamp(float(row.get("task_release_age_minutes") or 0.0) / (14.0 * 24.0 * 60.0)),
        quantile,
    ]


def outcome_label(outcome: str) -> int | None:
    if outcome in {"COMPLETED", "PARTIALLY_COMPLETED"}:
        return 1
    if outcome in {"SKIPPED", "DELAYED"}:
        return 0
    if outcome == "UNKNOWN":
        return None
    raise ValueError(f"unsupported outcome: {outcome}")


def adapt_dataset(source: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    tasks = read_jsonl(source / "tasks.jsonl")
    task_lookup = {str(task["task_id"]): task for task in tasks}
    durations = {str(row["task_id"]): row for row in read_jsonl(source / "duration_labels.jsonl")}
    cycles = {str(row["task_id"]): row for row in read_jsonl(source / "release_completion.jsonl")}
    blocks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counterfactual_blocks_excluded = 0
    for row in read_jsonl(source / "blocks.jsonl"):
        # v1.2 stores blocks for every Pareto candidate. Only the selected plan
        # produced observable user feedback; alternative-plan outcomes are
        # counterfactual simulator values and must not supervise execution.
        if row.get("selected_in_snapshot", True) is not True:
            counterfactual_blocks_excluded += 1
            continue
        blocks[str(row["task_id"])].append(row)
    histories = CausalUserHistory(read_jsonl(source / "user_days.jsonl"))
    output: dict[str, list[dict[str, Any]]] = {
        "train": [], "validation": [], "test": [], "semantic_test": []
    }
    cold_start_tasks = 0
    unknown_slots = 0
    excluded_semantic_holdout = 0
    task_prediction_before_release = sum(
        parse_instant(str(task["prediction_at"])) < parse_instant(str(task["released_at"]))
        for task in tasks
    )
    block_plan_before_release = sum(
        parse_instant(str(block["plan_generated_at"]))
        < parse_instant(str(task_lookup[str(block["task_id"])]["released_at"]))
        for task_blocks in blocks.values()
        for block in task_blocks
    )
    if task_prediction_before_release or block_plan_before_release:
        raise ValueError(
            "source dataset is not causally valid: "
            f"{task_prediction_before_release} tasks have prediction_at < released_at; "
            f"{block_plan_before_release} blocks have plan_generated_at < task.released_at"
        )
    for task in tasks:
        task_id = str(task["task_id"])
        user_id = str(task["anonymous_user_id"])
        released = parse_instant(str(task["released_at"]))
        prediction = parse_instant(str(task["prediction_at"]))
        category = CATEGORY_MAP.get(str(task["task_category"]))
        if category is None:
            raise ValueError(f"unsupported category: {task['task_category']}")
        duration = durations.get(task_id)
        cycle = cycles.get(task_id)
        duration_prediction = prediction if duration is None else parse_instant(str(duration["prediction_at"]))
        duration_state = histories.state_before(user_id, duration_prediction)
        if not any(duration_state):
            cold_start_tasks += 1
        slot_samples: list[dict[str, Any]] = []
        for block in sorted(blocks.get(task_id, []), key=lambda row: str(row["planned_start"])):
            prediction_time = parse_instant(str(block["prediction_at"]))
            label = outcome_label(str(block["outcome"])) if block.get("label_observed") is True else None
            if label is None:
                unknown_slots += 1
            slot_samples.append({
                "features": encode_slot(block),
                "user_state": histories.state_before(user_id, prediction_time),
                "outcome": label,
            })
        split = {"train": "train", "val": "validation", "test": "test"}.get(str(task["label_split"]))
        if split is None:
            raise ValueError(f"unsupported split: {task['label_split']}")
        adapted = {
            "task_id": task_id,
            "user_id": user_id,
            "title": str(task["sanitized_title"]),
            "category": category,
            "course_id": str(task["anonymous_course_id"]),
            "difficulty": int(task["difficulty"]),
            "priority": int(task["priority"]),
            "splittable": bool(task["splittable"]),
            "subtask_count": int(task["subtask_count"]),
            "estimated_minutes": int(task["initial_estimated_minutes"]),
            "released_at": str(task["released_at"]),
            "observed_at": str(task["prediction_at"]),
            "earliest_start_at": task.get("earliest_start_at"),
            "deadline_at": task.get("deadline_at"),
            "actual_work_minutes": None if duration is None else int(duration["actual_work_minutes"]),
            "completed_at": None if cycle is None else cycle.get("completed_at"),
            "user_state": duration_state,
            "slot_samples": slot_samples,
        }
        if bool(task.get("semantic_holdout")):
            output["semantic_test"].append(adapted)
            # Test-user tasks remain in the untouched user-holdout test. Holdout
            # families from train/validation users must never reach encoder fitting.
            if split in {"train", "validation"}:
                excluded_semantic_holdout += 1
                continue
        output[split].append(adapted)
    manifest = {
        "schema_version": 2,
        "source": str(source),
        "simulated": True,
        "causal_rule": "user-day state uses only dates strictly earlier than prediction_at",
        "counts": {name: len(rows) for name, rows in output.items()},
        "cold_start_tasks": cold_start_tasks,
        "unknown_slots_masked": unknown_slots,
        "counterfactual_blocks_excluded": counterfactual_blocks_excluded,
        "semantic_holdout_excluded_from_train_or_validation": excluded_semantic_holdout,
        "semantic_test_note": "all semantic_holdout tasks; test-user rows also remain in user-holdout test",
        "user_state_order": USER_STATE_ORDER,
        "slot_feature_order": SLOT_FEATURE_ORDER,
        "category_map": CATEGORY_MAP,
        "excluded_leakage_fields": ("sim_will_complete", "sim_risk_pref", "sim_reliability", "sim_note", "label_*"),
        "source_sha256": {path.name: sha256(path) for path in sorted(source.glob("*.jsonl"))},
    }
    return output, manifest


def write_adapted(output: Path, splits: dict[str, list[dict[str, Any]]], manifest: dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, rows in splits.items():
        with (output / f"{name}.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

