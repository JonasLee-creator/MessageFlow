"""Adapt public client state to the unchanged V4 planner. No simulator truth."""
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from evaluation.domain import Task, Block
from evaluation.planners import plan
from evaluation.metrics import feasibility
from evaluation.predictor import bucket, quantile

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {'AUTO':'其他','EXPERIMENT':'实验','REPORT':'报告','PROGRAMMING':'编程',
    'REVIEW':'复习','MEMORIZATION':'背诵','READING':'阅读','EXAM_PREPARATION':'考试准备','OTHER':'其他'}


def normalize_confirmed_blocks(old, confirmed, now, locks, step):
    """Remove excess legacy reservations before treating them as commitments.

    User locks and active blocks remain exact. Never silently trim those: a
    conflicting manual reservation requires the user to adjust it first.
    """
    limits = {tid: math.ceil(value / step) * step for tid, value in confirmed.items()}
    protected = [b for b in old if (b.task_id, b.start, b.end) in locks or b.start <= now]
    result = list(protected)
    for b in protected:
        limits[b.task_id] -= b.end - max(now, b.start)
    if any(value < 0 for value in limits.values()):
        raise ValueError('锁定或正在执行的时段超过剩余工时，请先核对剩余耗时与锁定时段')
    for b in sorted((b for b in old if b not in protected), key=lambda b: (b.start, b.task_id)):
        take = min(b.end - b.start, limits[b.task_id])
        if take > 0:
            result.append(Block(b.task_id, b.start, b.start + take))
            limits[b.task_id] -= take
    return sorted(result, key=lambda b: b.start)


def timestamp(value):
    if not isinstance(value,str) or len(value)>64:
        raise ValueError('invalid timestamp')
    parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamps must include timezone')
    return parsed


def number(value, low, high):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError('invalid numeric value')
    return value


def text(value, limit=200):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:
        raise ValueError('invalid text field')
    return value.strip()


def rows(payload, key, limit):
    values = payload.get(key,[])
    if not isinstance(values,list) or len(values)>limit or any(not isinstance(v,dict) for v in values):
        raise ValueError(f'{key}: invalid or too many records (maximum {limit})')
    return values


