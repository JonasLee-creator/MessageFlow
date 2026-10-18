"""Public-state complexity gate plus simple candidates, with held-out audits.

Version 5 does not read Scenario, simulator truth, split names, or real-study
labels. Thresholds are hypotheses to select on synthetic validation only.
"""
from datetime import timedelta
import math

from .improved_planner import rollout_loss
from .integrated_planner import integrated_plan, passes_guard
from .metrics import cvar, disruption, feasibility, mean
from .predictor import bucket, quantile
from .stable_planner import changed_tasks


DEFAULTS = {
    'adaptive_max_load': .35,
    'adaptive_min_slack_minutes': 180.,
    'adaptive_min_execution_probability': .5,
    'adaptive_max_execution_spread': .3,
    'adaptive_max_deadline_loss': 0.,
    'adaptive_max_completion_loss': 0.,
    'adaptive_max_tail_loss': 0.,
    'adaptive_movement_weight': .02,
    'adaptive_min_gain': .0001,
}


def validate_config(config):
    for key, default in DEFAULTS.items():
        value = config.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f'{key} must be a finite nonnegative number')
        if key not in ('adaptive_min_slack_minutes', 'adaptive_movement_weight') and value > 1:
            raise ValueError(f'{key} must be <=1')
    if config.get('optimizer_revision', 1) != 1:
        raise ValueError('adaptive planner anchors to original integrated revision 1, not plus')
    if config['planning_samples'] < 2:
        raise ValueError('adaptive planner requires >=2 audit samples')


def complexity(tasks, progress, now, horizon, fixed, old, origin, config, predictions, used):
    """Conservative deadline-prefix capacity screen, not a schedulability proof.

    Uses P80 and only feasible clock buckets. Earliest-start capacity is checked
    per task as well as jointly at each deadline, so late releases cannot borrow
    an entire day's past capacity. Frozen old work still consumes that capacity.
    """
    step = config['slot_minutes']
    slots = []
    at = lambda m: origin + timedelta(minutes=m)
    for minute in range(now, horizon, step):
        end = minute + step
        day = at(minute).date().isoformat()
        if end > horizon or not config['working_hours'][0] <= at(minute).hour < config['working_hours'][1]:
            continue
        if any(minute < e and s < end for s, e in fixed):
            continue
        if used.get(day, 0) + step > config['daily_capacity_minutes']:
            continue
        slots.append(minute)
    def capacity(minutes):
        days = {}
        for minute in minutes:
            day = at(minute).date().isoformat()
            days[day] = days.get(day, 0)+step
        # Do not greedily spend a day's budget on its first slots: a task that
        # becomes available in the evening can use that day's remaining budget.
        return sum(min(count, max(0, config['daily_capacity_minutes']-used.get(day, 0)))
                   for day, count in days.items())
    due_work = []
    slacks, individual_loads, execution, spreads = [], [], [], []
    for task in tasks:
        earliest = max(now, task.available, task.earliest)
        due = min(horizon, task.deadline if task.deadline is not None else horizon)
        eligible = [m for m in slots if m >= earliest and m + step <= due and not any(
            b.task_id != task.id and b.start < now+config['freeze_minutes'] and
            m < b.end and b.start < m+step for b in old)]
        mu, sigma, probs = predictions[task.id]
        ps = [probs[bucket(at(m))] for m in eligible]
        p = mean(ps) if ps else 0.
        execution.append(p)
        spreads.append(max(ps)-min(ps) if ps else 1.)
        # Observed overrun deliberately prevents the cheap route; original
        # integrated is retained for these states rather than using revision 2.
        estimate = max(task.estimate, quantile(mu, sigma, .8))
        retained = progress.get(task.id, 0)
        if retained >= estimate:
            estimate = retained + step
        remaining = max(step, estimate-retained)
        demand = math.ceil(remaining/max(.25, p)/step)*step
        available_capacity = capacity(eligible)
        individual_loads.append(demand/max(step, available_capacity) if available_capacity else 1e9)
        slacks.append(available_capacity-demand)
        due_work.append((due, demand))
    prefix_load = max((sum(work for d, work in due_work if d <= due)/max(step, capacity([m for m in slots if m+step <= due]))
                       for due, _ in due_work), default=0.)
    load = max([prefix_load, *individual_loads], default=0.)
    # Reserved work is still part of predicted demand; do not subtract its
    # capacity again globally. Per-task windows exclude other tasks' locks.
    load = max(load, sum(work for _, work in due_work)/max(step, capacity(slots)))
    metrics = dict(load=load, min_slack_minutes=min(slacks, default=0.),
        min_execution_probability=min(execution, default=0.),
        max_execution_spread=max(spreads, default=1.))
    low = (load <= config['adaptive_max_load'] and
        metrics['min_slack_minutes'] >= config['adaptive_min_slack_minutes'] and
        metrics['min_execution_probability'] >= config['adaptive_min_execution_probability'] and
        metrics['max_execution_spread'] <= config['adaptive_max_execution_spread'])
    return low, metrics


