from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import random
from typing import Any, Iterable

import numpy as np
import torch
from torch import Tensor

from .config import ModelConfig
from .losses import multitask_loss
from .network import ChronoFlowPredictor


MODEL_INPUTS = ("hashed_text", "category_id", "course_id", "numeric_features", "user_state", "slot_features", "slot_user_state")


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def run_epoch(
    model: ChronoFlowPredictor,
    batches: Iterable[dict[str, Any]],
    config: ModelConfig,
    device: torch.device,
    optimizer: torch.optim.Optimizer | None,
) -> dict[str, float]:
    training = optimizer is not None
    model.train(training)
    totals: defaultdict[str, float] = defaultdict(float)
    batch_count = 0
    context = torch.enable_grad() if training else torch.no_grad()
    with context:
        for raw_batch in batches:
            batch = move_batch(raw_batch, device)
            duration, execution = model(*(batch[name] for name in MODEL_INPUTS))
            loss, metrics = multitask_loss(
                duration,
                batch["duration_target"],
                batch["duration_mask"],
                execution,
                batch["execution_target"],
                batch["execution_mask"],
                config.training.duration_loss_weight,
                config.training.execution_loss_weight,
            )
            if training:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
                optimizer.step()
            for name, value in metrics.items():
                totals[name] += float(value.cpu())
            batch_count += 1
    if batch_count == 0:
        raise ValueError("dataset produced no batches")
    return {name: value / batch_count for name, value in totals.items()}


def move_batch(batch: dict[str, Any], device: torch.device) -> dict[str, Any]:
    return {name: value.to(device) if isinstance(value, Tensor) else value for name, value in batch.items()}


def save_checkpoint(
    path: str | Path,
    model: ChronoFlowPredictor,
    optimizer: torch.optim.Optimizer,
    config: ModelConfig,
    epoch: int,
    validation_metrics: dict[str, float],
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "epoch": epoch,
        "validation_metrics": validation_metrics,
        "model_version": config.model_version,
        "config_schema_version": config.schema_version,
    }, target)


def load_checkpoint(path: str | Path, model: ChronoFlowPredictor, device: torch.device) -> dict[str, Any]:
    checkpoint = torch.load(Path(path), map_location=device, weights_only=True)
    model.load_state_dict(checkpoint["model_state_dict"])
    return checkpoint

