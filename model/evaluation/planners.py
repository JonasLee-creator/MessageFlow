from __future__ import annotations

import math
from datetime import timedelta
from statistics import NormalDist

from .domain import Block, uniform
from .metrics import cvar, disruption, mean
from .predictor import bucket, quantile


METHODS = ('edf','priority_edf','deterministic','probabilistic','global_probability','personalized','risk_aware','drp_full')


def build_schedule(tasks, progress, completed, now, horizon, fixed, old, origin, config,
                   durations, probabilities, order, personalized, used, *, preserve_old=False,
                   preference_minutes=1440, continuity=True):
    step = config['slot_minutes']
    freeze = config['freeze_minutes']
    at = lambda m: origin+timedelta(minutes=m)
    # All methods obey the same near-term commitments and fixed-event constraints.
    locked = [b for b in old if b.end>now and (preserve_old or b.start<now+freeze) and b.task_id not in completed]
    result = list(locked)
    day_load = dict(used)
    for b in locked:
        for m in range(max(now,b.start),b.end,step):
            day = at(m).date().isoformat()
            day_load[day] = day_load.get(day,0)+step
    remaining = {}
    for task in tasks:
        committed = sum(max(0,b.end-max(now,b.start)) for b in locked if b.task_id==task.id)
        retained = progress.get(task.id,0)
        if continuity and not task.splittable:
            first_locked = min((b.start for b in locked if b.task_id==task.id),default=now)
            if first_locked>now:
                retained = 0
        remaining[task.id] = max(0,durations[task.id]-retained-committed)
    def rank(task):
        deadline = task.deadline if task.deadline is not None else horizon+20160
        if order == 'edf':
            return deadline,task.id
        if order == 'priority_edf':
            slack = deadline-now-remaining[task.id]
            return slack/max(1,task.priority),deadline,task.id
        # Short, important, low-slack work first; fixed before examining outcomes.
        return (deadline-now-remaining[task.id])/max(1,task.priority),remaining[task.id],task.id
    for task in sorted((t for t in tasks if t.id not in completed),key=rank):
        need = math.ceil(remaining[task.id]/step)*step
        if need<=0:
            continue
        # Non-splittable continuation must adjoin its frozen commitment.
        prior = [b for b in locked if b.task_id==task.id]
        start_at = max(now,task.available,task.earliest)
        if not task.splittable and prior:
            start_at = max(b.end for b in prior)
        candidates = []
        for start in range(math.ceil(start_at/step)*step,horizon,step):
            length = need
            if continuity and not task.splittable and not prior and start>now:
                length = math.ceil(durations[task.id]/step)*step
            end = start+(step if task.splittable else length)
            if end>horizon:
                continue
            if not task.splittable and prior and start != start_at:
                continue
            if any(start<e and s<end for s,e in fixed) or any(start<b.end and b.start<end for b in result):
                continue
            minutes = list(range(start,end,step))
            days = [at(m).date().isoformat() for m in minutes]
            if any(not config['working_hours'][0] <= at(m).hour < config['working_hours'][1] for m in minutes):
                continue
            if any(day_load.get(d,0)+days.count(d)*step>config['daily_capacity_minutes'] for d in set(days)):
                continue
            p = probabilities[task.id][bucket(at(start))] if personalized else 1.
            score = start-now + (1-p)*preference_minutes if personalized else start-now
            candidates.append((score,start,end))
        for _,start,end in sorted(candidates):
            if need<=0:
                break
            if any(start<b.end and b.start<end for b in result):
                continue
            days = [at(m).date().isoformat() for m in range(start,end,step)]
            if any(day_load.get(d,0)+days.count(d)*step>config['daily_capacity_minutes'] for d in set(days)):
                continue
            result.append(Block(task.id,start,end))
            for d in days:
                day_load[d] = day_load.get(d,0)+step
            need -= end-start
    return sorted(result,key=lambda b:b.start)


def predicted_loss(plan,tasks,progress,predictions,now,horizon,origin,config,sample):
    losses = []
    for task in tasks:
        mu,sigma,probabilities = predictions[task.id]
        # Conditional remaining duration after observed survival/overrun.
        known = progress.get(task.id,0)
        if not task.splittable:
            first_start=min((max(now,b.start) for b in plan if b.task_id==task.id and b.end>now),default=horizon)
            if first_start>now:
                known=0.
        normal = NormalDist()
        lower = normal.cdf((math.log(max(.001,known))-mu)/sigma) if known else 0.
        u = lower+(1-lower)*uniform('duration',sample,task.id)
        total = quantile(mu,sigma,max(.000001,min(.999999,u)))
        work,finish,last_end = known,None,None
        for b in plan:
            if b.task_id != task.id:
                continue
            if not task.splittable and last_end is not None and b.start!=last_end:
                work = 0.
            for minute in range(max(now,b.start),b.end,config['slot_minutes']):
                p = probabilities[bucket(origin+timedelta(minutes=minute))]
                if uniform('execution',sample,task.id,minute)<p:
                    work += config['slot_minutes']
                elif not task.splittable:
                    work = 0.
                if work>=total:
                    finish = minute+config['slot_minutes']
                    break
            last_end = b.end
            if finish is not None:
                break
        due = task.deadline if task.deadline is not None else horizon
        late = finish is None or finish>due
        unfinished = max(0.,total-work)/total
        losses.append(task.priority*(float(late)+unfinished))
    return sum(losses)/max(1,sum(t.priority for t in tasks))


