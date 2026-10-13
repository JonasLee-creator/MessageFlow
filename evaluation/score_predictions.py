# -*- coding: utf-8 -*-
"""Score prediction JSONL against gold labels in the input file or a separate gold file."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

ACTIONS = [
    "CREATE_TASK", "UPDATE_TASK", "CANCEL_TASK",
    "CREATE_EVENT", "UPDATE_EVENT", "CANCEL_EVENT", "IGNORE",
]


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def norm(text: str) -> str:
    return "".join((text or "").split())


def instant(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(second=0, microsecond=0)


def match(gold: list[dict], pred: list[dict]) -> list[tuple[int, int]]:
    used: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for gi, item in enumerate(gold):
        for pi, other in enumerate(pred):
            if pi in used:
                continue
            if item["action"] == other.get("action") and norm(item.get("title", "")) == norm(other.get("title", "")):
                pairs.append((gi, pi))
                used.add(pi)
                break
    matched = {gi for gi, _ in pairs}
    for gi, item in enumerate(gold):
        if gi in matched:
            continue
        for pi, other in enumerate(pred):
            if pi in used or item["action"] != other.get("action"):
                continue
            pairs.append((gi, pi))
            used.add(pi)
            break
    return pairs


def time_ok(gold: dict, pred: dict) -> bool:
    action = gold["action"]
    if action.startswith("CANCEL") or action == "IGNORE":
        return True
    if action.endswith("EVENT"):
        return instant(gold.get("start")) == instant(pred.get("start")) and instant(gold.get("end")) == instant(pred.get("end"))
    return instant(gold.get("deadline")) == instant(pred.get("deadline"))


def f1(tp: int, fp: int, fn: int) -> float:
    if tp == 0 and fp == 0 and fn == 0:
        return 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def percentile(values: list[int], ratio: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def score(gold_rows: list[dict], pred_rows: list[dict]) -> dict:
    pred_by_id = {row["sample_id"]: row for row in pred_rows}
    gold_rows = [row for row in gold_rows if row["id"] in pred_by_id]
    counts = {action: {"tp": 0, "fp": 0, "fn": 0} for action in ACTIONS}
    title_hit = title_total = time_hit = time_total = target_hit = target_total = 0
    multi_tp = multi_fp = multi_fn = 0
    ignore_total = ignore_fp = question_total = question_hit = hallucination = 0
    auto_total = auto_wrong = 0
    for gold_row in gold_rows:
        pred = pred_by_id.get(gold_row["id"])
        gold_items = gold_row["gold"]["items"]
        pred_items = (pred or {}).get("prediction", {}).get("items", [])
        pairs = match(gold_items, pred_items)
        matched_g = {gi for gi, _ in pairs}
        matched_p = {pi for _, pi in pairs}
        for gi, item in enumerate(gold_items):
            if gi not in matched_g:
                counts[item["action"]]["fn"] += 1
        for pi, item in enumerate(pred_items):
            action = item.get("action")
            if pi not in matched_p and action in counts:
                counts[action]["fp"] += 1
        for gi, pi in pairs:
            counts[gold_items[gi]["action"]]["tp"] += 1
            title_total += 1
            title_hit += norm(gold_items[gi].get("title", "")) == norm(pred_items[pi].get("title", ""))
            time_total += 1
            time_hit += time_ok(gold_items[gi], pred_items[pi])
            if gold_items[gi]["action"].startswith(("UPDATE", "CANCEL")):
                target_total += 1
                target_hit += gold_items[gi].get("target_id") == pred_items[pi].get("target_id")
        if len(gold_items) >= 2:
            strict = {(item["action"], norm(item.get("title", ""))) for item in gold_items}
            found = {(item.get("action"), norm(item.get("title", ""))) for item in pred_items}
            multi_tp += len(strict & found)
            multi_fp += len(found - strict)
            multi_fn += len(strict - found)
        if gold_row["gold"]["should_ignore"]:
            ignore_total += 1
            if any(item.get("action") != "IGNORE" for item in pred_items):
                ignore_fp += 1
        if any(item.get("requires_question") for item in gold_items):
            question_total += 1
            if any(item.get("questions") for item in pred_items):
                question_hit += 1
        text = gold_row["text"]
        names = {item.get("title", "") for item in gold_row.get("context", {}).get("candidate_tasks", [])}
        bad = False
        for item in pred_items:
            title = item.get("title") or ""
            if item.get("action") != "IGNORE" and title and title not in text and title not in names:
                bad = True
            if any(snippet not in text for snippet in item.get("evidence") or []):
                bad = True
        hallucination += int(bad)
        if pred and pred.get("auto_apply"):
            auto_total += 1
            correct = len(pairs) == len(gold_items) == len(pred_items) and all(
                norm(gold_items[gi].get("title", "")) == norm(pred_items[pi].get("title", ""))
                and time_ok(gold_items[gi], pred_items[pi])
                and gold_items[gi].get("target_id") == pred_items[pi].get("target_id")
                for gi, pi in pairs
            )
            auto_wrong += int(not correct)
    labels = [action for action in ACTIONS if any(counts[action].values())]
    macro = sum(f1(**counts[action]) for action in labels) / len(labels) if labels else 0.0
    latencies = [int(row.get("latency_ms") or 0) for row in pred_rows]
    prompt = [int(row.get("prompt_tokens") or 0) for row in pred_rows]
    completion = [int(row.get("completion_tokens") or 0) for row in pred_rows]
    def ratio(hit: int, total: int) -> float | None:
        return round(hit / total, 4) if total else None
    return {
        "samples": len(gold_rows),
        "action_macro_f1": round(macro, 4),
        "title_accuracy": ratio(title_hit, title_total),
        "time_accuracy": ratio(time_hit, time_total),
        "target_accuracy": ratio(target_hit, target_total),
        "multi_f1": round(f1(multi_tp, multi_fp, multi_fn), 4),
        "irrelevant_false_positive_rate": ratio(ignore_fp, ignore_total),
        "question_recall": ratio(question_hit, question_total),
        "hallucination_rate": ratio(hallucination, len(gold_rows)),
        "auto_apply_coverage": ratio(auto_total, len(gold_rows)),
        "wrong_auto_apply_rate": ratio(auto_wrong, auto_total),
        "latency_p50_ms": percentile(latencies, 0.50),
        "latency_p95_ms": percentile(latencies, 0.95),
        "avg_prompt_tokens": round(sum(prompt) / len(prompt), 1) if prompt else 0,
        "avg_completion_tokens": round(sum(completion) / len(completion), 1) if completion else 0,
        "api_errors": sum(1 for row in pred_rows if row.get("api_error")),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = score(load(args.gold), load(args.predictions))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
