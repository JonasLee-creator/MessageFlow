"""Survival-conditioned budgets and prefix-preserving repair proposals.

Inputs are public task attributes and observed progress, never simulator truth.
"""
from __future__ import annotations

import math
from statistics import NormalDist
from datetime import timedelta

from .domain import Block
from .predictor import quantile
from .predictor import bucket


def conditional_total(mu,sigma,observed,q,step):
    """Q(T | T > observed), not the unconditional quantile plus observed work."""
    if not all(math.isfinite(v) for v in (mu,sigma,observed,q,step)) or sigma<=0 or not 0<q<1 or observed<0 or step<=0:
        raise ValueError('invalid conditional duration parameters')
    lower=NormalDist().cdf((math.log(observed)-mu)/sigma) if observed>0 else 0.
    probability=min(1-1e-10,max(1e-10,lower+(1-lower)*q))
    # The predictor has a finite export range. Observed work is authoritative if
    # it exceeds that range; reserve one further slot rather than negative work.
    return max(observed+step,quantile(mu,sigma,probability))


def duration_budgets(tasks,progress,predictions,q,step,execution_buffer=False,execution_rates=None):
    result={}
    for task in tasks:
        known=progress.get(task.id,0.)
        total=conditional_total(*predictions[task.id][:2],known,q,step)
        if execution_buffer and task.splittable:
            probabilities=predictions[task.id][2].values()
            p=(execution_rates[task.id] if execution_rates is not None else
               sum(probabilities)/len(predictions[task.id][2]))
            p=max(.5,p)
            total=known+(total-known)/p
        result[task.id]=total
    return result


def feasible_execution_rates(tasks,predictions,now,horizon,fixed,old,origin,config,used):
    """Average only over usable task windows, not unavailable night buckets."""
    step=config['slot_minutes']
    rates={}
    for task in tasks:
        end=min(horizon,task.deadline) if task.deadline is not None and task.deadline>now else horizon
        values=[]
        start=math.ceil(max(now,task.available,task.earliest)/step)*step
        for minute in range(start,end-step+1,step):
            at=origin+timedelta(minutes=minute)
            last=origin+timedelta(minutes=minute+step-1)
            if not (config['working_hours'][0]<=at.hour<config['working_hours'][1] and
                    config['working_hours'][0]<=last.hour<config['working_hours'][1]):
                continue
            if used.get(at.date().isoformat(),0)>=config['daily_capacity_minutes']:
                continue
            if any(minute<e and s<minute+step for s,e in fixed):
                continue
            if any(b.task_id!=task.id and minute<b.end and b.start<minute+step for b in old):
                continue
            values.append(predictions[task.id][2][bucket(at)])
        # No current slot does not imply zero ability; leave feasibility to the builder.
        rates[task.id]=sum(values)/len(values) if values else config['execution_probability_prior']
    return rates


def trim_unfrozen_tails(old,tasks,progress,budgets,now,freeze,step):
    """Trim only surplus splittable suffixes; keep frozen and continuous work intact."""
    by_id={t.id:t for t in tasks}
    protected=[b for b in old if b.task_id in by_id and b.end>now and b.start<now+freeze]
    future=[b for b in old if b.task_id in by_id and b.end>now and b.start>=now+freeze]
    used={tid:sum(max(0,b.end-max(now,b.start)) for b in protected if b.task_id==tid) for tid in by_id}
    retained=list(protected)
    for block in sorted(future,key=lambda b:b.start):
        task=by_id[block.task_id]
        if not task.splittable:
            retained.append(block)
            continue
        remaining=max(0.,budgets[task.id]-progress.get(task.id,0)-used[task.id])
        keep=min(block.end-block.start,math.ceil(remaining/step)*step)
        if keep:
            retained.append(Block(block.task_id,block.start,block.start+keep))
            used[task.id]+=keep
    return sorted(retained,key=lambda b:b.start)


def incremental_candidates(tasks,progress,completed,now,horizon,fixed,old,origin,config,predictions,used):
    from .planners import build_schedule
    probabilities={tid:values[2] for tid,values in predictions.items()}
    step=config['slot_minutes']
    execution_rates=feasible_execution_rates(tasks,predictions,now,horizon,fixed,old,origin,config,used)
    candidates=[]
    # Missing work is added without evicting any existing reservation.
    for q in (.5,.8):
        budgets=duration_budgets(tasks,progress,predictions,q,step,execution_buffer=True,execution_rates=execution_rates)
        blocks=build_schedule(tasks,progress,completed,now,horizon,fixed,old,origin,config,
            budgets,probabilities,'edf',False,used,preserve_old=True,continuity=True)
        candidates.append((f'topup_p{q}',blocks,'incremental'))
    # Free only unfrozen surplus suffixes, then insert missing work into the gaps.
    budgets=duration_budgets(tasks,progress,predictions,.8,step,execution_buffer=True,execution_rates=execution_rates)
    retained=trim_unfrozen_tails(old,tasks,progress,budgets,now,config['freeze_minutes'],step)
    blocks=build_schedule(tasks,progress,completed,now,horizon,fixed,retained,origin,config,
        budgets,probabilities,'priority_edf',False,used,preserve_old=True,continuity=True)
    candidates.append(('trim_and_fill_p80',blocks,'incremental'))
    return candidates
