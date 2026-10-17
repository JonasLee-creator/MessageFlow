from __future__ import annotations

import math

import torch
from torch import Tensor
import torch.nn.functional as functional


def masked_lognormal_nll(parameters: Tensor, target_minutes: Tensor, mask: Tensor) -> Tensor:
    mu, sigma = parameters[..., 0], parameters[..., 1].clamp_min(1e-5)
    safe_target = target_minutes.clamp_min(1.0)
    log_target = safe_target.log()
    per_row = log_target + sigma.log() + 0.5 * math.log(2.0 * math.pi) + 0.5 * ((log_target - mu) / sigma).square()
    return _masked_mean(per_row, mask)


def masked_execution_bce(logits: Tensor, outcomes: Tensor, mask: Tensor, positive_weight: Tensor | None = None) -> Tensor:
    per_slot = functional.binary_cross_entropy_with_logits(
        logits,
        outcomes.clamp(0.0, 1.0),
        reduction="none",
        pos_weight=positive_weight,
    )
    return _masked_mean(per_slot, mask)


def multitask_loss(
    duration_parameters: Tensor,
    duration_target: Tensor,
    duration_mask: Tensor,
    execution_logits: Tensor,
    execution_target: Tensor,
    execution_mask: Tensor,
    duration_weight: float,
    execution_weight: float,
) -> tuple[Tensor, dict[str, Tensor]]:
    duration = masked_lognormal_nll(duration_parameters, duration_target, duration_mask)
    execution = masked_execution_bce(execution_logits, execution_target, execution_mask)
    total = duration_weight * duration + execution_weight * execution
    return total, {"loss": total.detach(), "duration_nll": duration.detach(), "execution_bce": execution.detach()}


def _masked_mean(values: Tensor, mask: Tensor) -> Tensor:
    weights = mask.to(values.dtype)
    count = weights.sum()
    if count.item() == 0:
        return values.sum() * 0.0
    return (values * weights).sum() / count

