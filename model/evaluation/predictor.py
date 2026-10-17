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
            from datetime import timedelta
            from chronoflow_model.records import TaskRecord
            from chronoflow_model.features import hashed_ngrams, category_index, course_bucket, numeric_features
            categories = {'实验':'EXPERIMENT','报告':'REPORT','编程':'PROGRAMMING','复习':'REVIEW',
                '背诵':'MEMORIZATION','阅读':'READING','考试准备':'EXAM_PREPARATION','其他':'OTHER'}
            at = lambda m: origin+timedelta(minutes=m)
            record = TaskRecord(task.id,'scenario-cold-start',task.title,categories.get(task.category,'OTHER'),
                task.course,task.difficulty,task.priority,task.splittable,0,int(task.estimate),
                at(task.released),at(now),at(task.earliest),at(task.deadline) if task.deadline is not None else None,
                None,None,(0.,)*12,())
            f = self.mc.features
            weekday = 2*math.pi*at(now).weekday()/7
            deadline = 1. if task.deadline is None else max(-1.,min(1.,(task.deadline-now)/20160))
            slots = [[float(i==j) for i in range(4)] + [math.sin(weekday),math.cos(weekday),
                min(1.,task.estimate/180),0.,0.,deadline,min(1.,(now-task.released)/20160),.5] for j in range(4)]
            torch = self.torch
            with torch.no_grad():
                duration, logits = self.model(
                    torch.tensor([hashed_ngrams(task.title,f)],dtype=torch.float32),
                    torch.tensor([category_index(record.category)]),
                    torch.tensor([course_bucket(task.course,f)]),
                    torch.tensor([numeric_features(record,at(now),f.numeric_feature_dim)],dtype=torch.float32),
                    torch.zeros(1,12),torch.tensor([slots],dtype=torch.float32),torch.zeros(1,4,12))
            mu,sigma = duration[0].tolist()
            probabilities = dict(zip(BUCKETS,torch.sigmoid(logits[0]).tolist()))
        value = (max(-3.,min(math.log(20160),mu)),max(.08,min(2.,sigma)),probabilities)
        self.cache[key] = value
        return value

    def predict(self, task, origin, now, history, personalized):
        mu,sigma,probabilities = self.base(task,origin,now)
        probabilities = dict(probabilities)
        if personalized:
            for key,(success,total) in history.items():
                if key == '_duration':
                    mu += success/(4+total)
                else:
                    probabilities[key] = (4*probabilities[key]+success)/(4+total)
        return mu,sigma,probabilities


def quantile(mu,sigma,q):
    return math.exp(min(math.log(20160),mu+sigma*NormalDist().inv_cdf(q)))
