"""Conservative causal feedback, one effective observation per work session."""
from __future__ import annotations

import math


class OnlineHistory(dict):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.pending = None
        self.updated_at = {}
        self.errors = {}
        self.session_count = 0

    def factor(self, key, now):
        elapsed = max(0, now-self.updated_at.get(key, now))
        return 2**(-elapsed/self.config['online_half_life_minutes'])

    def adjust(self, mu, probabilities, now):
        probabilities = dict(probabilities)
        for key, p0 in probabilities.items():
            success, count = self.get(key, (0., 0.))
            decay = self.factor(key, now)
            success, count = success*decay, count*decay
            prior = self.config['online_prior_strength']
            posterior = (prior*p0+success)/(prior+count)
            trust = count/(count+self.config['online_trust_sessions'])
            global_error, personal_error, n = self.errors.get(key, (0., 0., 0))
            forget=self.config['online_error_forgetting']
            mass=(1-forget**n)/(1-forget) if n else 1.
            if n >= self.config['online_gate_min_sessions'] and (personal_error-global_error)/mass > self.config['online_gate_margin']:
                trust = 0.
            delta = max(-self.config['online_probability_limit'],
                        min(self.config['online_probability_limit'], trust*(posterior-p0)))
            probabilities[key] = max(1e-7, min(1-1e-7, p0+delta))
        residuals, count = self.get('_duration', (0., 0.))
        decay = self.factor('_duration', now)
        shift = residuals*decay/(self.config['online_duration_prior']+count*decay)
        limit = self.config['online_duration_shift_limit']
        return mu+max(-limit, min(limit, shift)), probabilities

    def observe(self, task_id, time_bucket, minute, step, success, global_probability, personal_probability):
        identity = (task_id, time_bucket)
        if self.pending and (self.pending['identity'] != identity or self.pending['end'] != minute):
            self.flush(minute)
        if self.pending is None:
            self.pending = {'identity':identity, 'end':minute, 'success':0., 'n':0,
                            'global':0., 'personal':0.}
        p = self.pending
        p['end'] = minute+step
        p['success'] += float(success)
        p['n'] += 1
        # Predictions are supplied BEFORE this session's outcomes update parameters.
        p['global'] += global_probability
        p['personal'] += personal_probability

    def flush(self, now):
        if self.pending is None:
            return
        p = self.pending
        key = p['identity'][1]
        target = p['success']/p['n']
        a, n = self.get(key, (0., 0.))
        decay = self.factor(key, now)
        self[key] = (a*decay+target, n*decay+1.)
        self.updated_at[key] = now
        g, u, count = self.errors.get(key, (0., 0., 0))
        forget = self.config['online_error_forgetting']
        self.errors[key] = (forget*g+(p['global']/p['n']-target)**2,
                            forget*u+(p['personal']/p['n']-target)**2, count+1)
        self.session_count += 1
        self.pending = None

    def record_duration(self, observed_minutes, predicted_mu, now):
        if observed_minutes <= 0:
            return
        residual = math.log(observed_minutes)-predicted_mu
        bound = self.config['online_duration_residual_limit']
        residual = max(-bound, min(bound, residual))
        value, count = self.get('_duration', (0., 0.))
        decay = self.factor('_duration', now)
        self['_duration'] = (value*decay+residual, count*decay+1)
        self.updated_at['_duration'] = now
