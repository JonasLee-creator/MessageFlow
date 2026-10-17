from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch

from chronoflow_model.config import load_config
from chronoflow_model.network import ChronoFlowPredictor
from chronoflow_model.training import load_checkpoint


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a trained .pt checkpoint to ONNX.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "base.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    model = ChronoFlowPredictor(config)
    load_checkpoint(args.checkpoint, model, torch.device("cpu"))
    model.eval()
    f = config.features
    batch = 2
    slots = 4
    example = (
        torch.zeros(batch, f.hash_dim, dtype=torch.float32),
        torch.zeros(batch, dtype=torch.long),
        torch.zeros(batch, dtype=torch.long),
        torch.zeros(batch, f.numeric_feature_dim, dtype=torch.float32),
        torch.zeros(batch, f.user_state_dim, dtype=torch.float32),
        torch.zeros(batch, slots, f.slot_feature_dim, dtype=torch.float32),
        torch.zeros(batch, slots, f.user_state_dim, dtype=torch.float32),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model,
        example,
        args.output,
        input_names=("hashed_text", "category_id", "course_id", "numeric_features", "user_state", "slot_features", "slot_user_state"),
        output_names=("duration_parameters", "execution_logits"),
        dynamic_axes={
            "hashed_text": {0: "batch"},
            "category_id": {0: "batch"},
            "course_id": {0: "batch"},
            "numeric_features": {0: "batch"},
            "user_state": {0: "batch"},
            "slot_features": {0: "batch", 1: "slot_count"},
            "slot_user_state": {0: "batch", 1: "slot_count"},
            "duration_parameters": {0: "batch"},
            "execution_logits": {0: "batch", 1: "slot_count"},
        },
        opset_version=17,
        do_constant_folding=True,
    )
    shutil.copyfile(args.config, args.output.parent / "feature_config.json")
    (args.output.parent / "model_metadata.json").write_text(json.dumps({
        "model_version": config.model_version,
        "config_schema_version": config.schema_version,
        "checkpoint": args.checkpoint.name,
        "onnx": args.output.name,
        "trained": True,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print({"onnx": str(args.output), "bytes": args.output.stat().st_size})


if __name__ == "__main__":
    main()

