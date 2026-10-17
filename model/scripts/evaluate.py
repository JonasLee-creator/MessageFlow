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
from chronoflow_model.training import load_checkpoint, run_epoch


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a frozen ChronoFlow checkpoint.")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "base.json")
    args = parser.parse_args()
    config = load_config(args.config)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = ChronoFlowPredictor(config).to(device)
    checkpoint = load_checkpoint(args.checkpoint, model, device)
    dataset = TaskDataset(args.data, config)
    loader = DataLoader(dataset, batch_size=config.training.batch_size, shuffle=False,
        collate_fn=partial(collate_tasks, slot_feature_dim=config.features.slot_feature_dim))
    metrics = run_epoch(model, loader, config, device, None)
    print({"checkpoint_epoch": checkpoint.get("epoch"), "records": len(dataset), "metrics": metrics})


if __name__ == "__main__":
    main()

