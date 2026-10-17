from __future__ import annotations

from dataclasses import asdict
import math
import time

from .domain import uniform
from .metrics import disruption, feasibility, mean, outcomes
from .planners import plan
from .predictor import bucket
from .online import OnlineHistory
from .stable_planner import changed_tasks


def replay(scenario,method,seed,config,predictor):
    # Each method starts cold; one policy must not inherit another policy's cache.
    predictor.cache.clear()
    step = config['slot_minutes']
    progress,completed,first,history,used = {},{},{},{},{}
    modern_online=config.get('online_version',1)>=2 and method in ('personalized','risk_aware','drp_full')
    if modern_online:
        history=OnlineHistory(config)
    control,dirty_tasks={},set()
    old,visible = [],set()
    attempts,events,snapshots = [],[],[]
    violations,total_movement,replans = 0,0.,0
    actual = {tid:value['duration'] for tid,value in scenario.truth.items()}
    last_task,last_end = None,-1
    dirty = True
    for now in range(0,scenario.horizon,step):
        # Non-splittable work is retained only across uninterrupted attempts.
        # Clear stale progress BEFORE a planner observes it, not on execution later.
        for task in scenario.tasks:
            if not task.splittable and task.id not in completed and (last_task!=task.id or last_end!=now):
                progress[task.id] = 0.
        known = [t for t in scenario.tasks if t.available<=now]
        new_visible = {t.id for t in known}
        released = new_visible-visible
        exhausted = any(t.id not in completed and not any(b.task_id==t.id and b.end>now for b in old) for t in known)
        trigger=dirty or released or exhausted
        if config.get('enable_replan_cooldown',config.get('planner_version',1)>=3) and method=='drp_full' and not dirty and not released:
            urgent=any(t.id not in completed and t.deadline is not None and now<t.deadline<=now+config['urgent_deadline_minutes'] for t in known)
            if not urgent and now<control.get('next_review',0):
                trigger=False
        if trigger:
            control['affected']=sorted(dirty_tasks)
            started = time.perf_counter()
            new,detail = plan(method,known,progress,completed,now,scenario.horizon,scenario.fixed,
                             old,scenario.origin,config,predictor,history,used,control=control)
            seconds = time.perf_counter()-started
            errors = feasibility(new,known,scenario.fixed,config['daily_capacity_minutes'],scenario.at,
                now=now,used=used,horizon=scenario.horizon,working_hours=config['working_hours'])
            movement,frozen = disruption(old,new,now,config['freeze_minutes'])
            # Completed work may remove its obsolete commitment without violating a freeze.
            if completed:
                movement,frozen = disruption([b for b in old if b.task_id not in completed],new,now,config['freeze_minutes'])
            physical_changes=changed_tasks([b for b in old if b.task_id not in completed],new,now,step)
            violations += len(errors)+frozen
            if old:
                total_movement += movement
            events.append({'minute':now,'reason':'release' if released else 'feedback_or_exhausted',
                'latency_seconds':seconds,'movement_minutes':movement if old else 0.,
                'plan_changed':int(bool(physical_changes)),
                'physical_changed_task_count':len(physical_changes),
                'constraint_errors':errors,'freeze_violations':frozen,**detail})
            snapshots.append({'minute':now,'blocks':[asdict(b) for b in new]})
            old,visible,dirty = new,new_visible,False
            dirty_tasks.clear()
            control['next_review']=now+2*step
            replans += 1
        active = next((b for b in old if b.start<=now<b.end and b.task_id not in completed),None)
        if active is None:
            if modern_online:
                history.flush(now)
            continue
        task = next(t for t in known if t.id==active.task_id)
        name = bucket(scenario.at(now))
        p = scenario.truth[task.id]['probabilities'][name]
        # Task/time keyed potential outcomes. All policies face the same field.
        success = uniform(scenario.id,seed,task.id,now)<p
        if scenario.stress=='double_skip' and now in (120,150):
            success = False
        # Other stress transformations are already materialized in scenario_instances.
        done_before = progress.get(task.id,0)
        if not task.splittable and (last_task!=task.id or last_end!=now):
            done_before = 0.
        if success:
            first.setdefault(task.id,now)
        if modern_online:
            global_p=predictor.base(task,scenario.origin,now)[2][name]
            personal_p=predictor.predict(task,scenario.origin,now,history,True)[2][name]
            history.observe(task.id,name,now,step,success,global_p,personal_p)
        else:
            success_count,total = history.get(name,(0,0))
            history[name] = (success_count+int(success),total+1)
        day = scenario.at(now).date().isoformat()
        # Daily capacity is occupied time, including failed attempts.
        used[day] = used.get(day,0)+step
        work = min(step,max(0,actual[task.id]-done_before)) if success else 0.
        progress[task.id] = done_before+work if success or task.splittable else 0.
        if progress[task.id]>=actual[task.id]:
            completed[task.id] = now+round(work)
            if method in ('personalized','risk_aware','drp_full'):
                mu,_,_ = predictor.base(task,scenario.origin,task.available)
                if modern_online:
                    history.flush(now+step)
                    history.record_duration(progress[task.id],mu,now+step)
                else:
                    residuals,count = history.get('_duration',(0.,0))
                    history['_duration'] = (residuals+math.log(actual[task.id])-mu,count+1)
            dirty = True
            dirty_tasks.add(task.id)
        if not success:
            dirty = True
            dirty_tasks.add(task.id)
        attempts.append({'task_id':task.id,'start':now,'end':now+step,'success':success,
                         'work_minutes':work,'truth_probability':p})
        last_task,last_end = (task.id if success else None),now+step
    if modern_online:
        history.flush(scenario.horizon)
    for minute in range(0,scenario.horizon,step):
        used.setdefault(scenario.at(minute).date().isoformat(),0)
    result = outcomes(scenario.tasks,completed,first,progress,actual,scenario.horizon)
    result.update({'scenario_id':scenario.id,'stress':scenario.stress,'seed':seed,'method':method,
        'feasible':int(violations==0),'constraint_violations':violations,
        'disruption_minutes':total_movement,'replans':replans,
        'planning_seconds_mean':mean(e['latency_seconds'] for e in events),
        'planning_seconds_max':max((e['latency_seconds'] for e in events),default=0),
        'attempt_count':len(attempts),'execution_rate':mean(a['success'] for a in attempts),
        'predicted_cvar_reduction_mean':mean(e['predicted_cvar_reduction'] for e in events if e.get('predicted_cvar_reduction') is not None),
        'global_searches':sum(e.get('global_search',0) for e in events),
        'local_repairs':sum(e.get('stage')=='local' for e in events),
        'expanded_repairs':sum(e.get('stage')=='expanded' for e in events),
        'incremental_repairs':sum(e.get('stage')=='incremental' for e in events),
        'reference_plan_selections':sum(e.get('stage')=='reference' for e in events),
        'verification_fallbacks':sum(e.get('verification_fallback',0) for e in events),
        'keep_plan_decisions':sum(e.get('stage')=='keep' for e in events),
        'changed_plan_decisions':sum(e['plan_changed'] for e in events),
        'physical_changed_tasks_per_decision':mean(e['physical_changed_task_count'] for e in events),
        'rejected_low_gain_replans':sum(e.get('rejected_low_gain',0) for e in events),
        'affected_tasks_per_decision':mean(e['affected_task_count'] for e in events if 'affected_task_count' in e),
        'online_sessions':history.session_count if modern_online else 0,
        'switches':sum(a['task_id']!=b['task_id'] for a,b in zip(attempts,attempts[1:])),
        'daily_load_variance':mean((v-(mean(used.values()) or 0))**2 for v in used.values())})
    task_rows = [{'task_id':t.id,'released':t.released,'deadline':t.deadline,
        'completed':completed.get(t.id),'first_start':first.get(t.id),'censored':t.id not in completed,
        'followup_minutes':scenario.horizon-t.released,'actual_duration_minutes':actual[t.id],
        'retained_work_minutes':progress.get(t.id,0)} for t in scenario.tasks]
    return result,{'tasks':task_rows,'events':events,'attempts':attempts,'snapshots':snapshots}