def adaptive_plan(tasks, progress, completed, now, horizon, fixed, old, origin,
                  config, predictor, history, used, control):
    from .planners import plan, build_schedule
    config = {**DEFAULTS, **config}
    validate_config(config)
    old = [b for b in old if b.end > now and b.task_id not in completed]
    predictions = {t.id:predictor.predict(t, origin, now, history, True) for t in tasks}
    low, features = complexity(tasks, progress, now, horizon, fixed, old, origin, config, predictions, used)
    prior = {t.id:(math.log(t.estimate), config['duration_sigma_prior'],
        dict.fromkeys(predictions[t.id][2], config['execution_probability_prior'])) for t in tasks}
    count = history.get('_duration', (0., 0))[1]
    weight = config['cold_start_model_weight']+(1-config['cold_start_model_weight'])*count/(count+8)
    n = config['planning_samples']
    at = lambda m: origin+timedelta(minutes=m)
    cache = {}

    def audit(name, blocks, stage, offset):
        key = (offset, tuple((b.task_id, b.start, b.end) for b in blocks))
        if key in cache:
            return dict(cache[key], name=name, stage=stage)
        if feasibility(blocks, tasks, fixed, config['daily_capacity_minutes'], at,
                now=now, used=used, horizon=horizon, working_hours=config['working_hours']):
            return None
        movement, frozen = disruption(old, blocks, now, config['freeze_minutes'])
        if frozen:
            return None
        # Do not call an empty/partially dropped plan a low-risk cheap solution.
        if any(not any(b.task_id == t.id and b.end > now for b in blocks) for t in tasks):
            return None
        prepared = {t.id:[] for t in tasks}
        for block in sorted(blocks, key=lambda b:b.start):
            prepared[block.task_id].append(block)
        samples = [rollout_loss(blocks, tasks, progress,
            predictions if (s+.5)/n < weight else prior, now, horizon, origin,
            config, offset+s, components=True, prepared_blocks=prepared) for s in range(n)]
        deadline = [s['deadline'] for s in samples]
        response = [s['response'] for s in samples]
        row = dict(name=name, blocks=blocks, stage=stage, deadline_samples=deadline,
            response_samples=response, completion_samples=[s['completion_loss'] for s in samples],
            deadline_cvar=cvar(deadline, config['cvar_alpha']),
            movement=movement if old else 0., response_mean=mean(response))
        cache[key] = row
        return row

    def absolute_safe(row):
        return row is not None and (
            mean(row['deadline_samples']) <= config['adaptive_max_deadline_loss']+1e-12 and
            mean(row['completion_samples']) <= config['adaptive_max_completion_loss']+1e-12 and
            row['deadline_cvar'] <= config['adaptive_max_tail_loss']+1e-12)

    def score(row):
        return row['response_mean'] + config['adaptive_movement_weight']*row['movement']/max(1, horizon-now)

    def pick(rows):
        chosen = min(rows, key=lambda r:(score(r), r['movement'], r['name']))
        previous = next((r for r in rows if r['name'] == 'keep_current'), None)
        if previous is not None and score(previous)-score(chosen) < config['adaptive_min_gain']:
            return previous
        return chosen

    proposals = [('keep_current', old, 'keep')]
    for method in ('edf', 'priority_edf', 'deterministic'):
        blocks, _ = plan(method, tasks, progress, completed, now, horizon, fixed,
            old, origin, config, predictor, history, used, control={})
        proposals.append((f'simple_{method}', blocks, 'simple'))
    # Early-placement buffered alternatives use the same predictions as DRP,
    # with no preference delay or combinatorial search. Unused tails are freed
    # when replay observes completion, exactly as for the original planner.
    probabilities = {tid:values[2] for tid, values in predictions.items()}
    budgets = {}
    for task in tasks:
        total = max(task.estimate, quantile(*predictions[task.id][:2], .8),
                    progress.get(task.id, 0)+config['slot_minutes'])
        remaining = total-progress.get(task.id, 0)
        p = max(.5, mean(probabilities[task.id].values()))
        budgets[task.id] = progress.get(task.id, 0)+remaining/p if task.splittable else total
    for order in ('edf', 'priority_edf'):
        blocks = build_schedule(tasks, progress, completed, now, horizon, fixed, old, origin,
            config, budgets, probabilities, order, False, used)
        proposals.append((f'simple_buffered_{order}', blocks, 'simple'))
    rows = [row for name, blocks, stage in proposals
            if (row := audit(name, blocks, stage, 3*n)) is not None]
    selected, detail, verified, fallback = None, {}, None, False
    complex_called = False
    if low:
        eligible = [r for r in rows if absolute_safe(r)]
        if eligible:
            selected = pick(eligible)
            verified = audit(selected['name'], selected['blocks'], selected['stage'], 4*n)
            if not absolute_safe(verified):
                selected = None
                fallback = True
    # In a difficult state, compute the original integrated plan, and admit a
    # simple alternative only if paired guards protect deadline/completion/response.
    if selected is None:
        complex_called = True
        reference, detail = integrated_plan(tasks, progress, completed, now, horizon, fixed,
            old, origin, dict(config, planner_version=4, optimizer_revision=1), predictor, history, used, dict(control))
        # A failed low-complexity verification commits us to the original
        # fallback. Do not propose a second simple plan on the same audit set.
        ref_audit = (None if fallback else
                     audit('integrated_reference', reference, 'adaptive_reference', 3*n))
        if ref_audit is not None:
            safe = [ref_audit]+[r for r in rows if passes_guard(r, ref_audit, config)]
            selected = pick(safe)
            ref_verify = audit('integrated_reference', reference, 'adaptive_reference', 4*n)
            verified = audit(selected['name'], selected['blocks'], selected['stage'], 4*n)
            if not passes_guard(verified, ref_verify, config):
                verified = ref_verify
                fallback = True
        else:
            # Some tasks cannot fit at all. Preserve the original behavior rather
            # than letting the all-task coverage screen reject its fallback.
            verified = dict(name='integrated_reference', blocks=reference, stage='adaptive_reference',
                response_mean=detail.get('response_mean'), movement=disruption(old, reference, now, config['freeze_minutes'])[0])
    changed = changed_tasks(old, verified['blocks'], now, config['slot_minutes'])
    if changed:
        control['last_change'] = now
    control['known_ids'] = [t.id for t in tasks]
    control['affected'] = []
    # Do not carry the original plan's guard values over to a different proposal.
    result = {k:v for k,v in detail.items() if not k.startswith('guard_')}
    result.update(planner_version=5, candidate=verified['name'], stage=verified['stage'],
        adaptive_low_complexity=int(low), adaptive_complex_reference=int(complex_called),
        adaptive_simple_selected=int(verified['stage']=='simple'),
        adaptive_verification_fallback=int(fallback), adaptive_features=features,
        adaptive_predicted_response=verified['response_mean'],
        adaptive_candidate_count=len(rows), global_search=int(complex_called),
        reference_recomputed=int(complex_called), affected_task_count=len(changed))
    return verified['blocks'], result
