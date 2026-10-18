"""Offline Android entry point. The feature encoder and optimizer are shared
with evaluation; only ONNX execution crosses into the Android Java runtime.
No HTTP, torch, numpy, dataset, or model training is needed on the device.
"""
import json
import math
from pathlib import Path

from chronoflow_model.config import load_config
from evaluation.model_inputs import predictor_inputs
from evaluation.predictor import BUCKETS, Predictor
from deployment.planning import make_plan, timestamp


class AndroidPredictor(Predictor):
    trained = True

    def __init__(self, config, bridge, artifacts):
        super().__init__(config)
        self.bridge = bridge
        self.features = load_config(Path(artifacts) / 'feature_config.json').features

    def base(self, task, origin, now):
        key = (task, origin, now)
        if key not in self.cache:
            inputs = predictor_inputs(task, origin, now, self.features)
            raw = json.loads(str(self.bridge.infer(json.dumps(inputs, allow_nan=False))))
            duration, logits = raw['duration_parameters'], raw['execution_logits']
            if (len(duration) != 2 or len(logits) != 4 or
                    any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in duration + logits)):
                raise ValueError('invalid trained model output')
            mu, sigma = duration
            probabilities = dict(zip(BUCKETS, (1 / (1 + math.exp(-max(-60., min(60., x)))) for x in logits)))
            self.cache[key] = (max(-3., min(math.log(20160), mu)), max(.08, min(2., sigma)), probabilities)
        return self.cache[key]


def run(payload_json, bridge, artifacts, now_iso=None):
    payload = json.loads(payload_json)
    result = make_plan(payload, lambda config: AndroidPredictor(config, bridge, artifacts),
                       now=timestamp(now_iso) if now_iso else None)
    result['engine'] = 'chronoflow-local'
    result['explanation'] = '手机内的训练模型预测耗时与执行概率，结合课表、截止风险和计划稳定性生成安排。'
    return json.dumps(result, ensure_ascii=False, allow_nan=False)
