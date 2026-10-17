"""Version 2: continuity-correct scoring, candidate retention, conservative mixture.

No simulator truth is accepted by this module. All candidate schedules are audited.
"""
from __future__ import annotations

from datetime import timedelta
import math
from statistics import NormalDist

from .domain import uniform
from .metrics import cvar,disruption,feasibility,mean
from .predictor import bucket,quantile


def rollout_loss(blocks,tasks,progress,predictions,now,horizon,origin,config,sample,*,components=False):
    """Same reset semantics as replay, with deadline loss as the primary outcome."""
    step=config['slot_minutes']
    weight=sum(t.priority for t in tasks) or 1
    due_weight=sum(t.priority for t in tasks if t.deadline is not None and t.deadline<=horizon)
    deadline_loss,unfinished,response=0.,0.,0.
    for task in tasks:
        parts=sorted((b for b in blocks if b.task_id==task.id and b.end>now),key=lambda b:b.start)
        known=progress.get(task.id,0)
        if not task.splittable and (not parts or parts[0].start>now):
            known=0.
        mu,sigma,probabilities=predictions[task.id]
        lower=NormalDist().cdf((math.log(max(.001,known))-mu)/sigma) if known else 0.
        u=lower+(1-lower)*uniform('v2-duration',config['seed'],sample,task.id)
        total=quantile(mu,sigma,max(1e-6,min(1-1e-6,u)))
        work,finish,last_end=known,None,now
        for block in parts:
            start=max(now,block.start)
            if not task.splittable and start!=last_end:
                work=0.
            for minute in range(start,block.end,step):
                p=probabilities[bucket(origin+timedelta(minutes=minute))]
                if uniform('v2-execution',config['seed'],sample,task.id,minute)<p:
                    gain=min(step,max(0.,total-work))
                    work+=gain
                    if work>=total:
                        finish=minute+gain
                        break
                elif not task.splittable:
                    work=0.
            last_end=block.end
            if finish is not None:
                break
        if task.deadline is not None and task.deadline<=horizon:
            deadline_loss+=task.priority*int(finish is None or finish>task.deadline)
        unfinished+=task.priority*max(0.,total-work)/max(1.,total)
        response+=task.priority*(min(horizon,finish if finish is not None else horizon)-now)/max(1,horizon-now)
    if components:
        return {'deadline':deadline_loss/(due_weight or 1),
                'unfinished':unfinished/weight,'response':response/weight}
    return (deadline_loss/(due_weight or 1)
            +config['unfinished_weight']*unfinished/weight
            +config['response_weight']*response/weight)


def improved_plan(tasks,progress,completed,now,horizon,fixed,old,origin,config,predictor,history,used):
    from .planners import build_schedule
    predictions={t.id:predictor.predict(t,origin,now,history,True) for t in tasks}
    probabilities={tid:values[2] for tid,values in predictions.items()}
    prior={t.id:(math.log(t.estimate),config['duration_sigma_prior'],
        {key:config['execution_probability_prior'] for key in probabilities[t.id]}) for t in tasks}
    # A cold-start learned predictor can be miscalibrated. Evaluate a fixed mixture
    # with the user-estimate prior, rather than assuming perfect neural calibration.
    observations=history.get('_duration',(0.,0))[1]
    weight=config['cold_start_model_weight']
    weight=weight+(1-weight)*observations/(observations+8)
    candidates={}
    def add(name,durations,order='edf',personal=False,preserve=False):
        blocks=build_schedule(tasks,progress,completed,now,horizon,fixed,old,origin,config,
            durations,probabilities,order,personal,used,preserve_old=preserve,
            preference_minutes=config['preference_delay_minutes'],continuity=True)
        if feasibility(blocks,tasks,fixed,config['daily_capacity_minutes'],lambda m:origin+timedelta(minutes=m)):
            return
        _,frozen=disruption([b for b in old if b.task_id not in completed],blocks,now,config['freeze_minutes'])
        if frozen:
            return
        key=tuple((b.task_id,b.start,b.end) for b in blocks)
        candidates.setdefault(key,(name,blocks))
    estimated={t.id:max(t.estimate,progress.get(t.id,0)+config['slot_minutes']) for t in tasks}
    add('edf_estimate',estimated)
    add('retain_and_fill',estimated,preserve=True)
    for q in (.5,.8,.95):
        durations={t.id:max(quantile(*predictions[t.id][:2],q),progress.get(t.id,0)+config['slot_minutes']) for t in tasks}
        for order in ('edf','priority_edf'):
            add(f'p{q}-{order}',durations,order)
            add(f'p{q}-{order}-preference',durations,order,True)
        # Reserve execution time for splittable work; do not exponentially inflate
        # non-splittable tasks into an impossible all-day reservation.
        budgets={t.id:durations[t.id]/max(.5,mean(probabilities[t.id].values())) if t.splittable else durations[t.id]
                 for t in tasks}
        add(f'p{q}-execution_buffer',budgets)
    def losses(blocks):
        values=[]
        for s in range(config['planning_samples']):
            # Stratify the mixture instead of averaging two different worlds,
            # which would artificially reduce the tail risk.
            distribution=predictions if (s+.5)/config['planning_samples']<weight else prior
            values.append(rollout_loss(blocks,tasks,progress,distribution,now,horizon,origin,config,s))
        return values
    old_valid=[b for b in old if b.task_id not in completed and b.end>now]
    old_losses=losses(old_valid)
    scored=[]
    for name,blocks in candidates.values():
        values=losses(blocks)
        movement,_=disruption(old_valid,blocks,now,config['freeze_minutes'])
        # Movement in task-work units, not divided by an arbitrary shrinking horizon.
        scale=max(config['slot_minutes'],sum(t.estimate for t in tasks))
        stability=movement/scale if old_valid else 0.
        primary=mean(values)+config['risk_weight']*cvar(values,config['cvar_alpha'])
        score=primary+config['stability_weight']*stability
        scored.append((score,movement,name,blocks,values,primary))
    if not scored:
        raise ValueError('No feasible candidate, including EDF fallback; inspect input commitments')
    # Stability is a secondary objective: it must not buy a large deterioration
    # in predicted completion/risk merely by preserving an obsolete schedule.
    best_primary=min(item[5] for item in scored)
    admissible=[item for item in scored if item[5]<=best_primary+config['primary_loss_tolerance']]
    score,_,name,blocks,values,primary=min(admissible,key=lambda item:(item[0],item[1],item[2]))
    return blocks,{'planner_version':2,'candidate':name,'candidate_count':len(scored),
        'selection_score':score,'model_weight':weight,'predicted_mean_loss':mean(values),
        'primary_loss':primary,'best_primary_loss':best_primary,'admissible_candidates':len(admissible),
        'predicted_cvar':cvar(values,config['cvar_alpha']),
        'predicted_old_cvar':cvar(old_losses,config['cvar_alpha']),
        'predicted_cvar_reduction':cvar(old_losses,config['cvar_alpha'])-cvar(values,config['cvar_alpha'])}
