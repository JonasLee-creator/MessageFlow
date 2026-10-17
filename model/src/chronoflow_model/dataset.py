from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch
from torch import Tensor
from torch.utils.data import Dataset

from .config import ModelConfig
from .features import category_index, course_bucket, hashed_ngrams, numeric_features
from .records import TaskRecord


class TaskDataset(Dataset[dict[str, Any]]):
    def __init__(self, path: str | Path, config: ModelConfig) -> None:
        self.config = config
        self.records: list[TaskRecord] = []
        with Path(path).open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                    self.records.append(TaskRecord.from_dict(raw, config.features.user_state_dim, config.features.slot_feature_dim))
                except Exception as error:
                    raise ValueError(f"invalid record at {path}:{line_number}: {error}") from error

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        record = self.records[index]
        reference = record.observed_at
        return {
            "task_id": record.task_id,
            "user_id": record.user_id,
            "hashed_text": hashed_ngrams(record.title, self.config.features),
            "category_id": category_index(record.category),
            "course_id": course_bucket(record.course_id, self.config.features),
            "numeric_features": numeric_features(record, reference, self.config.features.numeric_feature_dim),
            "user_state": list(record.user_state),
            "duration_target": float(record.actual_work_minutes or 0),
            "duration_mask": record.actual_work_minutes is not None,
            "slots": [list(slot.features) for slot in record.slot_samples],
            "slot_user_states": [list(slot.user_state) for slot in record.slot_samples],
            "outcomes": [float(slot.outcome or 0) for slot in record.slot_samples],
            "outcome_mask": [slot.outcome is not None for slot in record.slot_samples],
        }


def collate_tasks(rows: list[dict[str, Any]], slot_feature_dim: int) -> dict[str, Tensor | list[str]]:
    max_slots = max(1, max((len(row["slots"]) for row in rows), default=0))
    slot_rows: list[list[list[float]]] = []
    slot_user_rows: list[list[list[float]]] = []
    outcome_rows: list[list[float]] = []
    mask_rows: list[list[bool]] = []
    for row in rows:
        count = len(row["slots"])
        padding = max_slots - count
        slot_rows.append(row["slots"] + [[0.0] * slot_feature_dim for _ in range(padding)])
        user_state_dim = len(row["user_state"])
        slot_user_rows.append(row["slot_user_states"] + [[0.0] * user_state_dim for _ in range(padding)])
        outcome_rows.append(row["outcomes"] + [0.0] * padding)
        mask_rows.append(row["outcome_mask"] + [False] * padding)
    return {
        "task_ids": [row["task_id"] for row in rows],
        "user_ids": [row["user_id"] for row in rows],
        "hashed_text": torch.tensor([row["hashed_text"] for row in rows], dtype=torch.float32),
        "category_id": torch.tensor([row["category_id"] for row in rows], dtype=torch.long),
        "course_id": torch.tensor([row["course_id"] for row in rows], dtype=torch.long),
        "numeric_features": torch.tensor([row["numeric_features"] for row in rows], dtype=torch.float32),
        "user_state": torch.tensor([row["user_state"] for row in rows], dtype=torch.float32),
        "duration_target": torch.tensor([row["duration_target"] for row in rows], dtype=torch.float32),
        "duration_mask": torch.tensor([row["duration_mask"] for row in rows], dtype=torch.bool),
        "slot_features": torch.tensor(slot_rows, dtype=torch.float32),
        "slot_user_state": torch.tensor(slot_user_rows, dtype=torch.float32),
        "execution_target": torch.tensor(outcome_rows, dtype=torch.float32),
        "execution_mask": torch.tensor(mask_rows, dtype=torch.bool),
    }