def make_plan(payload, predictor_factory, now=None):
    if not isinstance(payload,dict) or payload.get('consent') is not True:
        raise ValueError('explicit model processing consent is required')
    # Only fields below are used. Notification text, Canvas tokens and API keys
    # are never part of the public scheduling contract.
    zone = ZoneInfo(text(payload.get('timezone','Asia/Shanghai'),80))
    clock = (now or datetime.now(timezone.utc)).astimezone(zone)
    origin = clock.replace(hour=0,minute=0,second=0,microsecond=0)
    current = math.ceil((clock-origin).total_seconds()/1800)*30
    config = json.loads((ROOT/'evaluation/config_integrated.json').read_text(encoding='utf-8'))
    settings = payload.get('settings',{})
    if not isinstance(settings,dict):
        raise ValueError('invalid settings')
    start = number(settings.get('startHour',8),0,23)
    end = number(settings.get('endHour',22),1,24)
    capacity = number(settings.get('dailyCapacityMinutes',360),30,840)
    if start!=int(start) or end!=int(end) or end<=start or capacity%30:
        raise ValueError('invalid available hours/capacity')
    config.update(working_hours=[int(start),int(end)],daily_capacity_minutes=int(capacity))
    workload_policy = settings.get('workloadPolicy', 'model')
    if workload_policy not in ('model', 'confirmed'):
        raise ValueError('invalid workload policy')
    horizon = current+14*1440
    minute = lambda value: round((timestamp(value).astimezone(zone)-origin).total_seconds()/60)
    at = lambda value: origin+timedelta(minutes=value)
    tasks, progress, ids, confirmed = [], {}, set(), {}
    for row in rows(payload,'tasks',30):
        tid = text(row.get('id'),100)
        if tid in ids:
            raise ValueError('duplicate task ID')
        ids.add(tid)
        estimate = number(row.get('minutes'),1,20160)
        remaining = number(row.get('remaining',estimate),0,20160)
        if remaining<=0:
            continue
        if remaining>estimate:
            raise ValueError('remaining work exceeds total estimate')
        release = minute(row['releasedAt']) if row.get('releasedAt') else current
        # Availability is a task property: advancing the decision clock must
        # not invalidate an already-running commitment.
        earliest = max(release, minute(row['earliestStartAt']) if row.get('earliestStartAt') else release)
        if release>current:
            raise ValueError('future released task is not available to planner')
        category = row.get('category','OTHER')
        if category not in CATEGORIES and category not in CATEGORIES.values():
            category = 'OTHER'
        difficulty,priority = number(row.get('difficulty',3),1,5),number(row.get('priority',5),1,10)
        if difficulty!=int(difficulty) or priority!=int(priority) or not isinstance(row.get('splittable',True),bool):
            raise ValueError('invalid task attributes')
        tasks.append(Task(tid,text(row.get('title')),CATEGORIES.get(category,category),str(row.get('course') or 'unknown')[:100],
            int(difficulty),int(priority),release,release,earliest,
            minute(row['deadline']) if row.get('deadline') else None,float(estimate),row.get('splittable',True)))
        progress[tid] = max(0.,estimate-remaining)
        confirmed[tid] = remaining
    active_ids = {t.id for t in tasks}
    fixed = []
    for row in rows(payload,'events',256):
        a,b = minute(row.get('start')),minute(row.get('end'))
        if b<=a:
            raise ValueError('fixed event must have positive duration')
        if b>current and a<horizon:
            fixed.append((a,b))
    old, locked = [], []
    for row in rows(payload,'blocks',512):
        if row.get('taskId') not in active_ids:
            continue
        a,b = minute(row.get('start')),minute(row.get('end'))
        if b<=a:
            raise ValueError('invalid plan block')
        if b<=current:
            continue
        if b>horizon or a%30 or b%30:
            raise ValueError('future blocks must fit the 14-day, 30-minute planning grid')
        block = Block(row['taskId'],a,b)
        old.append(block)
        if row.get('locked') is True:
            locked.append((block.task_id,a,b))
    config['_locked_blocks'] = locked
    if workload_policy == 'confirmed':
        config['_confirmed_remaining_minutes'] = confirmed
        old = normalize_confirmed_blocks(old, confirmed, current, set(locked), config['slot_minutes'])
    history, used = {}, {}
    predictor = predictor_factory(config)
    residuals=[]
    completed_ids=set()
    for row in rows(payload,'completedTasks',100):
        tid=text(row.get('id'),100)
        if tid in completed_ids or tid in active_ids:
            raise ValueError('duplicate completed or active task')
        completed_ids.add(tid)
        finish=timestamp(row.get('completedAt')).astimezone(zone)
        if finish>clock:
            raise ValueError('future completion cannot personalize a plan')
        release=minute(row['releasedAt']) if row.get('releasedAt') else minute(row['completedAt'])
        if at(release)>finish:
            raise ValueError('completion precedes task release')
        estimate=number(row.get('minutes'),1,20160)
        actual=number(row.get('actualMinutes'),.001,20160)
        category=CATEGORIES.get(row.get('category'),row.get('category','其他'))
        sample=Task(tid,text(row.get('title')),category,str(row.get('course') or 'unknown')[:100],
            int(number(row.get('difficulty',3),1,5)),int(number(row.get('priority',5),1,10)),
            release,release,release,minute(row['deadline']) if row.get('deadline') else None,float(estimate),True)
        mu,_,_=predictor.base(sample,origin,release)
        residuals.append(math.log(actual)-mu)
    if residuals:
        history['_duration']=(sum(residuals),len(residuals))
    seen_feedback = set()
    for row in rows(payload,'history',200):
        recorded = timestamp(row.get('recordedAt')).astimezone(zone)
        if recorded>clock:
            raise ValueError('future feedback cannot personalize a plan')
        key = text(row.get('id'),100)
        if key in seen_feedback:
            raise ValueError('duplicate execution feedback')
        seen_feedback.add(key)
        planned = timestamp(row.get('plannedStart')).astimezone(zone)
        if planned>clock:
            continue  # Early feedback is not an attempted future slot.
        minutes = number(row.get('plannedMinutes'),1,1440)
        if row.get('outcome') not in ('COMPLETED','SKIPPED','DELAYED'):
            raise ValueError('invalid feedback outcome')
        name = bucket(planned)
        successes,total = history.get(name,(0,0))
        slots = max(1,math.ceil(minutes/30))
        history[name] = (successes+(slots if row['outcome']=='COMPLETED' else 0),total+slots)
        # Match replay: an attempted slot consumes capacity even when skipped.
        for offset in range(0,math.ceil(minutes),30):
            moment = planned+timedelta(minutes=offset)
            if moment>=clock:
                break
            day = moment.date().isoformat()
            used[day] = used.get(day,0)+min(30,minutes-offset)
    for task in tasks:
        if not task.splittable and not any(b.task_id==task.id and b.start<=current<b.end for b in old):
            progress[task.id]=0.
    blocks,detail = plan('drp_full',tasks,progress,{},current,horizon,fixed,old,origin,config,predictor,history,used,control={})
    errors = feasibility(blocks,tasks,fixed,config['daily_capacity_minutes'],at,
        now=current,used=used,horizon=horizon,working_hours=config['working_hours'])
    if errors or any(Block(t,a,b) not in blocks for t,a,b in locked):
        raise ValueError('existing commitments conflict with available time; adjust fixed/locked blocks first')
    if workload_policy == 'confirmed':
        for task in tasks:
            allocated = sum(b.end-max(current,b.start) for b in blocks if b.task_id==task.id)
            if allocated > math.ceil(confirmed[task.id]/config['slot_minutes'])*config['slot_minutes']:
                raise ValueError('模型计划超出已确认的剩余工时，原计划保留')
    predictions, risks = [], []
    for task in tasks:
        mu,sigma,probabilities = predictor.predict(task,origin,current,history,True)
        p50,p80,p95 = (max(1,round(quantile(mu,sigma,q))) for q in (.5,.8,.95))
        predictions.append(dict(taskId=task.id,p50Minutes=p50,p80Minutes=p80,p95Minutes=p95,
            executionProbability=probabilities,estimatedRemainingMinutes=task.estimate-progress[task.id]))
        before_due = sum(max(0,min(b.end,task.deadline if task.deadline is not None else horizon)-max(b.start,current))
            for b in blocks if b.task_id==task.id)
        missing = max(0,round(task.estimate-progress[task.id]-before_due))
        if missing or (task.deadline is not None and task.deadline<current):
            risks.append(dict(title=task.title,message='截止前可用时间不足或已逾期，请核对耗时与期限',missingMinutes=missing))
    return dict(engine='chronoflow-v4',trained=bool(getattr(predictor,'trained',False)),generatedAt=clock.isoformat(),planningFrom=at(current).isoformat(),
        blocks=[dict(taskId=b.task_id,start=at(b.start).isoformat(),end=at(b.end).isoformat(),
                     locked=(b.task_id,b.start,b.end) in locked) for b in blocks],
        risks=risks,predictions=predictions,
        explanation='训练模型预测耗时分布与时段执行概率；V4在课表、容量、冻结承诺与风险之间选择滚动计划。',
        forecast=dict(deadlineLoss=detail.get('deadline_mean'),tailLoss=detail.get('deadline_cvar')))
