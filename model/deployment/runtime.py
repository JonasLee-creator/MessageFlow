from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path

from chronoflow_model.config import load_config
from evaluation.model_inputs import predictor_inputs
from evaluation.predictor import BUCKETS, Predictor

ARTIFACTS = Path(__file__).resolve().parent/'artifacts'


def verified_artifacts(folder=ARTIFACTS):
    manifest = json.loads((folder/'checksums.json').read_text(encoding='utf-8'))
    for name, expected in manifest.items():
        if Path(name).name != name:
            raise ValueError('invalid artifact manifest')
        if hashlib.sha256((folder/name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'model artifact checksum mismatch: {name}')
    return manifest


def load_session(folder=ARTIFACTS):
    verified_artifacts(folder)
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    return ort.InferenceSession(str(folder/'chronoflow_predictor.onnx'),
        sess_options=options, providers=['CPUExecutionProvider'])


class OnnxPredictor(Predictor):
    trained = True
    def __init__(self, config, session, folder=ARTIFACTS):
        super().__init__(config)
        self.session = session
        self.features = load_config(folder/'feature_config.json').features

    def base(self, task, origin, now):
        import numpy as np
        key = (task, origin, now)
        if key not in self.cache:
            values = predictor_inputs(task, origin, now, self.features)
            feed = {name:np.asarray(value, dtype=np.int64 if name in ('category_id','course_id') else np.float32)
                    for name,value in values.items()}
            duration, logits = self.session.run(['duration_parameters','execution_logits'], feed)
            if duration.shape != (1,2) or logits.shape != (1,4) or not np.isfinite(duration).all() or not np.isfinite(logits).all():
                raise ValueError('invalid trained model output')
            mu, sigma = map(float,duration[0])
            probabilities = dict(zip(BUCKETS, (1/(1+np.exp(-np.clip(logits[0],-60,60)))).tolist()))
            self.cache[key] = (max(-3.,min(math.log(20160),mu)), max(.08,min(2.,sigma)), probabilities)
        return self.cache[key]