def plan(method,tasks,progress,completed,now,horizon,fixed,old,origin,config,predictor,history,used,*,control=None):
    tasks = [t for t in tasks if t.id not in completed]
    if not tasks:
        return [],{}
    if method=='drp_full' and config.get('planner_version',1)==5:
        from .adaptive_planner import adaptive_plan
        return adaptive_plan(tasks,progress,completed,now,horizon,fixed,old,origin,config,predictor,history,used,
                             control if control is not None else {})
    if method=='drp_full' and config.get('planner_version',1)==4:
        from .integrated_planner import integrated_plan
        return integrated_plan(tasks,progress,completed,now,horizon,fixed,old,origin,config,predictor,history,used,
                               control if control is not None else {})
    if method=='drp_full' and config.get('planner_version',1)>=3:
        from .stable_planner import stable_plan
        return stable_plan(tasks,progress,completed,now,horizon,fixed,old,origin,config,predictor,history,used,
                           control if control is not None else {})
    if method=='drp_full' and config.get('planner_version',1)>=2:
        from .improved_planner import improved_plan
        return improved_plan(tasks,progress,completed,now,horizon,fixed,old,origin,config,predictor,history,used,
                             control=control)
    personal = method in ('personalized','risk_aware','drp_full')
    if method in ('edf','priority_edf'):
        predictions = {t.id:(math.log(t.estimate),config['duration_sigma_prior'],
            {k:config['execution_probability_prior'] for k in ('morning','afternoon','evening','night')}) for t in tasks}
    else:
        predictions = {t.id:predictor.predict(t,origin,now,history,personal) for t in tasks}
    if method=='probabilistic':
        predictions = {tid:(mu,sigma,{k:config['execution_probability_prior'] for k in p})
                       for tid,(mu,sigma,p) in predictions.items()}
    probs = {tid:p[2] for tid,p in predictions.items()}
    if method in ('edf','priority_edf'):
        duration = {t.id:max(t.estimate,progress.get(t.id,0)+config['slot_minutes']) for t in tasks}
        return build_schedule(tasks,progress,completed,now,horizon,fixed,old,origin,config,
                              duration,probs,method,False,used),{}
    qs = (.5,) if method=='deterministic' else (.5,.8,.95)
    candidates = []
    for q in qs:
        durations = {t.id:max(quantile(*predictions[t.id][:2],q),progress.get(t.id,0)+config['slot_minutes']) for t in tasks}
        for order in ('edf','priority_edf'):
            blocks = build_schedule(tasks,progress,completed,now,horizon,fixed,old,origin,config,
                                    durations,probs,order,personal or method=='global_probability',used)
            # Deterministic shares learned P50, but does not optimize sampled risk.
            if method=='deterministic':
                estimates = {t.id:(math.log(durations[t.id]),.00001,{k:1. for k in probs[t.id]}) for t in tasks}
            else:
                estimates = predictions
            losses = [predicted_loss(blocks,tasks,progress,estimates,now,horizon,origin,config,s)
                      for s in range(config['planning_samples'])]
            movement,_ = disruption(old,blocks,now,config['freeze_minutes'])
            score = mean(losses)
            if method in ('risk_aware','drp_full'):
                score += config['risk_weight']*cvar(losses,config['cvar_alpha'])
            if method=='drp_full':
                score += config['stability_weight']*movement/max(1,horizon-now)
            candidates.append((score,blocks,{'predicted_mean_loss':mean(losses),
                'predicted_cvar':cvar(losses,config['cvar_alpha']),'quantile':q}))
    _,blocks,detail = min(candidates,key=lambda item:item[0])
    old_losses = [predicted_loss(old,tasks,progress,predictions,now,horizon,origin,config,s)
                  for s in range(config['planning_samples'])]
    detail['predicted_old_cvar'] = cvar(old_losses,config['cvar_alpha'])
    detail['predicted_cvar_reduction'] = detail['predicted_old_cvar']-detail['predicted_cvar']
    return blocks,detail
