from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


CATEGORIES = (
    "EXPERIMENT",
    "REPORT",
    "PROGRAMMING",
    "REVIEW",
    "MEMORIZATION",
    "READING",
    "EXAM_PREPARATION",
    "OTHER",
)
CATEGORY_TO_INDEX = {name: index for index, name in enumerate(CATEGORIES)}


def parse_instant(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class SlotSample:
    features: tuple[float, ...]
    user_state: tuple[float, ...]
    outcome: int | None

    @classmethod
    def from_dict(cls, raw: dict[str, Any], expected_dim: int, user_state_dim: int) -> "SlotSample":
        values = tuple(float(value) for value in raw.get("features", []))
        if len(values) != expected_dim:
            raise ValueError(f"slot feature dimension must be {expected_dim}")
        user_state = tuple(float(value) for value in raw.get("user_state", []))
        if len(user_state) != user_state_dim:
            raise ValueError(f"slot user_state dimension must be {user_state_dim}")
        outcome = raw.get("outcome")
        if outcome not in (None, 0, 1):
            raise ValueError("slot outcome must be 0, 1, or null")
        return cls(values, user_state, outcome)


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    user_id: str
    title: str
    category: str
    course_id: str
    difficulty: int
    priority: int
    splittable: bool
    subtask_count: int
    estimated_minutes: int
    released_at: datetime
    observed_at: datetime
    earliest_start_at: datetime | None
    deadline_at: datetime | None
    actual_work_minutes: int | None
    completed_at: datetime | None
    user_state: tuple[float, ...]
    slot_samples: tuple[SlotSample, ...]

    @classmethod
    def from_dict(cls, raw: dict[str, Any], user_state_dim: int, slot_feature_dim: int) -> "TaskRecord":
        category = str(raw.get("category", "OTHER")).upper()
        if category not in CATEGORY_TO_INDEX:
            raise ValueError(f"unsupported task category: {category}")
        released_at = parse_instant(raw.get("released_at"))
        if released_at is None:
            raise ValueError("released_at is required")
        observed_at = parse_instant(raw.get("observed_at"))
        if observed_at is None:
            raise ValueError("observed_at is required to prevent future-data leakage")
        user_state = tuple(float(value) for value in raw.get("user_state", []))
        if len(user_state) != user_state_dim:
            raise ValueError(f"user_state dimension must be {user_state_dim}")
        actual = raw.get("actual_work_minutes")
        record = cls(
            task_id=str(raw.get("task_id", "")).strip(),
            user_id=str(raw.get("user_id", "")).strip(),
            title=str(raw.get("title", "")).strip(),
            category=category,
            course_id=str(raw.get("course_id", "unknown-course")).strip() or "unknown-course",
            difficulty=int(raw.get("difficulty", 3)),
            priority=int(raw.get("priority", 5)),
            splittable=bool(raw.get("splittable", True)),
            subtask_count=int(raw.get("subtask_count", 0)),
            estimated_minutes=int(raw.get("estimated_minutes", 60)),
            released_at=released_at,
            observed_at=observed_at,
            earliest_start_at=parse_instant(raw.get("earliest_start_at")),
            deadline_at=parse_instant(raw.get("deadline_at")),
            actual_work_minutes=None if actual is None else int(actual),
            completed_at=parse_instant(raw.get("completed_at")),
            user_state=user_state,
            slot_samples=tuple(SlotSample.from_dict(row, slot_feature_dim, user_state_dim) for row in raw.get("slot_samples", [])),
        )
        record.validate()
        return record

    def validate(self) -> None:
        if not self.task_id or not self.user_id or not self.title:
            raise ValueError("task_id, user_id, and title are required")
        if not 1 <= self.difficulty <= 5 or not 1 <= self.priority <= 10:
            raise ValueError("difficulty or priority is outside its allowed range")
        if self.estimated_minutes <= 0 or self.subtask_count < 0:
            raise ValueError("estimated_minutes must be positive and subtask_count cannot be negative")
        if self.actual_work_minutes is not None and self.actual_work_minutes <= 0:
            raise ValueError("actual_work_minutes must be positive when present")
        if self.deadline_at is not None and self.deadline_at <= self.released_at:
            raise ValueError("deadline_at must be after released_at")
        if self.observed_at < self.released_at:
            raise ValueError("observed_at cannot be before released_at")
        if self.completed_at is not None and self.completed_at < self.released_at:
            raise ValueError("completed_at cannot be before released_at")

