from __future__ import annotations

import argparse
from functools import partial
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch
from torch.utils.data import DataLoader

from chronoflow_model.config import load_config
from chronoflow_model.dataset import TaskDataset, collate_tasks
from chronoflow_model.network import ChronoFlowPredictor
from chronoflow_model.training import run_epoch, save_checkpoint, seed_everything


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the global ChronoFlow predictor. This runs only when invoked explicitly.")
    parser.add_argument("--data", type=Path, required=True, help="Directory containing train.jsonl and validation.jsonl")
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "base.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args()
    config = load_config(args.config)
    seed_everything(config.seed)
    device = torch.device("cuda" if args.device == "cuda" or (args.device == "auto" and torch.cuda.is_available()) else "cpu")
    collate = partial(collate_tasks, slot_feature_dim=config.features.slot_feature_dim)
    train_data = TaskDataset(args.data / "train.jsonl", config)
    validation_data = TaskDataset(args.data / "validation.jsonl", config)
    train_loader = DataLoader(train_data, batch_size=config.training.batch_size, shuffle=True, collate_fn=collate)
    validation_loader = DataLoader(validation_data, batch_size=config.training.batch_size, shuffle=False, collate_fn=collate)
    model = ChronoFlowPredictor(config).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.training.learning_rate, weight_decay=config.training.weight_decay)
    best = float("inf")
    stale = 0
    for epoch in range(1, config.training.epochs + 1):
        training = run_epoch(model, train_loader, config, device, optimizer)
        validation = run_epoch(model, validation_loader, config, device, None)
        print({"epoch": epoch, "train": training, "validation": validation, "device": str(device)})
        if validation["loss"] < best:
            best = validation["loss"]
            stale = 0
            save_checkpoint(args.output / "chronoflow_best.pt", model, optimizer, config, epoch, validation)
        else:
            stale += 1
            if stale >= config.training.early_stopping_patience:
                break


if __name__ == "__main__":
    main()

