from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path


def uniform(*keys: object) -> float:
    """Counter-based random number: independent of policy call order."""
    digest = hashlib.sha256(json.dumps(keys, ensure_ascii=False).encode()).digest()
    return (int.from_bytes(digest[:8], 'big') + 0.5) / 2**64


def scenario_split(scenario_id: str) -> str:
    value = uniform('split-v1', scenario_id)
    return 'train' if value < .6 else 'validation' if value < .8 else 'test'


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    category: str
    course: str
    difficulty: int
    priority: int
    released: int
    available: int
    earliest: int
    deadline: int | None
    estimate: float
    splittable: bool


@dataclass(frozen=True)
class Block:
    task_id: str
    start: int
    end: int


@dataclass
class Scenario:
    id: str
    stress: str
    origin: datetime
    horizon: int
    tasks: list[Task]
    fixed: list[tuple[int, int]]
    # Simulator-only fields. Never pass Scenario to a planner/predictor.
    truth: dict

    def at(self, minute: int) -> datetime:
        return self.origin + timedelta(minutes=minute)


def load_scenarios(path: Path, split: str):
    with path.open(encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            if split != 'all' and scenario_split(raw['scenario_id']) != split:
                continue
            origin = (datetime.fromisoformat(raw['observation_start']) if raw.get('observation_start')
                      else min(datetime.fromisoformat(t['released_at']) for t in raw['tasks']))
            def minute(value):
                return round((datetime.fromisoformat(value) - origin).total_seconds() / 60)
            tasks, truth = [], {}
            for row in raw['tasks']:
                tid = row['local_task_id']
                released = minute(row['released_at'])
                tasks.append(Task(tid, row['sanitized_title'], row['task_category'],
                    row.get('anonymous_course_id', 'unknown'), row['difficulty'], row['priority'],
                    released, max(released, minute(row.get('prediction_at', row['released_at']))),
                    minute(row.get('earliest_start_at', row['released_at'])),
                    minute(row['deadline_at']) if row.get('deadline_at') else None,
                    float(row['initial_estimated_minutes']), bool(row['splittable'])))
                truth[tid] = {'duration': float(row['sampled_duration_minutes']),
                              'probabilities': row['execution_prob_by_bucket']}
            # Missing known_at: all fixed events are explicitly treated as known initially.
            fixed = [(minute(f['start']), minute(f['end'])) for f in raw['fixed_intervals']]
            yield Scenario(raw['scenario_id'], raw['stress_type'], origin,
                           int(raw['horizon_minutes']) if 'horizon_minutes' in raw else int(raw['horizon_days']) * 1440,
                           tasks, fixed, truth)
