from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path


@dataclass
class BetaPosterior:
    alpha: float = 2.0
    beta: float = 2.0

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def update(self, executed: bool, weight: float = 1.0) -> None:
        if weight <= 0:
            raise ValueError("update weight must be positive")
        if executed:
            self.alpha += weight
        else:
            self.beta += weight

    def decay(self, factor: float = 0.98) -> None:
        if not 0.0 <= factor <= 1.0:
            raise ValueError("decay factor must be between zero and one")
        self.alpha = 2.0 + (self.alpha - 2.0) * factor
        self.beta = 2.0 + (self.beta - 2.0) * factor


@dataclass
class DurationPosterior:
    weighted_log_ratio: float = 0.0
    weight: float = 0.0
    prior_weight: float = 5.0

    @property
    def multiplier(self) -> float:
        return math.exp(self.weighted_log_ratio / (self.prior_weight + self.weight))

    def update(self, estimated_minutes: int, actual_minutes: int, observation_weight: float = 1.0) -> None:
        if estimated_minutes <= 0 or actual_minutes <= 0 or observation_weight <= 0:
            raise ValueError("duration update values must be positive")
        ratio = max(0.25, min(4.0, actual_minutes / estimated_minutes))
        self.weighted_log_ratio += observation_weight * math.log(ratio)
        self.weight += observation_weight


@dataclass
class PersonalModelState:
    duration_by_category: dict[str, DurationPosterior] = field(default_factory=dict)
    execution_by_time_bucket: dict[str, BetaPosterior] = field(default_factory=lambda: {
        "MORNING": BetaPosterior(), "AFTERNOON": BetaPosterior(), "EVENING": BetaPosterior(), "NIGHT": BetaPosterior()
    })
    latent_state: list[float] = field(default_factory=lambda: [0.0] * 12)
    risk_weight: float = 1.0
    stability_weight: float = 1.0
    compactness_weight: float = 1.0
    sample_count: int = 0

    def update_duration(self, category: str, estimated_minutes: int, actual_minutes: int) -> None:
        self.duration_by_category.setdefault(category, DurationPosterior()).update(estimated_minutes, actual_minutes)
        self.sample_count += 1

    def update_execution(self, time_bucket: str, outcome: str) -> None:
        if outcome == "UNKNOWN":
            return
        if outcome not in {"COMPLETED", "PARTIALLY_COMPLETED", "SKIPPED", "DELAYED"}:
            raise ValueError("unsupported execution outcome")
        posterior = self.execution_by_time_bucket.setdefault(time_bucket, BetaPosterior())
        posterior.update(outcome in {"COMPLETED", "PARTIALLY_COMPLETED"}, 1.0 if outcome != "PARTIALLY_COMPLETED" else 0.5)
        self.sample_count += 1

    def update_latent(self, observations: list[float], retention: float = 0.85) -> None:
        if len(observations) != len(self.latent_state) or not 0.0 <= retention <= 1.0:
            raise ValueError("invalid latent-state update")
        self.latent_state = [retention * old + (1.0 - retention) * new for old, new in zip(self.latent_state, observations)]

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

