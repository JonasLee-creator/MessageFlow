"""V3: bounded local repair, global cooldown and separate deadline-risk guards."""
from datetime import timedelta
import math

from .improved_planner import rollout_loss
from .metrics import cvar,disruption,feasibility,mean
from .predictor import quantile


def changed_tasks(old,new,now,step):
    """Physical occupancy, independent of equivalent adjacent block encoding."""
    def footprint(blocks):
        result={}
        for b in blocks:
            result.setdefault(b.task_id,set()).update(range(max(now,b.start),b.end,step))
        return result
    left,right=footprint(old),footprint(new)
    return {tid for tid in left.keys()|right.keys() if left.get(tid,set())!=right.get(tid,set())}


def guarded_choice(rows,config):
    """Mean deadline loss and deadline CVaR cannot be traded for stability."""
    anchor=min(rows,key=lambda r:(r['primary'],r['movement']))
    safe=[r for r in rows if
        r['primary']<=anchor['primary']+config['primary_loss_tolerance']+1e-12 and
        r['deadline_mean']<=anchor['deadline_mean']+config['deadline_mean_tolerance']+1e-12 and
        r['deadline_cvar']<=anchor['deadline_cvar']+config['deadline_tail_tolerance']+1e-12]
    selected=min(safe,key=lambda r:(r['score'],r['movement'],r['name']))
    return selected,anchor,len(safe)


