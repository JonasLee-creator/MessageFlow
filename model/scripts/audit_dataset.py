from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable


TABLES = (
    "users", "tasks", "duration_labels", "blocks", "user_days",
    "release_completion", "pareto_choices", "plan_snapshots", "replans",
    "fixed_intervals", "scenarios", "scenario_instances",
)
COUNT_KEYS = {"scenario_instances": "scenario_instances_full"}
ID_FIELDS = {
    "users": "anonymous_user_id", "tasks": "task_id", "blocks": "block_id",
    "pareto_choices": "decision_id", "plan_snapshots": "snapshot_id",
    "replans": "replan_id", "fixed_intervals": "fixed_id",
    "scenarios": "scenario_id", "scenario_instances": "scenario_id",
}
FREEZE_KINDS = {"NONE", "SYSTEM_FREEZE", "USER_LOCK", "MANUAL_OVERRIDE"}


def instant(value: str | None) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed


def read_jsonl(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        errors.append(f"missing required file: {path.name}")
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("row is not an object")
                rows.append(value)
            except Exception as error:
                errors.append(f"{path.name}:{line_number}: invalid JSON: {error}")
    return rows


def duplicate_count(rows: Iterable[dict[str, Any]], key: str) -> int:
    values = [row.get(key) for row in rows]
    return len(values) - len(set(values))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def overlaps(left_start: datetime, left_end: datetime, right_start: datetime, right_end: datetime) -> bool:
    return left_start < right_end and right_start < left_end


def dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Whether left is no worse on every declared objective and better on one."""
    minimized = ("deadline_risk", "fragmentation", "stability_cost", "fatigue")
    maximized = ("mean_execution_prob", "free_minutes")
    no_worse = all(float(left[key]) <= float(right[key]) for key in minimized)
    no_worse = no_worse and all(float(left[key]) >= float(right[key]) for key in maximized)
    strict = any(float(left[key]) < float(right[key]) for key in minimized)
    strict = strict or any(float(left[key]) > float(right[key]) for key in maximized)
    return no_worse and strict


def audit(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    tables = {name: read_jsonl(root / f"{name}.jsonl", errors) for name in TABLES}

    split_path = root / "splits.json"
    split_info = json.loads(split_path.read_text(encoding="utf-8")) if split_path.is_file() else {}
    if not split_info:
        errors.append("missing or empty splits.json")
    expected_counts = split_info.get("counts", {})
    counts = {name: len(rows) for name, rows in tables.items()}
    for name, count in counts.items():
        expected = expected_counts.get(COUNT_KEYS.get(name, name))
        if expected is not None and expected != count:
            errors.append(f"{name}: count={count}, splits.json={expected}")

    checksums: dict[str, str] = {}
    checksum_path = root / "SHA256SUMS.txt"
    if checksum_path.is_file():
        for line in checksum_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                digest, filename = line.split(maxsplit=1)
                checksums[filename.strip()] = digest
    else:
        errors.append("missing SHA256SUMS.txt")
    if checksum_path.name in checksums:
        warnings.append("SHA256SUMS.txt lists itself; self-checksum is ignored")
    checksum_mismatches = [
        filename for filename, expected in checksums.items()
        if filename != checksum_path.name
        and (not (root / filename).is_file() or sha256(root / filename) != expected)
    ]
    if checksum_mismatches:
        errors.append(f"checksum mismatch or missing file: {checksum_mismatches}")

    generator_relative = str(split_info.get("generator") or "")
    declared_generator_path = root.parent / generator_relative if generator_relative else None
    bundled_generator_path = root / Path(generator_relative).name if generator_relative else None
    generator_path = next(
        (path for path in (declared_generator_path, bundled_generator_path) if path and path.is_file()),
        None,
    )
    generator_exists = generator_path is not None
    if not generator_exists:
        errors.append(f"declared generator is missing: {generator_relative or '<not declared>'}")
    elif declared_generator_path != generator_path:
        warnings.append(
            f"declared generator path is missing; using bundled copy {generator_path.name}"
        )

    non_simulation_roles = {
        name: sum(row.get("data_role") != "simulation_only" for row in rows)
        for name, rows in tables.items()
    }
    bad_roles = {name: count for name, count in non_simulation_roles.items() if count}
    if bad_roles:
        errors.append(f"rows missing data_role=simulation_only: {bad_roles}")

    duplicate_ids = {name: duplicate_count(tables[name], field) for name, field in ID_FIELDS.items()}
    for name, count in duplicate_ids.items():
        if count:
            errors.append(f"{name}: {count} duplicate primary IDs")

    users = tables["users"]
    tasks = tables["tasks"]
    user_split = {str(row.get("anonymous_user_id")): row.get("label_split") for row in users}
    split_sets = {name: set(values) for name, values in split_info.get("by_user", {}).items()}
    for left, right in (("train", "val"), ("train", "test"), ("val", "test")):
        if split_sets.get(left, set()) & split_sets.get(right, set()):
            errors.append("splits.json contains the same user in multiple splits")
            break
    if split_sets and set().union(*split_sets.values()) != set(user_split):
        errors.append("splits.json users do not exactly match users.jsonl")
    for name, values in split_sets.items():
        for user_id in values:
            if user_split.get(user_id) != name:
                errors.append(f"user {user_id} disagrees between users.jsonl and splits.json")

    task_by_id = {str(row.get("task_id")): row for row in tasks}
    block_by_id = {str(row.get("block_id")): row for row in tables["blocks"]}
    fixed_by_id = {str(row.get("fixed_id")): row for row in tables["fixed_intervals"]}
    choice_by_id = {str(row.get("decision_id")): row for row in tables["pareto_choices"]}
    scenario_by_id = {str(row.get("scenario_id")): row for row in tables["scenarios"]}

    unknown_references: Counter[str] = Counter()
    split_mismatches: Counter[str] = Counter()
    for table_name, rows in tables.items():
        for row in rows:
            user_id = row.get("anonymous_user_id")
            if user_id is not None:
                user_id = str(user_id)
                if user_id not in user_split:
                    unknown_references[f"{table_name}.user"] += 1
                elif row.get("label_split") != user_split[user_id]:
                    split_mismatches[table_name] += 1
            task_id = row.get("task_id")
            if table_name != "tasks" and task_id is not None:
                task = task_by_id.get(str(task_id))
                if task is None:
                    unknown_references[f"{table_name}.task"] += 1
                elif user_id is not None and str(task.get("anonymous_user_id")) != user_id:
                    unknown_references[f"{table_name}.task_user"] += 1
    if unknown_references:
        errors.append(f"unknown or inconsistent foreign keys: {dict(unknown_references)}")
    if split_mismatches:
        errors.append(f"row/user split mismatches: {dict(split_mismatches)}")

    task_errors: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    split_task_counts: Counter[str] = Counter()
    tasks_per_user: Counter[str] = Counter()
    titles: Counter[str] = Counter()
    task_prediction_before_release = 0
    held_families = set(split_info.get("semantic_family_holdout", {}).get("families", []))
    semantic_train_families: set[str] = set()
    semantic_test_families: set[str] = set()
    semantic_holdout_tasks = 0
    for row in tasks:
        try:
            released = instant(row.get("released_at"))
            earliest = instant(row.get("earliest_start_at"))
            deadline = instant(row.get("deadline_at"))
            prediction = instant(row.get("prediction_at"))
            if released is None or prediction is None:
                task_errors["missing_release_or_prediction"] += 1
            elif prediction < released:
                task_prediction_before_release += 1
            if earliest is not None and released is not None and earliest < released:
                task_errors["earliest_before_release"] += 1
            if bool(row.get("has_deadline")) != (deadline is not None):
                task_errors["has_deadline_mismatch"] += 1
            if deadline is not None and released is not None and deadline <= released:
                task_errors["deadline_not_after_release"] += 1
        except Exception:
            task_errors["invalid_timestamp"] += 1
        if not 1 <= int(row.get("difficulty", 0)) <= 5:
            task_errors["difficulty_range"] += 1
        if not 1 <= int(row.get("priority", 0)) <= 5:
            task_errors["priority_range"] += 1
        if int(row.get("initial_estimated_minutes", 0)) <= 0:
            task_errors["estimate_range"] += 1
        family = str(row.get("semantic_family"))
        holdout = bool(row.get("semantic_holdout"))
        if holdout:
            semantic_holdout_tasks += 1
            semantic_test_families.add(family)
            if family not in held_families or row.get("label_split_semantic") != "family_holdout_test":
                task_errors["semantic_holdout_metadata"] += 1
        else:
            semantic_train_families.add(family)
            if family in held_families or row.get("label_split_semantic") != row.get("label_split"):
                task_errors["semantic_train_metadata"] += 1
        categories[str(row.get("task_category"))] += 1
        split_task_counts[str(row.get("label_split"))] += 1
        tasks_per_user[str(row.get("anonymous_user_id"))] += 1
        titles[str(row.get("sanitized_title"))] += 1
    if task_errors:
        errors.append(f"task validation errors: {dict(task_errors)}")
    if task_prediction_before_release:
        errors.append(f"causal violation: {task_prediction_before_release} tasks have prediction_at before released_at")
    semantic_family_overlap = semantic_train_families & semantic_test_families
    if semantic_family_overlap:
        errors.append(f"semantic holdout leaks {len(semantic_family_overlap)} families into encoder training")
    if semantic_test_families != held_families:
        errors.append("semantic holdout families disagree with splits.json")

    duration_errors: Counter[str] = Counter()
    duration_by_category: Counter[str] = Counter()
    duration_prediction_before_release = 0
    for row in tables["duration_labels"]:
        actual = float(row.get("actual_work_minutes", 0))
        if actual <= 0:
            duration_errors["actual_minutes"] += 1
        if int(row.get("session_count", 0)) <= 0:
            duration_errors["session_count"] += 1
        if actual > 0 and abs(math.log(actual) - float(row.get("label_log_duration_mean", 0))) > 1e-6:
            duration_errors["log_label"] += 1
        try:
            task = task_by_id[str(row.get("task_id"))]
            if instant(row.get("prediction_at")) < instant(task.get("released_at")):
                duration_prediction_before_release += 1
            if instant(row.get("completed_at")) <= instant(row.get("prediction_at")):
                duration_errors["completion_not_after_prediction"] += 1
        except Exception:
            duration_errors["invalid_prediction_time"] += 1
        duration_by_category[str(row.get("task_category"))] += 1
    if duration_errors:
        errors.append(f"duration label errors: {dict(duration_errors)}")
    if duration_prediction_before_release:
        errors.append(f"causal violation: {duration_prediction_before_release} duration labels were predicted before task release")

    block_errors: Counter[str] = Counter()
    selected_block_errors: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    selected_outcome_counts: Counter[str] = Counter()
    time_bucket_counts: Counter[str] = Counter()
    freeze_counts: Counter[str] = Counter()
    block_planned_before_release = 0
    unknown_false_placeholders = 0
    counterfactual_observed_labels = 0
    counterfactual_actual_values = 0
    for row in tables["blocks"]:
        try:
            start, end = instant(row.get("planned_start")), instant(row.get("planned_end"))
            prediction, generated = instant(row.get("prediction_at")), instant(row.get("plan_generated_at"))
            actual_start, actual_end = instant(row.get("actual_start")), instant(row.get("actual_end"))
            if start is None or end is None or end <= start:
                block_errors["planned_time"] += 1
            if prediction is None or generated is None or start is None or not (prediction <= generated <= start):
                block_errors["prediction_plan_execution_order"] += 1
            task = task_by_id[str(row.get("task_id"))]
            if generated is not None and generated < instant(task.get("released_at")):
                block_planned_before_release += 1
            if (actual_start is None) != (actual_end is None):
                block_errors["partial_actual_time"] += 1
                if row.get("selected_in_snapshot") is True:
                    selected_block_errors["partial_actual_time"] += 1
            if actual_start is not None and actual_end is not None and actual_end <= actual_start:
                block_errors["actual_time"] += 1
        except Exception:
            block_errors["invalid_timestamp"] += 1
        outcome = str(row.get("outcome"))
        outcome_counts[outcome] += 1
        is_counterfactual = row.get("selected_in_snapshot") is False
        if not is_counterfactual:
            selected_outcome_counts[outcome] += 1
        time_bucket_counts[str(row.get("time_bucket"))] += 1
        observed = bool(row.get("label_observed"))
        if is_counterfactual:
            if observed:
                counterfactual_observed_labels += 1
            if any(row.get(key) is not None for key in ("actual_start", "actual_end", "actual_minutes")):
                counterfactual_actual_values += 1
            if row.get("outcome") is not None or row.get("label_executed") is not None or row.get("label_failed_feedback") is not None:
                block_errors["counterfactual_label_not_null"] += 1
        elif observed != (outcome != "UNKNOWN"):
            block_errors["observed_mask"] += 1
        executed = row.get("label_executed")
        failed = row.get("label_failed_feedback")
        expected_executed = outcome in {"COMPLETED", "PARTIALLY_COMPLETED"}
        expected_failed = outcome in {"SKIPPED", "DELAYED"}
        if is_counterfactual:
            pass
        elif outcome == "UNKNOWN":
            if executed is False and failed is False:
                unknown_false_placeholders += 1
            elif executed is not None or failed is not None:
                block_errors["unknown_has_nonempty_label"] += 1
        elif executed != expected_executed or failed != expected_failed:
            block_errors["outcome_label"] += 1
        actual = row.get("actual_minutes")
        if expected_executed and (actual is None or float(actual) <= 0):
            block_errors["executed_without_minutes"] += 1
            if row.get("selected_in_snapshot") is True:
                selected_block_errors["executed_without_minutes"] += 1
        freeze = str(row.get("freeze_kind"))
        freeze_counts[freeze] += 1
        expected_flags = {
            "NONE": (False, False, False), "SYSTEM_FREEZE": (True, False, False),
            "USER_LOCK": (False, True, False), "MANUAL_OVERRIDE": (False, False, True),
        }.get(freeze)
        flags = (bool(row.get("system_frozen")), bool(row.get("user_locked")), bool(row.get("manual_override")))
        if freeze not in FREEZE_KINDS:
            block_errors["freeze_enum"] += 1
        elif flags != expected_flags:
            block_errors["freeze_flag_mismatch"] += 1
    if block_errors:
        errors.append(f"block validation errors: {dict(block_errors)}")
    if block_planned_before_release:
        errors.append(f"causal violation: {block_planned_before_release} blocks were planned before their tasks were released")
    if counterfactual_observed_labels:
        errors.append(
            f"{counterfactual_observed_labels} unselected candidate blocks contain observed execution labels"
        )
    if unknown_false_placeholders:
        warnings.append(f"{unknown_false_placeholders} UNKNOWN blocks use false/false placeholders; always mask with label_observed")

    cycle_errors: Counter[str] = Counter()
    censored_count = completed_count = 0
    for row in tables["release_completion"]:
        try:
            released = instant(row.get("released_at"))
            first = instant(row.get("first_actual_start_at"))
            completed = instant(row.get("completed_at"))
            deadline = instant(row.get("deadline_at"))
            if bool(row.get("has_deadline")) != (deadline is not None):
                cycle_errors["has_deadline_mismatch"] += 1
            censored = bool(row.get("censored"))
            if censored:
                censored_count += 1
                if completed is not None or row.get("release_to_completion_minutes") is not None:
                    cycle_errors["censored_has_completion"] += 1
            else:
                completed_count += 1
                if released is None or completed is None:
                    cycle_errors["completed_missing_time"] += 1
                else:
                    lead = int((completed - released).total_seconds() // 60)
                    if lead != row.get("release_to_completion_minutes"):
                        cycle_errors["completion_formula"] += 1
                    actual = int(row.get("actual_work_minutes") or 0)
                    if max(0, lead - actual) != row.get("non_execution_gap_minutes"):
                        cycle_errors["gap_formula"] += 1
                    if deadline is not None and bool(completed <= deadline) != row.get("on_time"):
                        cycle_errors["on_time_formula"] += 1
                    if deadline is not None and deadline > released:
                        usage = (completed - released).total_seconds() / (deadline - released).total_seconds()
                        if abs(usage - float(row.get("deadline_window_usage"))) > 1.1e-4:
                            cycle_errors["window_usage_formula"] += 1
            if first is not None and released is not None:
                first_delay = int((first - released).total_seconds() // 60)
                if first_delay != row.get("release_to_first_start_minutes"):
                    cycle_errors["first_start_formula"] += 1
        except Exception:
            cycle_errors["invalid_time_or_number"] += 1
    if cycle_errors:
        errors.append(f"release/completion errors: {dict(cycle_errors)}")

    user_day_errors: Counter[str] = Counter()
    for row in tables["user_days"]:
        for key in ("completed_blocks", "skipped_blocks", "delayed_blocks", "actual_work_minutes", "planned_work_minutes", "task_backlog", "overdue_task_count"):
            if float(row.get(key, -1)) < 0:
                user_day_errors[f"negative_{key}"] += 1
        if not 0.0 <= float(row.get("recent_7_day_completion_rate", -1)) <= 1.0:
            user_day_errors["completion_rate"] += 1
    if user_day_errors:
        errors.append(f"user-day errors: {dict(user_day_errors)}")

    fixed_errors: Counter[str] = Counter()
    fixed_by_user: defaultdict[str, list[tuple[datetime, datetime, str]]] = defaultdict(list)
    for row in tables["fixed_intervals"]:
        try:
            start, end = instant(row.get("start")), instant(row.get("end"))
            if start is None or end is None or end <= start:
                fixed_errors["invalid_interval"] += 1
            else:
                fixed_by_user[str(row.get("anonymous_user_id"))].append((start, end, str(row.get("fixed_id"))))
        except Exception:
            fixed_errors["invalid_timestamp"] += 1
        if row.get("movable") is not False:
            fixed_errors["movable_fixed_interval"] += 1
    internal_fixed_overlaps = 0
    for intervals in fixed_by_user.values():
        intervals.sort()
        for previous, current in zip(intervals, intervals[1:]):
            if overlaps(previous[0], previous[1], current[0], current[1]):
                internal_fixed_overlaps += 1
    if internal_fixed_overlaps:
        fixed_errors["overlapping_fixed_intervals"] += internal_fixed_overlaps
    if fixed_errors:
        errors.append(f"fixed-interval errors: {dict(fixed_errors)}")
    if tables["fixed_intervals"] and all("known_at" not in row for row in tables["fixed_intervals"]):
        warnings.append("fixed_intervals has no known_at; causal availability of newly added events cannot be audited")

    choice_errors: Counter[str] = Counter()
    selected_counts: Counter[str] = Counter()
    identical_candidate_block_sets = dominated_choice_sets = dominated_candidates = 0
    empty_candidate_groups = 0
    dominated_candidates_by_plan: Counter[str] = Counter()
    for row in tables["pareto_choices"]:
        candidate_ids = list(row.get("candidate_plan_ids", []))
        candidates = list(row.get("candidates", []))
        by_id = {str(candidate.get("plan_id")): candidate for candidate in candidates}
        selected = str(row.get("selected_plan_id"))
        selected_counts[str(row.get("label_preferred_plan"))] += 1
        if selected not in candidate_ids or set(candidate_ids) != set(by_id):
            choice_errors["candidate_metadata"] += 1
        if sorted(candidate_ids) != sorted(row.get("display_order", [])) or len(set(candidate_ids)) != len(candidate_ids):
            choice_errors["display_or_candidates"] += 1
        if row.get("label_preferred_plan") != selected:
            choice_errors["label_mismatch"] += 1
        signatures: list[tuple[str, ...]] = []
        for candidate in candidates:
            block_ids = tuple(sorted(str(value) for value in candidate.get("block_ids", [])))
            signatures.append(block_ids)
            for block_id in block_ids:
                if block_id not in block_by_id:
                    choice_errors["unknown_candidate_block"] += 1
        if signatures and all(not signature for signature in signatures):
            empty_candidate_groups += 1
        elif len(signatures) > 1 and len(set(signatures)) == 1:
            identical_candidate_block_sets += 1
        metrics = [candidate.get("metrics", {}) for candidate in candidates]
        try:
            dominated_indexes = {
                j for i in range(len(metrics)) for j in range(len(metrics))
                if i != j and dominates(metrics[i], metrics[j])
            }
            dominated_candidates += len(dominated_indexes)
            for index in dominated_indexes:
                dominated_candidates_by_plan[str(candidates[index].get("plan_id"))] += 1
            if dominated_indexes:
                dominated_choice_sets += 1
        except (KeyError, TypeError, ValueError):
            choice_errors["invalid_metrics"] += 1
    if choice_errors:
        errors.append(f"Pareto-choice errors: {dict(choice_errors)}")
    if identical_candidate_block_sets:
        errors.append(f"{identical_candidate_block_sets} Pareto decisions give every candidate the same block set")
    if empty_candidate_groups:
        errors.append(f"{empty_candidate_groups} Pareto decisions contain no candidate blocks")
    if dominated_choice_sets:
        errors.append(f"{dominated_choice_sets} Pareto decisions contain dominated candidates")

    snapshot_errors: Counter[str] = Counter()
    selected_version_mismatches = fixed_overlap_references = total_selected_references = 0
    affected_snapshots: set[str] = set()
    for row in tables["plan_snapshots"]:
        choice = choice_by_id.get(str(row.get("decision_id")))
        if choice is None:
            snapshot_errors["unknown_decision"] += 1
        elif choice.get("selected_plan_id") != row.get("selected_plan_id") or choice.get("schedule_version") != row.get("schedule_version"):
            snapshot_errors["choice_mismatch"] += 1
        fixed_rows = []
        for fixed_id in row.get("fixed_interval_ids", []):
            fixed = fixed_by_id.get(str(fixed_id))
            if fixed is None:
                snapshot_errors["unknown_fixed_interval"] += 1
            else:
                fixed_rows.append(fixed)
        selected_ids = [str(value) for value in row.get("selected_block_ids", [])]
        total_selected_references += len(selected_ids)
        if choice is not None:
            chosen = next((item for item in choice.get("candidates", []) if item.get("plan_id") == row.get("selected_plan_id")), None)
            if chosen is None or set(selected_ids) != set(str(value) for value in chosen.get("block_ids", [])):
                snapshot_errors["selected_blocks_disagree_with_candidate"] += 1
        for block_id in selected_ids:
            block = block_by_id.get(block_id)
            if block is None:
                snapshot_errors["unknown_selected_block"] += 1
                continue
            if block.get("schedule_version") != row.get("schedule_version"):
                selected_version_mismatches += 1
            try:
                block_start, block_end = instant(block.get("planned_start")), instant(block.get("planned_end"))
                for fixed in fixed_rows:
                    if overlaps(block_start, block_end, instant(fixed.get("start")), instant(fixed.get("end"))):
                        fixed_overlap_references += 1
                        affected_snapshots.add(str(row.get("snapshot_id")))
                        break
            except Exception:
                snapshot_errors["invalid_interval"] += 1
    if snapshot_errors:
        errors.append(f"plan-snapshot errors: {dict(snapshot_errors)}")
    if fixed_overlap_references:
        errors.append(f"{fixed_overlap_references} selected block references overlap fixed intervals across {len(affected_snapshots)} snapshots")
    if selected_version_mismatches:
        warnings.append(f"{selected_version_mismatches}/{total_selected_references} selected block references differ from snapshot schedule_version")

    replan_errors: Counter[str] = Counter()
    replan_reasons: Counter[str] = Counter()
    locked_blocks_moved = reverted_without_acceptance = 0
    for row in tables["replans"]:
        replan_reasons[str(row.get("replan_reason"))] += 1
        if float(row.get("hours_until_execution", -1)) < 0:
            replan_errors["negative_horizon"] += 1
        try:
            expected_shift = int((instant(row.get("new_planned_start")) - instant(row.get("old_planned_start"))).total_seconds() / 60)
            if expected_shift != int(row.get("minutes_shifted")):
                replan_errors["shift_formula"] += 1
            if int(row.get("schedule_version_after")) <= int(row.get("schedule_version_before")):
                replan_errors["schedule_version_order"] += 1
        except Exception:
            replan_errors["invalid_time_or_version"] += 1
        freeze = str(row.get("freeze_kind"))
        if freeze not in FREEZE_KINDS:
            replan_errors["freeze_enum"] += 1
        if freeze == "USER_LOCK" and float(row.get("minutes_shifted", 0)) != 0:
            locked_blocks_moved += 1
        if row.get("user_reverted_replan") and not row.get("user_accepted_replan"):
            reverted_without_acceptance += 1
    if replan_errors:
        errors.append(f"replan errors: {dict(replan_errors)}")
    if locked_blocks_moved:
        errors.append(f"{locked_blocks_moved} USER_LOCK replans move locked tasks")
    if reverted_without_acceptance:
        warnings.append(f"{reverted_without_acceptance} replans are reverted with accepted=false; document whether this means rejection")

    scenario_errors: Counter[str] = Counter()
    for row in tables["scenario_instances"]:
        header = scenario_by_id.get(str(row.get("scenario_id")))
        if header is None:
            scenario_errors["missing_header"] += 1
            continue
        for key in ("seed", "stress_type", "horizon_days", "n_tasks"):
            if row.get(key) != header.get(key):
                scenario_errors[f"header_{key}"] += 1
        if len(row.get("tasks", [])) != int(row.get("n_tasks", -1)):
            scenario_errors["task_count"] += 1
        for task in row.get("tasks", []):
            if bool(task.get("has_deadline")) != (task.get("deadline_at") is not None):
                scenario_errors["has_deadline_mismatch"] += 1
            if not float(task.get("duration_p50", 0)) <= float(task.get("duration_p80", 0)) <= float(task.get("duration_p95", 0)):
                scenario_errors["duration_quantile_order"] += 1
    if scenario_errors:
        errors.append(f"scenario-instance errors: {dict(scenario_errors)}")

    missing_rates: dict[str, dict[str, float]] = {}
    for name, rows in tables.items():
        keys = sorted({key for row in rows for key in row})
        missing_rates[name] = {
            key: round(sum(row.get(key) is None for row in rows) / len(rows), 4)
            for key in keys if rows and any(row.get(key) is None for row in rows)
        }

    negative_feedback = selected_outcome_counts["SKIPPED"] + selected_outcome_counts["DELAYED"]
    known_feedback = sum(selected_outcome_counts.values()) - selected_outcome_counts["UNKNOWN"]
    negative_rate = negative_feedback / known_feedback if known_feedback else 0.0
    if min(duration_by_category.values(), default=0) < 250:
        warnings.append("at least one duration category has fewer than 250 examples")
    if negative_rate < 0.15:
        warnings.append("negative execution feedback is below 15%; execution model may be poorly identified")
    warnings.append("sim_* fields are generator ground truth and must be excluded from predictor inputs")

    task_counts = sorted(tasks_per_user.values())
    per_user_summary = {
        "minimum": min(task_counts, default=0),
        "median": task_counts[len(task_counts) // 2] if task_counts else 0,
        "maximum": max(task_counts, default=0),
    }
    scenario_stress = Counter(str(row.get("stress_type")) for row in tables["scenarios"])
    return {
        "status": "PASS" if not errors else "FAIL",
        "schema": split_info.get("scheme"),
        "simulated": bool(split_info.get("simulated")),
        "counts": counts,
        "checksum_mismatches": checksum_mismatches,
        "generator": {
            "declared": generator_relative,
            "resolved": None if generator_path is None else str(generator_path),
            "exists": generator_exists,
        },
        "non_simulation_roles": bad_roles,
        "duplicate_ids": duplicate_ids,
        "task_counts_by_split": dict(split_task_counts),
        "task_categories": dict(categories),
        "tasks_per_user": per_user_summary,
        "unique_sanitized_titles": len(titles),
        "duplicate_title_rows": sum(count - 1 for count in titles.values() if count > 1),
        "semantic_holdout": {
            "families": len(semantic_test_families), "tasks": semantic_holdout_tasks,
            "family_overlap_with_encoder_train": len(semantic_family_overlap),
        },
        "causal_violations": {
            "task_prediction_before_release": task_prediction_before_release,
            "duration_prediction_before_release": duration_prediction_before_release,
            "blocks_planned_before_task_release": block_planned_before_release,
        },
        "duration_examples_by_category": dict(duration_by_category),
        "block_outcomes": dict(outcome_counts),
        "selected_block_outcomes": dict(selected_outcome_counts),
        "block_time_buckets": dict(time_bucket_counts),
        "block_freeze_kinds": dict(freeze_counts),
        "selected_block_errors": dict(selected_block_errors),
        "counterfactual_blocks": {
            "observed_labels": counterfactual_observed_labels,
            "with_actual_values": counterfactual_actual_values,
        },
        "known_negative_feedback_rate": round(negative_rate, 4),
        "completion_cycles": {"completed": completed_count, "censored": censored_count},
        "pareto": {
            "selections": dict(selected_counts),
            "identical_candidate_block_sets": identical_candidate_block_sets,
            "empty_candidate_groups": empty_candidate_groups,
            "decision_sets_with_dominance": dominated_choice_sets,
            "dominated_candidates": dominated_candidates,
            "dominated_candidates_by_plan": dict(dominated_candidates_by_plan),
        },
        "plan_snapshots": {
            "selected_block_references": total_selected_references,
            "schedule_version_mismatches": selected_version_mismatches,
            "fixed_interval_overlap_references": fixed_overlap_references,
            "affected_snapshots": len(affected_snapshots),
        },
        "replan_reasons": dict(replan_reasons),
        "locked_blocks_moved": locked_blocks_moved,
        "scenario_stress_types": dict(scenario_stress),
        "missing_rates": missing_rates,
        "errors": errors,
        "warnings": sorted(set(warnings)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit ChronoFlow relational data without training.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.dataset)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
