from __future__ import annotations

from datetime import datetime
import math
import re
import unicodedata

from .config import FeatureConfig
from .records import CATEGORY_TO_INDEX, TaskRecord


NUMERIC_FEATURE_ORDER = (
    "difficulty",
    "priority",
    "log_estimated_minutes",
    "deadline_distance",
    "release_age",
    "earliest_start_delay",
    "splittable",
    "subtask_count",
    "has_deadline",
    "has_earliest_start",
    "is_short_task",
    "is_long_task",
    "deadline_under_24h",
    "deadline_under_72h",
    "reserved_1",
    "reserved_2",
)


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower().strip()
    return re.sub(r"\s+", " ", value)


def stable_hash(text: str) -> int:
    """FNV-1a 32-bit; intentionally simple to reproduce in Kotlin and JavaScript."""
    value = 2166136261
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 16777619) & 0xFFFFFFFF
    return value


def hashed_ngrams(title: str, config: FeatureConfig) -> list[float]:
    normalized = normalize_title(title)
    output = [0.0] * config.hash_dim
    count = 0
    for size in range(config.ngram_min, config.ngram_max + 1):
        for index in range(max(0, len(normalized) - size + 1)):
            token = normalized[index : index + size]
            hashed = stable_hash(token)
            bucket = hashed % config.hash_dim
            sign = -1.0 if hashed & 0x80000000 else 1.0
            output[bucket] += sign
            count += 1
    if count:
        scale = math.sqrt(sum(value * value for value in output)) or 1.0
        output = [value / scale for value in output]
    return output


def course_bucket(course_id: str, config: FeatureConfig) -> int:
    return stable_hash(course_id) % config.course_hash_buckets


def category_index(category: str) -> int:
    return CATEGORY_TO_INDEX.get(category.upper(), CATEGORY_TO_INDEX["OTHER"])


def numeric_features(record: TaskRecord, reference_time: datetime, expected_dim: int) -> list[float]:
    if expected_dim != len(NUMERIC_FEATURE_ORDER):
        raise ValueError(f"numeric_feature_dim must remain {len(NUMERIC_FEATURE_ORDER)} until the feature contract is versioned")
    deadline_hours = None if record.deadline_at is None else (record.deadline_at - reference_time).total_seconds() / 3600.0
    release_age_hours = max(0.0, (reference_time - record.released_at).total_seconds() / 3600.0)
    earliest_delay_hours = 0.0 if record.earliest_start_at is None else max(0.0, (record.earliest_start_at - record.released_at).total_seconds() / 3600.0)
    deadline_normalized = 1.0 if deadline_hours is None else max(-1.0, min(1.0, deadline_hours / (14.0 * 24.0)))
    return [
        record.difficulty / 5.0,
        record.priority / 10.0,
        math.log1p(record.estimated_minutes) / math.log1p(20160),
        deadline_normalized,
        min(1.0, release_age_hours / (30.0 * 24.0)),
        min(1.0, earliest_delay_hours / (14.0 * 24.0)),
        1.0 if record.splittable else 0.0,
        min(1.0, record.subtask_count / 8.0),
        1.0 if record.deadline_at is not None else 0.0,
        1.0 if record.earliest_start_at is not None else 0.0,
        1.0 if record.estimated_minutes <= 30 else 0.0,
        1.0 if record.estimated_minutes >= 180 else 0.0,
        1.0 if deadline_hours is not None and deadline_hours <= 24 else 0.0,
        1.0 if deadline_hours is not None and deadline_hours <= 72 else 0.0,
        0.0,
        0.0,
    ]
