from __future__ import annotations

import math
from statistics import NormalDist


BUCKETS = ('morning', 'afternoon', 'evening', 'night')


def bucket(at):
    return 'morning' if 6 <= at.hour < 12 else 'afternoon' if 12 <= at.hour < 18 else 'evening' if 18 <= at.hour < 23 else 'night'


class Predictor:
    """Prior predictor, optionally backed by the actual frozen .pt checkpoint.

    History is only feedback from this policy's past simulated attempts. The neural
    user state stays at cold-start zeros: a scenario has no historical user identity.
    Beta updates supply explicit online personalization outside the neural network.
    """
    def __init__(self, config, checkpoint=None, model_config=None):
        self.config = config
        self.model = None
        self.cache = {}
        if checkpoint:
            import torch
            from chronoflow_model.config import load_config
            from chronoflow_model.network import ChronoFlowPredictor
            from chronoflow_model.training import load_checkpoint
            self.torch = torch
            self.mc = load_config(model_config)
            self.model = ChronoFlowPredictor(self.mc)
            load_checkpoint(checkpoint, self.model, torch.device('cpu'))
            self.model.eval()

    def base(self, task, origin, now):
        key = (task, origin, now)
        if key in self.cache:
            return self.cache[key]
        mu = math.log(task.estimate)
        sigma = self.config['duration_sigma_prior']
        probabilities = {k:self.config['execution_probability_prior'] for k in BUCKETS}
        if self.model is not None:
            from .model_inputs import predictor_inputs
            inputs = predictor_inputs(task,origin,now,self.mc.features)
            torch = self.torch
            with torch.no_grad():
                duration, logits = self.model(
                    *(torch.tensor(inputs[name],dtype=torch.long if name in ('category_id','course_id') else torch.float32)
                      for name in ('hashed_text','category_id','course_id','numeric_features','user_state','slot_features','slot_user_state')))
            mu,sigma = duration[0].tolist()
            probabilities = dict(zip(BUCKETS,torch.sigmoid(logits[0]).tolist()))
        value = (max(-3.,min(math.log(20160),mu)),max(.08,min(2.,sigma)),probabilities)
        self.cache[key] = value
        return value

    def predict(self, task, origin, now, history, personalized):
        mu,sigma,probabilities = self.base(task,origin,now)
        probabilities = dict(probabilities)
        if personalized and hasattr(history,'adjust'):
            mu,probabilities = history.adjust(mu,probabilities,now)
            return mu,sigma,probabilities
        if personalized:
            for key,(success,total) in history.items():
                if key == '_duration':
                    mu += success/(4+total)
                else:
                    probabilities[key] = (4*probabilities[key]+success)/(4+total)
        return mu,sigma,probabilities


def quantile(mu,sigma,q):
    return math.exp(min(math.log(20160),mu+sigma*NormalDist().inv_cdf(q)))
