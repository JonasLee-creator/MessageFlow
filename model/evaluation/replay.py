from __future__ import annotations

from dataclasses import asdict
import math
import time

from .domain import uniform
from .metrics import disruption, feasibility, mean, outcomes
from .planners import plan
from .predictor import bucket


def replay(scenario,method,seed,config,predictor):
    # Each method starts cold; one policy must not inherit another policy's cache.
    predictor.cache.clear()
    step = config['slot_minutes']
    progress,completed,first,history,used = {},{},{},{},{}
    old,visible = [],set()
    attempts,events,snapshots = [],[],[]
    violations,total_movement,replans = 0,0.,0
    actual = {tid:value['duration'] for tid,value in scenario.truth.items()}
    last_task,last_end = None,-1
    dirty = True
    for now in range(0,scenario.horizon,step):
        known = [t for t in scenario.tasks if t.available<=now]
        new_visible = {t.id for t in known}
        released = new_visible-visible
        exhausted = any(t.id not in completed and not any(b.task_id==t.id and b.end>now for b in old) for t in known)
        if dirty or released or exhausted:
            started = time.perf_counter()
            new,detail = plan(method,known,progress,completed,now,scenario.horizon,scenario.fixed,
                             old,scenario.origin,config,predictor,history,used)
            seconds = time.perf_counter()-started
            errors = feasibility(new,known,scenario.fixed,config['daily_capacity_minutes'],scenario.at)
            movement,frozen = disruption(old,new,now,config['freeze_minutes'])
            # Completed work may remove its obsolete commitment without violating a freeze.
            if completed:
                movement,frozen = disruption([b for b in old if b.task_id not in completed],new,now,config['freeze_minutes'])
            violations += len(errors)+frozen
            if old:
                total_movement += movement
            events.append({'minute':now,'reason':'release' if released else 'feedback_or_exhausted',
                'latency_seconds':seconds,'movement_minutes':movement if old else 0.,
                'constraint_errors':errors,'freeze_violations':frozen,**detail})
            snapshots.append({'minute':now,'blocks':[asdict(b) for b in new]})
            old,visible,dirty = new,new_visible,False
            replans += 1
        active = next((b for b in old if b.start<=now<b.end and b.task_id not in completed),None)
        if active is None:
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
                residuals,count = history.get('_duration',(0.,0))
                history['_duration'] = (residuals+math.log(actual[task.id])-mu,count+1)
            dirty = True
        if not success:
            dirty = True
        attempts.append({'task_id':task.id,'start':now,'end':now+step,'success':success,
                         'work_minutes':work,'truth_probability':p})
        last_task,last_end = (task.id if success else None),now+step
    for minute in range(0,scenario.horizon,step):
        used.setdefault(scenario.at(minute).date().isoformat(),0)
    result = outcomes(scenario.tasks,completed,first,progress,actual,scenario.horizon)
    result.update({'scenario_id':scenario.id,'stress':scenario.stress,'seed':seed,'method':method,
        'feasible':int(violations==0),'constraint_violations':violations,
        'disruption_minutes':total_movement,'replans':replans,
        'planning_seconds_mean':mean(e['latency_seconds'] for e in events),
        'planning_seconds_max':max((e['latency_seconds'] for e in events),default=0),
        'attempt_count':len(attempts),'execution_rate':mean(a['success'] for a in attempts),
        'predicted_cvar_reduction_mean':mean(e['predicted_cvar_reduction'] for e in events if 'predicted_cvar_reduction' in e),
        'switches':sum(a['task_id']!=b['task_id'] for a,b in zip(attempts,attempts[1:])),
        'daily_load_variance':mean((v-(mean(used.values()) or 0))**2 for v in used.values())})
    task_rows = [{'task_id':t.id,'released':t.released,'deadline':t.deadline,
        'completed':completed.get(t.id),'first_start':first.get(t.id),'censored':t.id not in completed,
        'followup_minutes':scenario.horizon-t.released,'actual_duration_minutes':actual[t.id],
        'retained_work_minutes':progress.get(t.id,0)} for t in scenario.tasks]
    return result,{'tasks':task_rows,'events':events,'attempts':attempts,'snapshots':snapshots}
