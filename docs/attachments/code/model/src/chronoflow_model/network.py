from __future__ import annotations

import torch
from torch import Tensor, nn
import torch.nn.functional as functional

from .config import ModelConfig


class TaskEncoder(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        f = config.features
        n = config.network
        self.hash_projection = nn.Linear(f.hash_dim, n.hash_projection_dim)
        self.category_embedding = nn.Embedding(f.category_count, f.category_embedding_dim)
        self.course_embedding = nn.Embedding(f.course_hash_buckets, f.course_embedding_dim)
        input_dim = n.hash_projection_dim + f.category_embedding_dim + f.course_embedding_dim + f.numeric_feature_dim
        layers: list[nn.Module] = []
        previous = input_dim
        for hidden in n.encoder_hidden_dims:
            layers.extend((nn.Linear(previous, hidden), nn.SiLU(), nn.Dropout(n.dropout)))
            previous = hidden
        layers.append(nn.Linear(previous, n.task_embedding_dim))
        self.encoder = nn.Sequential(*layers)

    def forward(self, hashed_text: Tensor, category_id: Tensor, course_id: Tensor, numeric: Tensor) -> Tensor:
        text = functional.silu(self.hash_projection(hashed_text))
        category = self.category_embedding(category_id)
        course = self.course_embedding(course_id)
        return self.encoder(torch.cat((text, category, course, numeric), dim=-1))


class DurationHead(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        n = config.network
        self.minimum_sigma = n.minimum_sigma
        self.maximum_sigma = n.maximum_sigma
        self.layers = nn.Sequential(
            nn.Linear(n.task_embedding_dim + config.features.user_state_dim, n.head_hidden_dim),
            nn.SiLU(),
            nn.Dropout(n.dropout),
            nn.Linear(n.head_hidden_dim, 2),
        )

    def forward(self, task_embedding: Tensor, user_state: Tensor) -> Tensor:
        raw = self.layers(torch.cat((task_embedding, user_state), dim=-1))
        mu = raw[..., :1]
        sigma = (functional.softplus(raw[..., 1:2]) + self.minimum_sigma).clamp(max=self.maximum_sigma)
        return torch.cat((mu, sigma), dim=-1)


class ExecutionHead(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        n = config.network
        f = config.features
        self.layers = nn.Sequential(
            nn.Linear(n.task_embedding_dim + f.user_state_dim + f.slot_feature_dim, n.head_hidden_dim),
            nn.SiLU(),
            nn.Dropout(n.dropout),
            nn.Linear(n.head_hidden_dim, 1),
        )

    def forward(self, task_embedding: Tensor, slot_user_state: Tensor, slot_features: Tensor) -> Tensor:
        slot_count = slot_features.shape[1]
        task = task_embedding.unsqueeze(1).expand(-1, slot_count, -1)
        return self.layers(torch.cat((task, slot_user_state, slot_features), dim=-1)).squeeze(-1)


class ChronoFlowPredictor(nn.Module):
    """Global frozen predictor. Personal state is supplied as an explicit input."""

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.task_encoder = TaskEncoder(config)
        self.duration_head = DurationHead(config)
        self.execution_head = ExecutionHead(config)

    def forward(
        self,
        hashed_text: Tensor,
        category_id: Tensor,
        course_id: Tensor,
        numeric_features: Tensor,
        user_state: Tensor,
        slot_features: Tensor,
        slot_user_state: Tensor,
    ) -> tuple[Tensor, Tensor]:
        task_embedding = self.task_encoder(hashed_text, category_id, course_id, numeric_features)
        duration_parameters = self.duration_head(task_embedding, user_state)
        execution_logits = self.execution_head(task_embedding, slot_user_state, slot_features)
        return duration_parameters, execution_logits


def duration_quantiles(parameters: Tensor) -> tuple[Tensor, Tensor, Tensor]:
    """Return log-normal P50/P80/P95 in minutes without sampling."""
    mu, sigma = parameters[..., 0], parameters[..., 1]
    p50 = torch.exp(mu)
    p80 = torch.exp(mu + 0.8416212336 * sigma)
    p95 = torch.exp(mu + 1.6448536270 * sigma)
    return p50, p80, p95
