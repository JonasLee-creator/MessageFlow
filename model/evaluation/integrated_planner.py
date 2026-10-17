"""One acceptance rule anchored to an unchanged V2 reference at the current state.

This protects forecast metrics, not unknowable real outcomes. No ground truth is
accepted. V2/global prediction evaluation is still required, even during cooldown.
"""
from datetime import timedelta
import math
import statistics

from .improved_planner import improved_plan,rollout_loss
from .metrics import cvar,disruption,feasibility,mean
from .predictor import quantile
from .stable_planner import changed_tasks
from .incremental_repairs import conditional_total,incremental_candidates


def paired_upper_difference(values,reference,z):
    differences=[a-b for a,b in zip(values,reference)]
    if len(differences)!=len(values) or len(values)!=len(reference) or not differences:
        raise ValueError('guard samples must be nonempty, paired and equal length')
    error=statistics.stdev(differences)/math.sqrt(len(differences)) if len(differences)>1 else 0.
    return mean(differences)+z*error


def passes_guard(candidate,reference,config):
    """Empirical tail guard plus a paired approximate confidence margin for means."""
    deadline=paired_upper_difference(candidate['deadline_samples'],reference['deadline_samples'],config['guard_confidence_z'])
    response=paired_upper_difference(candidate['response_samples'],reference['response_samples'],config['guard_confidence_z'])
    completion=paired_upper_difference(candidate['completion_samples'],reference['completion_samples'],config['guard_confidence_z'])
    tail=candidate['deadline_cvar']-reference['deadline_cvar']
    return (deadline<=config['guard_mean_tolerance']+1e-12 and
            tail<=config['guard_tail_tolerance']+1e-12 and
            completion<=config['guard_completion_tolerance']+1e-12 and
            response<=config['guard_response_tolerance']+1e-12)


