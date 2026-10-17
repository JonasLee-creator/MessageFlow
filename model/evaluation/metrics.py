from __future__ import annotations

import math
import random
import statistics


def mean(values):
    values = list(values)
    return statistics.fmean(values) if values else None


def cvar(values, alpha=.9):
    """Empirical CVaR with fractional mass at the quantile boundary."""
    values = sorted(values, reverse=True)
    if not values or not 0 < alpha < 1:
        raise ValueError('CVaR needs observations and 0 < alpha < 1')
    mass = len(values) * (1-alpha)
    whole = int(mass)
    total = sum(values[:whole])
    if whole < len(values):
        total += (mass-whole) * values[whole]
    return total / mass


def feasibility(blocks, tasks, fixed, capacity, at):
    errors = []
    ordered = sorted(blocks, key=lambda b: b.start)
    by_id = {t.id: t for t in tasks}
    day_load = {}
    for i, block in enumerate(ordered):
        task = by_id[block.task_id]
        if block.end <= block.start or block.start < max(task.available, task.earliest):
            errors.append('invalid_window')
        if i and block.start < ordered[i-1].end:
            errors.append('overlap')
        if any(block.start < end and start < block.end for start, end in fixed):
            errors.append('fixed_conflict')
        for minute in range(block.start, block.end):
            day = at(minute).date().isoformat()
            day_load[day] = day_load.get(day, 0) + 1
    if any(v > capacity for v in day_load.values()):
        errors.append('daily_capacity')
    for task in tasks:
        parts = [b for b in ordered if b.task_id == task.id]
        if not task.splittable and any(a.end != b.start for a, b in zip(parts, parts[1:])):
            errors.append('illegal_split')
    return errors


def disruption(old, new, now, freeze):
    """Match by task and block ordinal; count shifts AND additions/deletions."""
    def index(blocks):
        result = {}
        for block in sorted(blocks, key=lambda b: b.start):
            if block.start >= now:
                result.setdefault(block.task_id, []).append(block)
        return result
    left, right = index(old), index(new)
    cost, frozen = 0., 0
    for tid in left.keys() | right.keys():
        a, b = left.get(tid, []), right.get(tid, [])
        # Preserve exact commitments before ordinal matching. A newly inserted
        # block must not make an unchanged frozen block appear to have moved.
        frozen += sum(x.start<now+freeze and x not in b for x in a)
        unchanged = set(a) & set(b)
        a = [x for x in a if x not in unchanged]
        b = [x for x in b if x not in unchanged]
        for i in range(max(len(a), len(b))):
            x = a[i] if i < len(a) else None
            y = b[i] if i < len(b) else None
            if x is not None:
                weight = 1 + 3 * math.exp(-(x.start-now)/120)
                cost += weight * (abs(x.start-y.start) + abs(x.end-y.end) if y else x.end-x.start)
            elif y:
                cost += y.end-y.start
    return cost, frozen


def outcomes(tasks, completed, first, progress, actual, horizon):
    eligible = [t for t in tasks if t.available < horizon]
    due = [t for t in eligible if t.deadline is not None and t.deadline <= horizon]
    weight = sum(t.priority for t in due)
    ontime = lambda t: t.id in completed and completed[t.id] <= t.deadline
    # Loss measured at deadlines: unfinished fractions remain defined for censored tasks.
    deadline_loss = sum(t.priority * (0 if ontime(t) else 1) for t in due) / (weight or 1)
    ages = [min(completed.get(t.id, horizon), horizon)-t.released for t in eligible]
    # Different follow-up lengths: call this restricted observed latency, NOT KM RMST.
    return {
        'weighted_ontime_rate': sum(t.priority for t in due if ontime(t))/weight if weight else None,
        'ontime_rate': sum(ontime(t) for t in due)/len(due) if due else None,
        'deadline_loss': deadline_loss,
        'completion_rate': len(completed)/len(eligible) if eligible else None,
        'restricted_latency_minutes': mean(ages),
        'normalized_restricted_latency': mean((min(completed.get(t.id,horizon),horizon)-t.released)/max(1,horizon-t.released) for t in eligible),
        'first_start_delay_minutes': mean(first.get(t.id,horizon)-t.released for t in eligible),
        'censored_fraction': sum(t.id not in completed for t in eligible)/len(eligible) if eligible else None,
        'unfinished_minutes': sum(max(0, actual[t.id]-progress.get(t.id,0)) for t in eligible if t.id not in completed),
        'completed_tardiness_minutes': mean(max(0,completed[t.id]-t.deadline) for t in due if t.id in completed),
        'deadline_tasks': len(due),
    }


def paired_bootstrap(rows, baseline, method, metric, samples, seed):
    # Scenario is the independent cluster; repeated seeds are averaged inside each cluster.
    groups = {}
    for row in rows:
        if row['method'] in (baseline,method) and row.get(metric) is not None:
            groups.setdefault(row['scenario_id'], {}).setdefault(row['method'], []).append(row[metric])
    delta = [mean(v[method])-mean(v[baseline]) for v in groups.values() if baseline in v and method in v]
    if not delta:
        return {'metric':metric, 'clusters':0}
    rng = random.Random(seed)
    boot = sorted(mean(rng.choices(delta,k=len(delta))) for _ in range(samples))
    return {'metric':metric, 'method':method, 'baseline':baseline, 'clusters':len(delta),
            'difference':mean(delta), 'ci95_low':boot[int(.025*(samples-1))],
            'ci95_high':boot[int(.975*(samples-1))], 'positive_difference_rate':mean(d>0 for d in delta)}


def paired_tail_bootstrap(rows,baseline,method,samples,seed,alpha):
    groups = {}
    for row in rows:
        if row['method'] in (baseline,method):
            groups.setdefault(row['scenario_id'],{}).setdefault(row['method'],[]).append(row['deadline_loss'])
    groups = [v for v in groups.values() if baseline in v and method in v]
    if not groups:
        return {'metric':'cvar_deadline_loss','clusters':0}
    def delta(cluster):
        return cvar([x for g in cluster for x in g[method]],alpha)-cvar([x for g in cluster for x in g[baseline]],alpha)
    rng=random.Random(seed)
    boot=sorted(delta(rng.choices(groups,k=len(groups))) for _ in range(samples))
    return {'metric':'cvar_deadline_loss','method':method,'baseline':baseline,
        'clusters':len(groups),'difference':delta(groups),'ci95_low':boot[int(.025*(samples-1))],
        'ci95_high':boot[int(.975*(samples-1))]}