def stable_plan(tasks,progress,completed,now,horizon,fixed,old,origin,config,predictor,history,used,control):
    from .planners import build_schedule
    step=config['slot_minutes']
    at=lambda m:origin+timedelta(minutes=m)
    old=[b for b in old if b.end>now and b.task_id not in completed]
    predictions={t.id:predictor.predict(t,origin,now,history,True) for t in tasks}
    probabilities={tid:p[2] for tid,p in predictions.items()}
    prior={t.id:(math.log(t.estimate),config['duration_sigma_prior'],
        {key:config['execution_probability_prior'] for key in probabilities[t.id]}) for t in tasks}
    count=history.get('_duration',(0.,0))[1]
    weight=config['cold_start_model_weight']+(1-config['cold_start_model_weight'])*count/(count+8)
    new_ids={t.id for t in tasks}-set(control.get('known_ids',[]))
    missing={t.id for t in tasks if not any(b.task_id==t.id for b in old)}
    affected=(new_ids|missing|set(control.get('affected',[])))-set(completed)
    ordered=sorted((t for t in tasks if t.id in affected),
                   key=lambda t:(t.deadline if t.deadline is not None else horizon+20160,-t.priority,t.id))
    local_ids={t.id for t in ordered[:config['local_max_affected_tasks']]}
    candidates={}
    def add(name,blocks,stage):
        if feasibility(blocks,tasks,fixed,config['daily_capacity_minutes'],at):
            return
        future_load=dict(used)
        for b in blocks:
            for m in range(max(now,b.start),b.end,step):
                day=at(m).date().isoformat()
                future_load[day]=future_load.get(day,0)+step
        if any(v>config['daily_capacity_minutes'] for v in future_load.values()):
            return
        if disruption(old,blocks,now,config['freeze_minutes'])[1]:
            return
        key=tuple((b.task_id,b.start,b.end) for b in blocks)
        candidates.setdefault(key,{'name':name,'blocks':blocks,'stage':stage})
    add('keep_current',old,'keep')
    for q in ((.5,.8) if config.get('enable_local_repair',True) else ()):
        retained=[b for b in old if b.task_id not in local_ids or b.start<now+config['freeze_minutes']]
        durations={}
        for t in tasks:
            if t.id in local_ids:
                durations[t.id]=max(quantile(*predictions[t.id][:2],q),progress.get(t.id,0)+step)
            else:
                committed=sum(max(0,b.end-max(now,b.start)) for b in retained if b.task_id==t.id)
                first=min((b.start for b in retained if b.task_id==t.id),default=now)
                saved=progress.get(t.id,0) if t.splittable or first<=now else 0.
                durations[t.id]=committed+saved
        blocks=build_schedule(tasks,progress,completed,now,horizon,fixed,retained,origin,config,
            durations,probabilities,'edf',False,used,preserve_old=True,continuity=True)
        if changed_tasks(old,blocks,now,step)<=local_ids:
            add(f'local_p{q}',blocks,'local')

    def score(row):
        components=[]
        for s in range(config['planning_samples']):
            distribution=predictions if (s+.5)/config['planning_samples']<weight else prior
            components.append(rollout_loss(row['blocks'],tasks,progress,distribution,now,horizon,
                                          origin,config,s,components=True))
        values=[v['deadline']+config['unfinished_weight']*v['unfinished']+
                config['response_weight']*v['response'] for v in components]
        movement,_=disruption(old,row['blocks'],now,config['freeze_minutes'])
        primary=mean(values)+config['risk_weight']*cvar(values,config['cvar_alpha'])
        row.update(primary=primary,movement=movement,mean_loss=mean(values),
            cvar=cvar(values,config['cvar_alpha']),deadline_mean=mean(v['deadline'] for v in components),
            deadline_cvar=cvar([v['deadline'] for v in components],config['cvar_alpha']),
            score=primary+config['stability_weight']*movement/max(step,sum(t.estimate for t in tasks)))
        return row
    local=[score(r) for r in candidates.values()]
    urgent=any(t.id in affected and t.deadline is not None and now<t.deadline<=now+config['urgent_deadline_minutes'] for t in tasks)
    cooldown=(config.get('enable_replan_cooldown',True) and
              now-control.get('last_global',-10**9)<config['global_replan_cooldown_minutes'])
    repair_needed=bool(affected)
    # Escalate when local candidates remain risky; urgent events bypass cooldown.
    local_risk=min((r['deadline_mean'] for r in local),default=1.)
    full_allowed=(not config.get('enable_replan_cooldown',True) or 'last_global' not in control or not local or urgent or len(new_ids)>config['local_max_affected_tasks'] or
                  (not cooldown and (repair_needed or local_risk>0)))
    if full_allowed:
        control['last_global']=now
        for q in (.5,.8,.95):
            durations={t.id:max(quantile(*predictions[t.id][:2],q),progress.get(t.id,0)+step) for t in tasks}
            for order in ('edf','priority_edf'):
                for personal in (False,True):
                    blocks=build_schedule(tasks,progress,completed,now,horizon,fixed,old,origin,config,
                        durations,probabilities,order,personal,used,
                        preference_minutes=config['preference_delay_minutes'],continuity=True)
                    add(f'global_p{q}_{order}_{personal}',blocks,'global')
        estimates={t.id:max(t.estimate,progress.get(t.id,0)+step) for t in tasks}
        add('global_edf',build_schedule(tasks,progress,completed,now,horizon,fixed,old,origin,config,
            estimates,probabilities,'edf',False,used),'global')
    rows=[r if 'primary' in r else score(r) for r in candidates.values()]
    if not rows:
        raise ValueError('V3 found no feasible plan; fixed commitments need explicit repair')
    selected,anchor,n_safe=guarded_choice(rows,config)
    previous=next((r for r in rows if r['stage']=='keep'),None)
    rejected=False
    if config.get('enable_low_gain_rejection',True) and previous is not None and selected is not previous and not missing:
        gain=previous['primary']-selected['primary']
        # Apply the same protection to accepting a new plan over the old one.
        protects=(previous['deadline_mean']<=anchor['deadline_mean']+config['deadline_mean_tolerance'] and
                  previous['deadline_cvar']<=anchor['deadline_cvar']+config['deadline_tail_tolerance'] and
                  previous['primary']<=anchor['primary']+config['primary_loss_tolerance'])
        if gain<config['minimum_replan_gain'] and protects:
            selected=previous
            rejected=True
    control['known_ids']=[t.id for t in tasks]
    control['affected']=[]
    detail={'planner_version':3,'candidate':selected['name'],'stage':selected['stage'],
        'candidate_count':len(rows),'admissible_candidates':n_safe,'global_search':int(full_allowed),
        'cooldown_active':int(cooldown),'rejected_low_gain':int(rejected),
        'affected_task_count':len(changed_tasks(old,selected['blocks'],now,step)),
        'primary_loss':selected['primary'],'best_primary_loss':anchor['primary'],
        'deadline_mean':selected['deadline_mean'],'deadline_cvar':selected['deadline_cvar'],
        'guard_deadline_mean':anchor['deadline_mean'],'guard_deadline_cvar':anchor['deadline_cvar'],
        'predicted_mean_loss':selected['mean_loss'],'predicted_cvar':selected['cvar'],
        'predicted_old_cvar':previous['cvar'] if previous else None,
        'predicted_cvar_reduction':previous['cvar']-selected['cvar'] if previous else None}
    return selected['blocks'],detail