def integrated_plan(tasks,progress,completed,now,horizon,fixed,old,origin,config,predictor,history,used,control):
    from .planners import build_schedule
    step=config['slot_minutes']
    upgraded=config.get('optimizer_revision',1)>=2
    old=[b for b in old if b.task_id not in completed and b.end>now]
    # Same state, same online history, original V2 objective and candidate search.
    baseline_config=dict(config,planner_version=2,enable_local_repair=False,
        enable_replan_cooldown=False,enable_low_gain_rejection=False)
    reference_blocks,reference_detail=improved_plan(tasks,progress,completed,now,horizon,fixed,
        old,origin,baseline_config,predictor,history,used,control={})
    predictions={t.id:predictor.predict(t,origin,now,history,True) for t in tasks}
    probabilities={tid:p[2] for tid,p in predictions.items()}
    prior={t.id:(math.log(t.estimate),config['duration_sigma_prior'],
        {key:config['execution_probability_prior'] for key in probabilities[t.id]}) for t in tasks}
    count=history.get('_duration',(0.,0))[1]
    model_weight=config['cold_start_model_weight']+(1-config['cold_start_model_weight'])*count/(count+8)
    at=lambda m:origin+timedelta(minutes=m)
    cache={}

    def evaluate(name,blocks,stage,offset=None):
        offset=config['planning_samples'] if offset is None else offset
        key=(offset,tuple((b.task_id,b.start,b.end) for b in blocks))
        if key in cache:
            return dict(cache[key],name=name,stage=stage)
        if feasibility(blocks,tasks,fixed,config['daily_capacity_minutes'],at,
                       now=now,used=used,horizon=horizon,working_hours=config['working_hours']):
            return None
        if disruption(old,blocks,now,config['freeze_minutes'])[1]:
            return None
        values=[]
        prepared={t.id:[] for t in tasks}
        for b in sorted(blocks,key=lambda b:b.start):
            if b.end>now:
                prepared[b.task_id].append(b)
        # Audit with sample IDs disjoint from V2's candidate-search samples.
        # V2 reference is not reselected on these audit draws.
        n=config['planning_samples']
        for s in range(n):
            distribution=predictions if (s+.5)/n<model_weight else prior
            values.append(rollout_loss(blocks,tasks,progress,distribution,now,horizon,
                origin,config,s+offset,components=True,prepared_blocks=prepared))
        deadline=[v['deadline'] for v in values]
        response=[v['response'] for v in values]
        aggregate=[v['deadline']+config['unfinished_weight']*v['unfinished']+
                   config['response_weight']*v['response'] for v in values]
        row={'name':name,'blocks':blocks,'stage':stage,'audit_offset':offset,'deadline_samples':deadline,
             'completion_samples':[v['completion_loss'] for v in values],
             'response_samples':response,'deadline_mean':mean(deadline),
             'deadline_cvar':cvar(deadline,config['cvar_alpha']),
             'mean_loss':mean(aggregate),'cvar':cvar(aggregate,config['cvar_alpha']),
             'movement':disruption(old,blocks,now,config['freeze_minutes'])[0] if old else 0.}
        cache[key]=row
        return row

    reference=evaluate('v2_reference',reference_blocks,'reference')
    if reference is None:
        raise ValueError('V2 reference violates a hard constraint; inspect commitments')
    previous=evaluate('keep_current',old,'keep')
    cooldown=now-control.get('last_change',-10**9)<config['adaptive_cooldown_minutes']
    previous_safe=previous is not None and passes_guard(previous,reference,config)
    new_ids={t.id for t in tasks}-set(control.get('known_ids',[]))
    missing={t.id for t in tasks if not any(b.task_id==t.id for b in old)}
    # Pending work is accounted for; no hidden true duration or execution outcome.
    def slack(task):
        if upgraded:
            total=conditional_total(*predictions[task.id][:2],progress.get(task.id,0),.8,step)
        else:
            total=quantile(*predictions[task.id][:2],.8)
        remaining=max(step,total-progress.get(task.id,0))
        execution=max(.25,mean(probabilities[task.id].values()))
        duration=remaining/execution if task.splittable else remaining
        earliest=max(now,task.available,task.earliest) if upgraded else now
        return (task.deadline if task.deadline is not None else horizon+20160)-earliest-duration
    risk_ids={t.id for t in tasks if t.deadline is not None and now<t.deadline and slack(t)<=config['freeze_minutes']}
    affected=(new_ids|missing|risk_ids|set(control.get('affected',[])))-set(completed)
    reference_changes=changed_tasks(old,reference_blocks,now,step)
    ranked=sorted(tasks,key=lambda t:(t.id not in affected,t.id not in reference_changes,slack(t),-t.priority,t.id))
    safe=[reference]
    if previous_safe:
        safe.append(previous)
    incremental_count=0
    if upgraded:
        for name,blocks,stage in incremental_candidates(tasks,progress,completed,now,horizon,
                fixed,old,origin,config,predictions,used):
            row=evaluate(name,blocks,stage)
            if row is not None and passes_guard(row,reference,config):
                safe.append(row)
                incremental_count+=1
    # Cooldown never vetoes a required repair. If the old plan fails its audit,
    # scopes expand and the certified V2 fallback is always available.
    tried=[]
    zero_movement_safe=upgraded and any(r['movement']==0 for r in safe) and not missing and not new_ids
    if not ((cooldown and previous_safe and not missing and not new_ids) or zero_movement_safe):
        sizes=sorted({min(len(tasks),n) for n in config['repair_scopes']}|{len(tasks)})
        for size in sizes:
            local_ids={t.id for t in ranked[:size]}
            tried.append(size)
            retained=[b for b in old if b.task_id not in local_ids or b.start<now+config['freeze_minutes']]
            found=False
            for q in (.5,.8,.95):
                durations={}
                for task in tasks:
                    if task.id in local_ids:
                        if upgraded:
                            durations[task.id]=conditional_total(*predictions[task.id][:2],progress.get(task.id,0),q,step)
                        else:
                            durations[task.id]=max(quantile(*predictions[task.id][:2],q),progress.get(task.id,0)+step)
                    else:
                        committed=sum(max(0,b.end-max(now,b.start)) for b in retained if b.task_id==task.id)
                        first=min((b.start for b in retained if b.task_id==task.id),default=now)
                        saved=progress.get(task.id,0) if task.splittable or first<=now else 0.
                        durations[task.id]=committed+saved
                for order in ('edf','priority_edf'):
                    blocks=build_schedule(tasks,progress,completed,now,horizon,fixed,retained,origin,config,
                        durations,probabilities,order,False,used,preserve_old=True,continuity=True)
                    if not changed_tasks(old,blocks,now,step)<=local_ids:
                        continue
                    row=evaluate(f'repair_{size}_p{q}_{order}',blocks,'local' if size<len(tasks) else 'expanded')
                    if row is not None and passes_guard(row,reference,config):
                        safe.append(row)
                        found=True
            if found:
                break
    # Reduce disturbance only inside the set protected against the reference.
    selected=min(safe,key=lambda r:(r['movement'],r['mean_loss'],r['deadline_cvar'],r['name']))
    rejected=False
    if previous_safe and not missing and not new_ids:
        gain=previous['mean_loss']-selected['mean_loss']
        if cooldown or gain<config['minimum_replan_gain']:
            selected=previous
            rejected=True
    # Freeze the proposal, then verify it on another disjoint draw set. If it
    # fails, use V2 directly; do not search/reselect on the verification draws.
    proposal_name=selected['name']
    verification_reference=evaluate('v2_reference',reference_blocks,'reference',2*config['planning_samples'])
    verified=evaluate(selected['name'],selected['blocks'],selected['stage'],2*config['planning_samples'])
    fallback=not passes_guard(verified,verification_reference,config)
    selected=verification_reference if fallback else verified
    reference=verification_reference
    if previous is not None:
        previous=evaluate('keep_current',old,'keep',2*config['planning_samples'])
    changed=changed_tasks(old,selected['blocks'],now,step)
    if changed:
        control['last_change']=now
    control['known_ids']=[t.id for t in tasks]
    control['affected']=[]
    return selected['blocks'],{
        'planner_version':4,'candidate':selected['name'],'stage':selected['stage'],
        'optimizer_revision':config.get('optimizer_revision',1),
        'incremental_candidates_passed':incremental_count,
        'skipped_repair_search':int(zero_movement_safe),
        'candidate_count':len(cache),'admissible_candidates':len(safe),'global_search':1,
        'reference_candidate':reference_detail['candidate'],'reference_recomputed':1,
        'proposed_candidate':proposal_name,'verification_fallback':int(fallback),
        'repair_scopes_tried':tried,'cooldown_active':int(cooldown),
        'cooldown_bypassed_for_risk':int(cooldown and not previous_safe),
        'rejected_low_gain':int(rejected and not fallback),'affected_task_count':len(changed),
        'guard_passed':int(passes_guard(selected,reference,config)),
        'deadline_mean':selected['deadline_mean'],'guard_deadline_mean':reference['deadline_mean'],
        'deadline_cvar':selected['deadline_cvar'],'guard_deadline_cvar':reference['deadline_cvar'],
        'response_mean':mean(selected['response_samples']),
        'completion_loss':mean(selected['completion_samples']),
        'guard_completion_loss':mean(reference['completion_samples']),
        'guard_response_mean':mean(reference['response_samples']),
        'predicted_mean_loss':selected['mean_loss'],'predicted_cvar':selected['cvar'],
        'predicted_old_cvar':previous['cvar'] if previous else None,
        'predicted_cvar_reduction':previous['cvar']-selected['cvar'] if previous else None}
