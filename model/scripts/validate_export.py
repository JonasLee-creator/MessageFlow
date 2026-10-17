from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import onnxruntime as ort
import torch

from chronoflow_model.config import load_config
from chronoflow_model.network import ChronoFlowPredictor
from chronoflow_model.training import load_checkpoint


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare PyTorch and ONNX outputs on fixed synthetic inputs.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--onnx", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "base.json")
    parser.add_argument("--tolerance", type=float, default=1e-4)
    args = parser.parse_args()
    config = load_config(args.config)
    torch.manual_seed(config.seed)
    f = config.features
    inputs = {
        "hashed_text": torch.randn(3, f.hash_dim),
        "category_id": torch.tensor([0, 2, 7], dtype=torch.long),
        "course_id": torch.tensor([1, 25, 300], dtype=torch.long),
        "numeric_features": torch.randn(3, f.numeric_feature_dim),
        "user_state": torch.randn(3, f.user_state_dim),
        "slot_features": torch.randn(3, 5, f.slot_feature_dim),
        "slot_user_state": torch.randn(3, 5, f.user_state_dim),
    }
    model = ChronoFlowPredictor(config)
    load_checkpoint(args.checkpoint, model, torch.device("cpu"))
    model.eval()
    with torch.no_grad():
        expected = model(*inputs.values())
    session = ort.InferenceSession(str(args.onnx), providers=["CPUExecutionProvider"])
    actual = session.run(None, {name: value.numpy() for name, value in inputs.items()})
    errors = [float(np.max(np.abs(reference.numpy() - candidate))) for reference, candidate in zip(expected, actual)]
    if max(errors) > args.tolerance:
        raise RuntimeError(f"ONNX parity failed: max errors={errors}")
    print({"max_absolute_errors": errors, "tolerance": args.tolerance})


if __name__ == "__main__":
    main()

