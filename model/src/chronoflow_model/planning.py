from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence


@dataclass(frozen=True)
class PlanBlock:
    task_id: str
    start_minute: int
    end_minute: int

    @property
    def duration_minutes(self) -> int:
        return self.end_minute - self.start_minute


@dataclass(frozen=True)
class TaskRiskInput:
    task_id: str
    released_minute: int
    deadline_minute: int | None
    priority: int
    duration_samples: tuple[int, ...]
    execution_probabilities: tuple[float, ...]


@dataclass(frozen=True)
class CandidateMetrics:
    expected_unfinished: float
    expected_tardiness: float
    cvar_tardiness: float
    fragmentation: float
    fatigue: float
    stability: float
    response_delay: float
    preference_mismatch: float

    def vector(self) -> tuple[float, ...]:
        return (
            self.expected_unfinished,
            self.expected_tardiness,
            self.cvar_tardiness,
            self.fragmentation,
            self.fatigue,
            self.stability,
            self.preference_mismatch,
        )


@dataclass(frozen=True)
class RiskWeights:
    unfinished: float = 5.0
    tardiness: float = 3.0
    cvar: float = 4.0
    fragmentation: float = 0.5
    fatigue: float = 0.5
    stability: float = 1.5
    response_delay: float = 0.3
    preference: float = 1.0


@dataclass(frozen=True)
class CandidatePlan:
    name: str
    blocks: tuple[PlanBlock, ...]
    metrics: CandidateMetrics


def cvar(losses: Sequence[float], alpha: float = 0.9) -> float:
    if not losses or not 0.0 < alpha < 1.0:
        raise ValueError("CVaR requires losses and alpha between zero and one")
    ordered = sorted(float(value) for value in losses)
    tail_count = max(1, math.ceil((1.0 - alpha) * len(ordered)))
    return sum(ordered[-tail_count:]) / tail_count


def robust_score(metrics: CandidateMetrics, weights: RiskWeights) -> float:
    return (
        weights.unfinished * metrics.expected_unfinished
        + weights.tardiness * metrics.expected_tardiness
        + weights.cvar * metrics.cvar_tardiness
        + weights.fragmentation * metrics.fragmentation
        + weights.fatigue * metrics.fatigue
        + weights.stability * metrics.stability
        + weights.response_delay * metrics.response_delay
        + weights.preference * metrics.preference_mismatch
    )


def stability_cost(old_blocks: Iterable[PlanBlock], new_blocks: Iterable[PlanBlock], freeze_minutes: int = 120) -> float:
    old = {block.task_id: block for block in old_blocks}
    total = 0.0
    for block in new_blocks:
        previous = old.get(block.task_id)
        if previous is None:
            continue
        shift = abs(block.start_minute - previous.start_minute)
        if previous.start_minute <= freeze_minutes and shift > 0:
            return math.inf
        proximity_weight = 4.0 if previous.start_minute <= 24 * 60 else 2.0 if previous.start_minute <= 48 * 60 else 1.0
        total += proximity_weight * shift
    return total


def respects_fixed_intervals(blocks: Iterable[PlanBlock], fixed_intervals: Iterable[tuple[int, int]]) -> bool:
    block_rows = sorted(blocks, key=lambda value: value.start_minute)
    for index, block in enumerate(block_rows):
        if block.start_minute < 0 or block.end_minute <= block.start_minute:
            return False
        if index and block.start_minute < block_rows[index - 1].end_minute:
            return False
        if any(block.start_minute < end and start < block.end_minute for start, end in fixed_intervals):
            return False
    return True


def pareto_front(plans: Iterable[CandidatePlan], tolerance: float = 1e-9) -> list[CandidatePlan]:
    rows = list(plans)
    result: list[CandidatePlan] = []
    for candidate in rows:
        current = candidate.metrics.vector()
        dominated = False
        for other in rows:
            if other is candidate:
                continue
            comparison = other.metrics.vector()
            no_worse = all(left <= right + tolerance for left, right in zip(comparison, current))
            strictly_better = any(left < right - tolerance for left, right in zip(comparison, current))
            if no_worse and strictly_better:
                dominated = True
                break
        if not dominated:
            result.append(candidate)
    return result


def normalized_response_delay(completed_minute: int, released_minute: int, deadline_minute: int | None) -> float:
    lead = max(0, completed_minute - released_minute)
    if deadline_minute is None or deadline_minute <= released_minute:
        return float(lead) / (24.0 * 60.0)
    return lead / (deadline_minute - released_minute)

