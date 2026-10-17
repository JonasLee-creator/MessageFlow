from __future__ import annotations

import argparse
from functools import partial
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT/'src')]


def main():
    import torch
    from torch.utils.data import DataLoader
    from chronoflow_model.config import load_config
    from chronoflow_model.dataset import TaskDataset,collate_tasks
    from chronoflow_model.network import ChronoFlowPredictor
    from chronoflow_model.training import MODEL_INPUTS,load_checkpoint
    from evaluation.prediction_metrics import binary_metrics,duration_metrics
    parser = argparse.ArgumentParser(description='Prediction metrics versus train-only baselines')
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--train-data',type=Path,required=True)
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=ROOT/'config/base.json')
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists')
    config = load_config(args.config)
    train = TaskDataset(args.train_data,config)
    test = TaskDataset(args.data,config)
    durations = [r.actual_work_minutes for r in train.records if r.actual_work_minutes is not None]
    labels = [s.outcome for r in train.records for s in r.slot_samples if s.outcome is not None]
    if not durations or not labels:
        parser.error('training reference lacks duration or execution labels')
    import math
    mu = statistics.mean(math.log(t) for t in durations)
    sigma = max(.08,statistics.pstdev(math.log(t) for t in durations))
    rate = statistics.mean(labels)
    model = ChronoFlowPredictor(config)
    load_checkpoint(args.checkpoint,model,torch.device('cpu'))
    model.eval()
    parameters,targets,probabilities,outcomes = [],[],[],[]
    loader = DataLoader(test,batch_size=config.training.batch_size,collate_fn=partial(collate_tasks,slot_feature_dim=config.features.slot_feature_dim))
    with torch.no_grad():
        for batch in loader:
            duration,logits = model(*(batch[k] for k in MODEL_INPUTS))
            mask = batch['duration_mask']
            parameters.extend(duration[mask].tolist())
            targets.extend(batch['duration_target'][mask].tolist())
            mask = batch['execution_mask']
            probabilities.extend(torch.sigmoid(logits)[mask].tolist())
            outcomes.extend(batch['execution_target'][mask].tolist())
    report = {'data':str(args.data),'duration':duration_metrics(parameters,targets),
        'execution':binary_metrics(probabilities,outcomes),
        'train_lognormal_baseline':duration_metrics([(mu,sigma)]*len(targets),targets),
        'train_median_mae_minutes':statistics.mean(abs(t-statistics.median(durations)) for t in targets) if targets else None,
        'train_rate_baseline':binary_metrics([rate]*len(outcomes),outcomes),
        'half_probability_baseline':binary_metrics([.5]*len(outcomes),outcomes)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
