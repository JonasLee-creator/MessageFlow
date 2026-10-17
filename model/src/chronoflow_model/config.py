from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FeatureConfig:
    hash_dim: int
    ngram_min: int
    ngram_max: int
    category_count: int
    category_embedding_dim: int
    course_hash_buckets: int
    course_embedding_dim: int
    numeric_feature_dim: int
    user_state_dim: int
    slot_feature_dim: int


@dataclass(frozen=True)
class NetworkConfig:
    hash_projection_dim: int
    encoder_hidden_dims: tuple[int, ...]
    task_embedding_dim: int
    head_hidden_dim: int
    dropout: float
    minimum_sigma: float
    maximum_sigma: float


@dataclass(frozen=True)
class TrainingConfig:
    batch_size: int
    epochs: int
    learning_rate: float
    weight_decay: float
    duration_loss_weight: float
    execution_loss_weight: float
    early_stopping_patience: int


@dataclass(frozen=True)
class PlanningConfig:
    slot_minutes: int
    horizon_days: int
    freeze_minutes: int
    scenario_count: int
    cvar_alpha: float


@dataclass(frozen=True)
class ModelConfig:
    schema_version: int
    model_version: str
    seed: int
    features: FeatureConfig
    network: NetworkConfig
    training: TrainingConfig
    planning: PlanningConfig


def load_config(path: str | Path) -> ModelConfig:
    raw: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise ValueError("unsupported model configuration schema")
    feature = FeatureConfig(**raw["features"])
    network_raw = dict(raw["network"])
    network_raw["encoder_hidden_dims"] = tuple(network_raw["encoder_hidden_dims"])
    config = ModelConfig(
        schema_version=raw["schema_version"],
        model_version=str(raw["model_version"]),
        seed=int(raw["seed"]),
        features=feature,
        network=NetworkConfig(**network_raw),
        training=TrainingConfig(**raw["training"]),
        planning=PlanningConfig(**raw["planning"]),
    )
    _validate(config)
    return config


def _validate(config: ModelConfig) -> None:
    f = config.features
    n = config.network
    t = config.training
    p = config.planning
    if f.hash_dim < 128 or f.ngram_min < 1 or f.ngram_max < f.ngram_min:
        raise ValueError("invalid text feature configuration")
    if min(f.category_count, f.course_hash_buckets, f.numeric_feature_dim, f.user_state_dim, f.slot_feature_dim) <= 0:
        raise ValueError("feature dimensions must be positive")
    if not 0.0 <= n.dropout < 1.0 or not 0.0 < n.minimum_sigma <= n.maximum_sigma:
        raise ValueError("invalid network regularization or sigma range")
    if t.batch_size <= 0 or t.epochs <= 0 or t.learning_rate <= 0:
        raise ValueError("invalid training configuration")
    if p.slot_minutes <= 0 or p.horizon_days <= 0 or p.scenario_count <= 0 or not 0.0 < p.cvar_alpha < 1.0:
        raise ValueError("invalid planning configuration")

