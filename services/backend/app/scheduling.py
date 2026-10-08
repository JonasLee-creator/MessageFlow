import math
from datetime import timedelta
from zoneinfo import ZoneInfo

from ortools.sat.python import cp_model
from sqlalchemy import select, func
from .db import now
from .models import Task, Event, ScheduleBlock, ScheduleVersion, User

STEP = timedelta(minutes=30)


def overlap(a, b, c, d):
    return a < d and c < b


def block_json(b):
    return {"id": b.id, "task_id": b.task_id, "start_at": b.start_at.isoformat(), "end_at": b.end_at.isoformat(), "locked": b.locked, "version": b.version}


def replan(db, user_id, trigger="MANUAL", clock=None):
    clock = clock or now()
    tz = ZoneInfo(db.get(User, user_id).timezone)
    local = clock.astimezone(tz)
    cursor = local.replace(minute=(local.minute // 30) * 30, second=0, microsecond=0)
    if cursor < local:
        cursor += STEP
    slots = []
    while cursor < local + timedelta(days=14):
        if 8 <= cursor.hour < 23:
            slots.append(cursor)
        cursor += STEP
    tasks = db.scalars(select(Task).where(Task.user_id == user_id, Task.status.not_in(["completed", "cancelled"]))).all()
    events = db.scalars(select(Event).where(Event.user_id == user_id, Event.status == "active", Event.end_at > clock)).all()
    old = db.scalars(select(ScheduleBlock).where(ScheduleBlock.user_id == user_id)).all()
    active_ids = {t.id for t in tasks}
    # Keep past history and in-progress blocks; never move a block that has started.
    locked = [b for b in old if b.task_id in active_ids and b.end_at > clock and (b.locked or b.start_at < clock)]
    occupied = [(e.start_at, e.end_at) for e in events] + [(b.start_at, b.end_at) for b in locked]
    free = [s for s in slots if not any(overlap(s, s + STEP, a, b) for a, b in occupied)]
    model = cp_model.CpModel()
    assignments = {}
    objective = []
    risks = []
    task_by_id = {t.id: t for t in tasks}
    for b in locked:
        t = task_by_id[b.task_id]
        if (t.deadline and b.end_at > t.deadline) or any(overlap(b.start_at, b.end_at, e.start_at, e.end_at) for e in events):
            risks.append({"task_id": t.id, "title": t.title, "reason": "锁定时间与截止时间或固定日程冲突"})
    for i, b in enumerate(locked):
        if any(overlap(b.start_at, b.end_at, c.start_at, c.end_at) for c in locked[i + 1:]):
            risks.append({"task_id": b.task_id, "title": task_by_id[b.task_id].title, "reason": "锁定时间互相冲突"})
    for task in tasks:
        reserved = sum(max(0, int((b.end_at - max(b.start_at, clock)).total_seconds() / 60)) for b in locked if b.task_id == task.id)
        needed = math.ceil(max(0, task.remaining_duration - reserved) / 30)
        if not task.splittable and needed and reserved:
            risks.append({"task_id": task.id, "title": task.title, "reason": "不可拆分任务已有锁定时间，请解锁后调整完整连续时段"})
        eligible = [i for i, s in enumerate(free) if not task.deadline or s + STEP <= task.deadline]
        if needed > len(eligible):
            risks.append({"task_id": task.id, "title": task.title, "required_minutes": needed * 30, "available_minutes": len(eligible) * 30, "reason": "截止前可用时间不足"})
        if not needed:
            continue
        if task.splittable:
            variables = []
            previous = None
            for i in eligible:
                x = model.new_bool_var(f"{task.id}_{i}")
                assignments[task.id, i] = x
                variables.append(x)
                start = model.new_bool_var(f"start_{task.id}_{i}")
                if previous is not None and free[i] == free[previous] + STEP:
                    model.add(start >= x - assignments[task.id, previous])
                else:
                    model.add(start >= x)
                objective.append(start * 50)
                objective.append(x * (i + 1) * task.priority)
                previous = i
            model.add(sum(variables) == needed)
        else:
            starts = []
            coverage = {i: [] for i in eligible}
            eligible_set = set(eligible)
            for i in eligible:
                indexes = list(range(i, i + needed))
                if all(j in eligible_set and free[j] == free[i] + STEP * (j - i) for j in indexes):
                    x = model.new_bool_var(f"run_{task.id}_{i}")
                    starts.append(x)
                    objective.append(x * (i + 1) * task.priority * needed)
                    for j in indexes:
                        coverage[j].append(x)
            model.add(sum(starts) == 1)
            for i, vars_ in coverage.items():
                x = model.new_bool_var(f"{task.id}_{i}")
                model.add(x == sum(vars_))
                assignments[task.id, i] = x
    for i in range(len(free)):
        model.add(sum(x for (tid, j), x in assignments.items() if j == i) <= 1)
    model.minimize(sum(objective))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 3
    solver.parameters.num_search_workers = 4
    result = solver.solve(model) if not risks else cp_model.INFEASIBLE
    status = solver.status_name(result)
    feasible = result in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    if not feasible and not risks:
        risks.append({"reason": "任务共同争用时间，或连续时间不足" if result == cp_model.INFEASIBLE else "求解超时，尚未找到可行方案"})
    version = (db.scalar(select(func.max(ScheduleVersion.version)).where(ScheduleVersion.user_id == user_id)) or 0) + 1
    retained = {b.id for b in locked}
    for b in old:
        if b.end_at > clock and b.id not in retained:
            db.delete(b)
    for t in tasks:
        t.status = "scheduled" if feasible else "pending"
    if feasible:
        for task in tasks:
            selected = [free[i] for i in range(len(free)) if (task.id, i) in assignments and solver.value(assignments[task.id, i])]
            runs = []
            for s in selected:
                if runs and runs[-1][1] == s:
                    runs[-1][1] = s + STEP
                else:
                    runs.append([s, s + STEP])
            for start, end in runs:
                db.add(ScheduleBlock(user_id=user_id, task_id=task.id, start_at=start, end_at=end, version=version))
    db.flush()
    blocks = db.scalars(select(ScheduleBlock).where(ScheduleBlock.user_id == user_id).order_by(ScheduleBlock.start_at)).all()
    db.add(ScheduleVersion(user_id=user_id, version=version, trigger=trigger, status=status, risks=risks, snapshot=[block_json(b) for b in blocks if b.end_at > clock]))
    db.flush()
    return {"version": version, "status": status, "risks": risks, "blocks": [block_json(b) for b in blocks]}
