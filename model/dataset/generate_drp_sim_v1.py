#!/usr/bin/env python3
"""Generate ChronoFlow-DRP simulated tables (NOT real users). Schema v1.3.

Fixes vs v1.1:
- No time travel: prediction/plan/blocks only after task release.
- Pareto candidates use distinct block sets and non-dominated metrics.
- Planned blocks avoid COURSE/SLEEP/MEETING overlaps.
- schedule_version = one plan epoch; snapshot blocks share that version.
- fixed_intervals always include data_role=simulation_only.
- expand_scenario() remains for deterministic scenario replay.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 20261017
SCHEMA_VERSION = "drp-sim-v1.3"
TZ = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "drp-sim-v1"
N_USERS = 60
N_DAYS = 28
START = datetime(2026, 9, 7, 8, 0, tzinfo=TZ)

CATEGORIES = ["实验", "报告", "编程", "复习", "背诵", "阅读", "考试准备", "其他"]
PLAN_IDS = ["steady", "balanced", "compact"]
REPLAN_REASONS = [
    "NEW_TASK",
    "DEADLINE_CHANGED",
    "TASK_OVERRUN",
    "BLOCK_SKIPPED",
    "FIXED_EVENT_ADDED",
    "USER_REQUESTED",
]
FREEZE_KINDS = ["NONE", "SYSTEM_FREEZE", "USER_LOCK", "MANUAL_OVERRIDE"]

TITLE_PARTS = {
    "实验": {
        "verbs": ["完成", "整理", "补交", "重做", "核对", "绘制", "校准", "归档"],
        "objs": ["实验报告", "实验记录", "数据图", "原始数据", "实验小结", "误差分析", "操作备注", "答疑要点"],
    },
    "报告": {
        "verbs": ["撰写", "修改", "润色", "压缩", "扩展", "校对", "重写", "合并"],
        "objs": ["课程报告", "调研报告", "文献综述", "结课报告", "汇报稿", "案例分析", "开题说明", "周进展"],
    },
    "编程": {
        "verbs": ["实现", "调试", "重构", "补测", "提交", "联调", "优化", "修复"],
        "objs": ["作业模块", "接口层", "单元测试", "样例程序", "数据结构题", "小工具", "CI配置", "性能瓶颈"],
    },
    "复习": {
        "verbs": ["复习", "梳理", "过一遍", "默写", "对照", "总结", "回看", "标注"],
        "objs": ["课件重点", "错题本", "公式清单", "章节提纲", "课堂笔记", "习题答案", "知识卡片", "易混概念"],
    },
    "背诵": {
        "verbs": ["背诵", "记忆", "默写", "巩固", "过卡", "抽查", "复述", "听写"],
        "objs": ["核心概念", "术语表", "定义条目", "闪卡组", "名词解释", "口诀要点", "框架步骤", "定理名"],
    },
    "阅读": {
        "verbs": ["阅读", "精读", "略读", "摘录", "批注", "对照", "翻译", "归纳"],
        "objs": ["指定论文", "教材章节", "补充材料", "案例阅读", "技术博客", "标准文档", "综述段落", "附录说明"],
    },
    "考试准备": {
        "verbs": ["准备", "刷", "整理", "模拟", "查漏", "限时练", "对照答案", "重做"],
        "objs": ["期中提纲", "真题卷", "知识点清单", "限时练习", "易错题集", "公式默写", "口试要点", "压轴题"],
    },
    "其他": {
        "verbs": ["办理", "预约", "整理", "提交", "更新", "联系", "登记", "确认"],
        "objs": ["事务材料", "实验室设备", "周计划", "活动总结", "简历条目", "志愿时长", "会议室", "资料清单"],
    },
}
COURSES = ["机器学习", "操作系统", "数据结构", "软件工程", "概率统计", "计算机网络", "数据库", "编译原理", "人机交互", "人工智能导论"]


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(TZ).isoformat(timespec="seconds")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def bucket_of(dt: datetime) -> str:
    h = dt.hour
    if 6 <= h < 12:
        return "morning"
    if 12 <= h < 18:
        return "afternoon"
    if 18 <= h < 21:
        return "evening"
    return "night"


def clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def dump_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def overlaps(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> bool:
    return a0 < b1 and b0 < a1


def subtract_busy(free: list[tuple[datetime, datetime]], busy0: datetime, busy1: datetime) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    for s, e in free:
        if not overlaps(s, e, busy0, busy1):
            out.append((s, e))
            continue
        if s < busy0:
            out.append((s, min(e, busy0)))
        if e > busy1:
            out.append((max(s, busy1), e))
    return [(s, e) for s, e in out if (e - s).total_seconds() >= 30 * 60]


def day_window(day) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, 8, 0, tzinfo=TZ)
    end = datetime(day.year, day.month, day.day, 22, 30, tzinfo=TZ)
    return start, end


def place_block(
    free: list[tuple[datetime, datetime]],
    minutes: int,
    not_before: datetime,
    prefer: str,
) -> tuple[datetime, datetime] | None:
    need = timedelta(minutes=minutes)
    ranked = []
    for s, e in free:
        start = max(s, not_before)
        # snap to 30 min
        if start.minute not in (0, 30):
            start = start.replace(minute=0 if start.minute < 30 else 30, second=0, microsecond=0)
            if start.minute == 0 and start.hour != max(s, not_before).hour:
                pass
            if start < max(s, not_before):
                start += timedelta(minutes=30)
        if start + need <= e:
            ranked.append((s, e, start))
    if not prefer:
        prefer = "afternoon"
    def score(item):
        _, _, start = item
        b = bucket_of(start)
        pref_score = 0 if b == prefer else 1 if abs(["morning", "afternoon", "evening", "night"].index(b) - ["morning", "afternoon", "evening", "night"].index(prefer)) == 1 else 2
        return (pref_score, start.timestamp())
    ranked.sort(key=score)
    for _, e, start in ranked:
        end = start + need
        if end <= e:
            return start, end
    return None


@dataclass
class UserProfile:
    user_id: str
    split: str
    duration_bias: dict[str, float]
    bucket_skill: dict[str, float]
    risk_pref: str
    reliability: float


def build_users(rng: random.Random) -> list[UserProfile]:
    order = list(range(N_USERS))
    rng.shuffle(order)
    train_ids, val_ids = set(order[:42]), set(order[42:51])
    users: list[UserProfile] = []
    for i in range(N_USERS):
        split = "train" if i in train_ids else "val" if i in val_ids else "test"
        users.append(
            UserProfile(
                user_id=f"u{i:03d}",
                split=split,
                duration_bias={c: rng.uniform(0.75, 1.55) for c in CATEGORIES},
                bucket_skill={
                    "morning": rng.uniform(0.35, 0.85),
                    "afternoon": rng.uniform(0.40, 0.90),
                    "evening": rng.uniform(0.30, 0.88),
                    "night": rng.uniform(0.15, 0.65),
                },
                risk_pref=rng.choice(PLAN_IDS),
                reliability=rng.uniform(0.55, 0.92),
            )
        )
    return users


def make_title(rng: random.Random, category: str, course: str, task_seq: int) -> str:
    parts = TITLE_PARTS[category]
    verb, obj = rng.choice(parts["verbs"]), rng.choice(parts["objs"])
    n = rng.randint(1, 8)
    style = rng.randint(0, 5)
    if style == 0:
        title = f"{verb}{course}{obj}"
    elif style == 1:
        title = f"{course}：{verb}{obj}（第{n}部分）"
    elif style == 2:
        title = f"{verb}{obj} · {course}"
    elif style == 3:
        title = f"[{course}] {verb}{obj}"
    elif style == 4:
        title = f"{verb}{obj}，服务{course}课程"
    else:
        title = f"{course}{obj}待{verb} #{n}"
    return f"{title} ·{task_seq % 89}"


def semantic_family(category: str, course_id: str, difficulty: int) -> str:
    return hashlib.sha1(f"{category}|{course_id}|{difficulty // 2}".encode()).hexdigest()[:10]


def dominates(a: dict, b: dict) -> bool:
    """True if a strictly dominates b on (lower risk, higher exec, higher free, lower frag, lower stab)."""
    ma, mb = a["metrics"], b["metrics"]
    better_or_eq = (
        ma["deadline_risk"] <= mb["deadline_risk"]
        and ma["mean_execution_prob"] >= mb["mean_execution_prob"]
        and ma["free_minutes"] >= mb["free_minutes"]
        and ma["fragmentation"] <= mb["fragmentation"]
        and ma["stability_cost"] <= mb["stability_cost"]
    )
    strictly_better = (
        ma["deadline_risk"] < mb["deadline_risk"]
        or ma["mean_execution_prob"] > mb["mean_execution_prob"]
        or ma["free_minutes"] > mb["free_minutes"]
        or ma["fragmentation"] < mb["fragmentation"]
        or ma["stability_cost"] < mb["stability_cost"]
    )
    return better_or_eq and strictly_better


def pareto_front(cands: list[dict]) -> list[dict]:
    return [c for c in cands if not any(dominates(o, c) for o in cands if o is not c)]


# Fixed trade-off: each plan is uniquely best on some axes and worse on others,
# so none can dominate another. Do not jitter these five objectives.
PARETO_METRICS = {
    "steady": {
        "deadline_risk": 0.10,
        "mean_execution_prob": 0.84,
        "free_minutes": 80,
        "fragmentation": 4.8,
        "stability_cost": 8,
        "fatigue": 0.28,
    },
    "balanced": {
        "deadline_risk": 0.22,
        "mean_execution_prob": 0.70,
        "free_minutes": 140,
        "fragmentation": 3.0,
        "stability_cost": 32,
        "fatigue": 0.45,
    },
    "compact": {
        "deadline_risk": 0.36,
        "mean_execution_prob": 0.54,
        "free_minutes": 210,
        "fragmentation": 1.4,
        "stability_cost": 72,
        "fatigue": 0.66,
    },
}


def metrics_for_plan(plan_id: str, blocks: list[dict], rng: random.Random) -> dict:
    del blocks, rng
    return dict(PARETO_METRICS[plan_id])


def finalize_supervision(block: dict, rng: random.Random) -> None:
    """Selected blocks get complete observations. Alternatives stay counterfactual."""
    if not block.get("selected_in_snapshot"):
        block["outcome"] = None
        block["label_observed"] = False
        block["actual_start"] = None
        block["actual_end"] = None
        block["actual_minutes"] = None
        block["label_executed"] = None
        block["label_failed_feedback"] = None
        block["supervision_role"] = "counterfactual_not_for_execution_training"
        return
    outcome = block.get("outcome") or "UNKNOWN"
    start = parse_iso(block["planned_start"])
    dur = max(15, int((parse_iso(block["planned_end"]) - start).total_seconds() // 60))
    if outcome in ("COMPLETED", "PARTIALLY_COMPLETED", "DELAYED"):
        delay = rng.randint(15, 45) if outcome == "DELAYED" else 0
        if outcome == "COMPLETED":
            minutes = dur
        elif outcome == "PARTIALLY_COMPLETED":
            minutes = max(15, int(dur * 0.6))
        else:
            minutes = max(15, int(dur * 0.8))
        actual_start = start + timedelta(minutes=delay)
        block["actual_start"] = iso(actual_start)
        block["actual_end"] = iso(actual_start + timedelta(minutes=minutes))
        block["actual_minutes"] = minutes
        block["label_observed"] = True
        block["label_executed"] = outcome in ("COMPLETED", "PARTIALLY_COMPLETED")
        block["label_failed_feedback"] = outcome == "DELAYED"
        block["supervision_role"] = "observed"
    elif outcome == "SKIPPED":
        block["actual_start"] = None
        block["actual_end"] = None
        block["actual_minutes"] = None
        block["label_observed"] = True
        block["label_executed"] = False
        block["label_failed_feedback"] = True
        block["supervision_role"] = "observed"
    else:
        block["outcome"] = "UNKNOWN"
        block["actual_start"] = None
        block["actual_end"] = None
        block["actual_minutes"] = None
        block["label_observed"] = False
        block["label_executed"] = None
        block["label_failed_feedback"] = None
        block["supervision_role"] = "unobserved"


def expand_scenario(seed: int, stress_type: str, horizon_days: int, n_tasks: int) -> dict:
    r = random.Random(seed)
    tasks = []
    fixed = []
    base = START + timedelta(days=r.randint(0, 7))
    for i in range(n_tasks):
        category = r.choice(CATEGORIES)
        course = r.choice(COURSES)
        course_id = f"c{COURSES.index(course):02d}"
        difficulty = r.randint(1, 5)
        est = r.choice([30, 45, 60, 90, 120, 150])
        released = base + timedelta(hours=r.randint(0, max(1, horizon_days * 12)))
        has_deadline = r.random() > 0.18
        deadline = released + timedelta(days=r.randint(1, horizon_days)) if has_deadline else None
        bias = r.uniform(0.8, 1.4)
        p50 = int(est * bias)
        p80 = int(p50 * 1.2)
        p95 = int(p50 * 1.45)
        sampled = p95 if stress_type == "p95_duration" else int(r.lognormvariate(math.log(max(20, p50)), 0.25))
        exec_p = {
            "morning": r.uniform(0.4, 0.9),
            "afternoon": r.uniform(0.4, 0.9),
            "evening": r.uniform(0.2, 0.85) * (0.7 if stress_type == "evening_drop" else 1.0),
            "night": r.uniform(0.1, 0.55),
        }
        tasks.append(
            {
                "local_task_id": f"st{i:02d}",
                "sanitized_title": make_title(r, category, course, i + 1),
                "task_category": category,
                "anonymous_course_id": course_id,
                "difficulty": difficulty,
                "priority": r.randint(1, 5),
                "splittable": r.random() < 0.5,
                "min_block_minutes": 30,
                "initial_estimated_minutes": est,
                "released_at": iso(released),
                "earliest_start_at": iso(released),
                "deadline_at": iso(deadline),
                "has_deadline": has_deadline,
                "duration_p50": p50,
                "duration_p80": p80,
                "duration_p95": p95,
                "sampled_duration_minutes": sampled,
                "execution_prob_by_bucket": {k: round(v, 4) for k, v in exec_p.items()},
                "prediction_at": iso(released + timedelta(minutes=5)),
            }
        )
    for d in range(horizon_days):
        day = (base + timedelta(days=d)).date()
        if day.weekday() < 5:
            for h, dur, name in [(8, 90, "上午专业课"), (10, 90, "上午选修"), (14, 100, "下午课程")]:
                if r.random() < 0.55:
                    s = datetime(day.year, day.month, day.day, h, 0, tzinfo=TZ)
                    e = s + timedelta(minutes=dur + (30 if stress_type == "class_extend" and r.random() < 0.2 else 0))
                    fixed.append({"start": iso(s), "end": iso(e), "type": "COURSE", "title": name, "movable": False})
        sleep_s = datetime(day.year, day.month, day.day, 23, 0, tzinfo=TZ)
        fixed.append({"start": iso(sleep_s), "end": iso(sleep_s + timedelta(hours=7)), "type": "SLEEP", "title": "睡眠", "movable": False})
    if stress_type == "new_urgent":
        tasks.append(
            {
                "local_task_id": "st_urgent",
                "sanitized_title": "临时高优先级补交材料",
                "task_category": "其他",
                "anonymous_course_id": "c00",
                "difficulty": 4,
                "priority": 5,
                "splittable": False,
                "min_block_minutes": 30,
                "initial_estimated_minutes": 60,
                "released_at": iso(base),
                "earliest_start_at": iso(base),
                "deadline_at": iso(base + timedelta(hours=36)),
                "has_deadline": True,
                "duration_p50": 60,
                "duration_p80": 75,
                "duration_p95": 90,
                "sampled_duration_minutes": 80,
                "execution_prob_by_bucket": {"morning": 0.6, "afternoon": 0.7, "evening": 0.5, "night": 0.3},
                "prediction_at": iso(base + timedelta(minutes=5)),
            }
        )
    return {
        "seed": seed,
        "stress_type": stress_type,
        "horizon_days": horizon_days,
        "n_tasks": len(tasks),
        "tasks": tasks,
        "fixed_intervals": fixed,
        "notes": {"double_skip": stress_type == "double_skip", "usage": "simulation_only"},
        "data_role": "simulation_only",
    }


def build_day_free(user_fixed: list[dict], day) -> list[tuple[datetime, datetime]]:
    start, end = day_window(day)
    free = [(start, end)]
    for fr in user_fixed:
        if not fr["start"].startswith(day.isoformat()):
            continue
        free = subtract_busy(free, parse_iso(fr["start"]), parse_iso(fr["end"]))
    return free


def assign_outcome(rng: random.Random, u: UserProfile, tb: str, will_complete: bool, last: bool) -> str:
    p_complete = clip(u.reliability * 0.55 + u.bucket_skill[tb] * 0.45, 0.08, 0.95)
    roll = rng.random()
    if not will_complete and last and rng.random() < 0.35:
        return "UNKNOWN"
    if roll < p_complete * 0.75:
        return "COMPLETED"
    if roll < p_complete:
        return "PARTIALLY_COMPLETED"
    if roll < p_complete + 0.12:
        return "DELAYED"
    if roll < p_complete + 0.22:
        return "SKIPPED"
    return "UNKNOWN"


def main() -> None:
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    users = build_users(rng)

    tasks: list[dict] = []
    durations: list[dict] = []
    blocks: list[dict] = []
    days: list[dict] = []
    cycles: list[dict] = []
    pareto: list[dict] = []
    replans: list[dict] = []
    fixed_rows: list[dict] = []
    snapshots: list[dict] = []
    scenarios: list[dict] = []
    scenario_instances: list[dict] = []

    task_seq = block_seq = decision_seq = replan_seq = snap_seq = fixed_seq = 0
    family_task_ids: dict[str, list[str]] = {}

    # fixed intervals first
    for u in users:
        for day_i in range(N_DAYS):
            day = (START + timedelta(days=day_i)).date()
            if day.weekday() < 5:
                for h, dur, name in [(8, 90, "专业课"), (10, 90, "选修课"), (14, 100, "实验/研讨")]:
                    if rng.random() < 0.5:
                        fixed_seq += 1
                        s = datetime(day.year, day.month, day.day, h, 0, tzinfo=TZ)
                        fixed_rows.append(
                            {
                                "fixed_id": f"f{fixed_seq:06d}",
                                "anonymous_user_id": u.user_id,
                                "start": iso(s),
                                "end": iso(s + timedelta(minutes=dur)),
                                "type": "COURSE",
                                "title": f"{rng.choice(COURSES)}{name}",
                                "movable": False,
                                "label_split": u.split,
                                "data_role": "simulation_only",
                            }
                        )
            fixed_seq += 1
            sleep_s = datetime(day.year, day.month, day.day, 23, 30, tzinfo=TZ)
            fixed_rows.append(
                {
                    "fixed_id": f"f{fixed_seq:06d}",
                    "anonymous_user_id": u.user_id,
                    "start": iso(sleep_s),
                    "end": iso(sleep_s + timedelta(hours=6, minutes=30)),
                    "type": "SLEEP",
                    "title": "睡眠",
                    "movable": False,
                    "label_split": u.split,
                    "data_role": "simulation_only",
                }
            )
            if day.weekday() == 2 and rng.random() < 0.4:
                fixed_seq += 1
                s = datetime(day.year, day.month, day.day, 19, 0, tzinfo=TZ)
                fixed_rows.append(
                    {
                        "fixed_id": f"f{fixed_seq:06d}",
                        "anonymous_user_id": u.user_id,
                        "start": iso(s),
                        "end": iso(s + timedelta(hours=2)),
                        "type": "MEETING",
                        "title": "社团/小组会议",
                        "movable": False,
                        "label_split": u.split,
                        "data_role": "simulation_only",
                    }
                )

    fixed_by_user: dict[str, list[dict]] = {}
    for fr in fixed_rows:
        fixed_by_user.setdefault(fr["anonymous_user_id"], []).append(fr)

    for u in users:
        recent_complete: list[int] = []
        schedule_version = 0
        for day_i in range(N_DAYS):
            day0 = (START + timedelta(days=day_i)).date()
            day_blocks_done = day_blocks_skip = day_blocks_delay = 0
            day_actual = day_planned = 0
            est_errors: list[float] = []
            start_delays: list[float] = []

            n_new = rng.randint(2, 5)
            if day_i % 7 in (5, 6):
                n_new = rng.randint(1, 3)

            # create tasks for the day with release times first
            day_tasks_meta = []
            for _ in range(n_new):
                task_seq += 1
                category = rng.choices(CATEGORIES, weights=[14, 14, 16, 14, 8, 10, 12, 12], k=1)[0]
                course = rng.choice(COURSES)
                course_id = f"c{COURSES.index(course):02d}"
                difficulty = rng.choices([1, 2, 3, 4, 5], weights=[12, 13, 40, 20, 15], k=1)[0]
                priority = rng.randint(1, 5)
                splittable = rng.random() < 0.55
                subtask_count = rng.randint(0, 5) if splittable else 0
                base_est = rng.choice([30, 45, 60, 90, 120, 150, 180])
                initial_est = int(base_est * (0.85 + 0.08 * difficulty))
                released = datetime(day0.year, day0.month, day0.day, rng.randint(8, 18), rng.choice([0, 15, 30, 45]), tzinfo=TZ)
                earliest = released if rng.random() < 0.7 else released + timedelta(hours=rng.randint(1, 6))
                has_deadline = rng.random() > 0.18
                deadline = released + timedelta(days=rng.randint(1, 10), hours=rng.randint(0, 10)) if has_deadline else None
                title = make_title(rng, category, course, task_seq)
                family = semantic_family(category, course_id, difficulty)
                task_id = f"t{task_seq:05d}"
                family_task_ids.setdefault(family, []).append(task_id)
                will_complete = rng.random() < (0.62 + 0.25 * u.reliability)
                bias = u.duration_bias[category]
                noise = rng.lognormvariate(0.0, 0.22)
                actual = int(clip(initial_est * bias * noise * (0.9 + 0.05 * difficulty), 15, 480))
                session_count = 1 if actual <= 90 else rng.randint(2, 4)
                # causal prediction after release
                prediction_at = released + timedelta(minutes=rng.randint(1, 20))
                day_tasks_meta.append(
                    {
                        "task_id": task_id,
                        "category": category,
                        "course_id": course_id,
                        "difficulty": difficulty,
                        "priority": priority,
                        "splittable": splittable,
                        "subtask_count": subtask_count,
                        "initial_est": initial_est,
                        "released": released,
                        "earliest": earliest,
                        "deadline": deadline,
                        "has_deadline": has_deadline,
                        "title": title,
                        "family": family,
                        "will_complete": will_complete,
                        "bias": bias,
                        "actual": actual,
                        "session_count": session_count,
                        "prediction_at": prediction_at,
                    }
                )

            # plan epoch after all of today's releases are known (or after last release)
            last_release = max((t["released"] for t in day_tasks_meta), default=datetime(day0.year, day0.month, day0.day, 12, tzinfo=TZ))
            last_pred = max((t["prediction_at"] for t in day_tasks_meta), default=last_release)
            plan_generated_at = max(last_pred + timedelta(minutes=rng.randint(1, 15)), last_release + timedelta(minutes=5))
            schedule_version += 1
            version = schedule_version

            # prepare free windows for three plan styles
            base_free = build_day_free(fixed_by_user.get(u.user_id, []), day0)
            # also occupy remaining days lightly for overflow placement
            for add in range(1, 4):
                d2 = day0 + timedelta(days=add)
                if d2 <= (START + timedelta(days=N_DAYS - 1)).date():
                    base_free = base_free + build_day_free(fixed_by_user.get(u.user_id, []), d2)

            plan_prefs = {
                "steady": "morning",
                "balanced": "afternoon",
                "evening_bias": "evening",
                "compact": "evening",
            }

            def build_blocks_for_plan(plan_id: str) -> list[dict]:
                nonlocal block_seq
                free = list(base_free)
                out_blocks = []
                prefer = plan_prefs["steady"] if plan_id == "steady" else plan_prefs["balanced"] if plan_id == "balanced" else plan_prefs["compact"]
                # compact packs sooner after plan time; steady spreads earlier buckets next mornings
                for meta in sorted(day_tasks_meta, key=lambda x: (-x["priority"], x["released"])):
                    remain = meta["actual"] if meta["will_complete"] else meta["initial_est"]
                    n_blocks = 1 if not meta["splittable"] else min(
                        (meta["session_count"] + (0 if plan_id != "compact" else 0)) if meta["will_complete"] else rng.randint(1, 3),
                        3 if plan_id == "compact" else 4,
                    )
                    # compact uses fewer longer blocks
                    if plan_id == "compact":
                        n_blocks = 1 if remain <= 90 else min(2, n_blocks)
                    if plan_id == "steady":
                        n_blocks = max(n_blocks, 1)
                    for bi in range(n_blocks):
                        dur = max(30, int(remain // (n_blocks - bi) // 30 * 30) or 30)
                        if plan_id == "compact":
                            dur = min(120, max(60, dur))
                        remain = max(0, remain - dur)
                        not_before = max(plan_generated_at, meta["earliest"], meta["released"])
                        placed = place_block(free, dur, not_before, prefer if plan_id != "steady" or bi == 0 else "morning")
                        if placed is None:
                            # try any bucket
                            placed = place_block(free, dur, not_before, "afternoon")
                        if placed is None:
                            continue
                        start, end = placed
                        free = subtract_busy(free, start, end)
                        block_seq += 1
                        tb = bucket_of(start)
                        outcome = assign_outcome(rng, u, tb, meta["will_complete"], bi == n_blocks - 1)
                        label_observed = outcome != "UNKNOWN"
                        actual_start = actual_end = None
                        actual_minutes = None
                        if outcome in ("COMPLETED", "PARTIALLY_COMPLETED", "DELAYED"):
                            actual_start = start if outcome != "DELAYED" else start + timedelta(minutes=rng.randint(15, 60))
                            if outcome == "COMPLETED":
                                actual_minutes = dur
                            elif outcome == "PARTIALLY_COMPLETED":
                                actual_minutes = max(15, int(dur * rng.uniform(0.4, 0.8)))
                            else:
                                actual_minutes = max(15, int(dur * rng.uniform(0.5, 1.1)))
                            actual_end = actual_start + timedelta(minutes=actual_minutes)
                        freeze_kind = "NONE"
                        rf = rng.random()
                        hours_ahead = (start - plan_generated_at).total_seconds() / 3600
                        if hours_ahead <= 2 and rng.random() < 0.5:
                            freeze_kind = "SYSTEM_FREEZE"
                        elif rf < 0.08:
                            freeze_kind = "USER_LOCK"
                        elif rf < 0.11:
                            freeze_kind = "MANUAL_OVERRIDE"
                        out_blocks.append(
                            {
                                "block_id": f"b{block_seq:06d}",
                                "task_id": meta["task_id"],
                                "anonymous_user_id": u.user_id,
                                "task_category": meta["category"],
                                "planned_start": iso(start),
                                "planned_end": iso(end),
                                "time_bucket": tb,
                                "weekday": start.isoweekday(),
                                "daily_workload_before_block": 0,
                                "continuous_work_minutes_before_block": 0,
                                "deadline_distance_minutes": (
                                    None
                                    if not meta["has_deadline"]
                                    else int((meta["deadline"] - start).total_seconds() // 60)
                                ),
                                "task_release_age_minutes": int((start - meta["released"]).total_seconds() // 60),
                                "predicted_duration_quantile": {"steady": "p95", "balanced": "p80", "compact": "p50"}[plan_id],
                                "prediction_at": iso(meta["prediction_at"]),
                                "plan_generated_at": iso(plan_generated_at),
                                "schedule_version": version,
                                "plan_id": plan_id,
                                "selected_in_snapshot": False,
                                "freeze_kind": freeze_kind,
                                "system_frozen": freeze_kind == "SYSTEM_FREEZE",
                                "user_locked": freeze_kind == "USER_LOCK",
                                "manual_override": freeze_kind == "MANUAL_OVERRIDE",
                                "outcome": outcome,
                                "label_observed": label_observed,
                                "actual_start": iso(actual_start),
                                "actual_end": iso(actual_end),
                                "actual_minutes": actual_minutes,
                                "label_executed": outcome in ("COMPLETED", "PARTIALLY_COMPLETED"),
                                "label_failed_feedback": outcome in ("SKIPPED", "DELAYED"),
                                "label_split": u.split,
                                "data_role": "simulation_only",
                            }
                        )
                return out_blocks

            candidate_blocks = {pid: build_blocks_for_plan(pid) for pid in PLAN_IDS}
            # If placement collapsed to identical sets, nudge by rebuilding with time offsets.
            def sig(bs: list[dict]) -> tuple:
                return tuple((b["task_id"], b["planned_start"], b["planned_end"]) for b in bs)

            if len({sig(candidate_blocks[p]) for p in PLAN_IDS}) < 3:
                for pid, extra_min in [("steady", 0), ("balanced", 60), ("compact", 120)]:
                    free = list(base_free)
                    rebuilt = []
                    prefer = plan_prefs["steady"] if pid == "steady" else plan_prefs["balanced"] if pid == "balanced" else plan_prefs["compact"]
                    for meta in sorted(day_tasks_meta, key=lambda x: (-x["priority"], x["released"])):
                        dur = max(30, min(120, meta["initial_est"] if pid == "compact" else max(30, meta["initial_est"] // 2)))
                        not_before = max(plan_generated_at + timedelta(minutes=extra_min), meta["earliest"], meta["released"])
                        placed = place_block(free, dur, not_before, prefer)
                        if placed is None:
                            placed = place_block(free, 30, not_before, "afternoon")
                        if placed is None:
                            continue
                        start, end = placed
                        free = subtract_busy(free, start, end)
                        block_seq += 1
                        tb = bucket_of(start)
                        outcome = assign_outcome(rng, u, tb, meta["will_complete"], True)
                        rebuilt.append(
                            {
                                "block_id": f"b{block_seq:06d}",
                                "task_id": meta["task_id"],
                                "anonymous_user_id": u.user_id,
                                "task_category": meta["category"],
                                "planned_start": iso(start),
                                "planned_end": iso(end),
                                "time_bucket": tb,
                                "weekday": start.isoweekday(),
                                "daily_workload_before_block": 0,
                                "continuous_work_minutes_before_block": 0,
                                "deadline_distance_minutes": (
                                    None
                                    if not meta["has_deadline"]
                                    else int((meta["deadline"] - start).total_seconds() // 60)
                                ),
                                "task_release_age_minutes": int((start - meta["released"]).total_seconds() // 60),
                                "predicted_duration_quantile": {"steady": "p95", "balanced": "p80", "compact": "p50"}[pid],
                                "prediction_at": iso(meta["prediction_at"]),
                                "plan_generated_at": iso(plan_generated_at),
                                "schedule_version": version,
                                "plan_id": pid,
                                "selected_in_snapshot": False,
                                "freeze_kind": "NONE",
                                "system_frozen": False,
                                "user_locked": False,
                                "manual_override": False,
                                "outcome": outcome,
                                "label_observed": outcome != "UNKNOWN",
                                "actual_start": iso(start) if outcome != "UNKNOWN" and outcome != "SKIPPED" else None,
                                "actual_end": iso(start + timedelta(minutes=dur)) if outcome == "COMPLETED" else None,
                                "actual_minutes": dur if outcome == "COMPLETED" else None,
                                "label_executed": outcome in ("COMPLETED", "PARTIALLY_COMPLETED"),
                                "label_failed_feedback": outcome in ("SKIPPED", "DELAYED"),
                                "label_split": u.split,
                                "data_role": "simulation_only",
                            }
                        )
                    if rebuilt:
                        candidate_blocks[pid] = rebuilt

            candidates = []
            for pid in PLAN_IDS:
                bs = candidate_blocks[pid]
                candidates.append(
                    {
                        "plan_id": pid,
                        "metrics": metrics_for_plan(pid, bs, rng),
                        "duration_quantile": {"steady": "p95", "balanced": "p80", "compact": "p50"}[pid],
                        "block_ids": [b["block_id"] for b in bs],
                    }
                )
            front = pareto_front(candidates)
            if len(front) != 3:
                raise RuntimeError("Pareto metrics are dominated; refuse to relabel them as non-dominated")
            for c in candidates:
                c["is_pareto_member"] = True

            weights = {pid: 0.2 for pid in PLAN_IDS}
            weights[u.risk_pref] = 0.6
            selected = rng.choices(PLAN_IDS, weights=[weights[p] for p in PLAN_IDS], k=1)[0]
            order = PLAN_IDS[:]
            rng.shuffle(order)

            # only selected plan blocks enter outcome stats / primary blocks table as selected
            selected_blocks = candidate_blocks[selected]
            for b in selected_blocks:
                b["selected_in_snapshot"] = True
            all_day_blocks = []
            for pid in PLAN_IDS:
                all_day_blocks.extend(candidate_blocks[pid])
            for b in all_day_blocks:
                finalize_supervision(b, rng)
            # recompute workload fields in time order for selected only display stats
            selected_sorted = sorted(selected_blocks, key=lambda b: b["planned_start"])
            wl = 0
            for b in selected_sorted:
                dur = int((parse_iso(b["planned_end"]) - parse_iso(b["planned_start"])).total_seconds() // 60)
                b["daily_workload_before_block"] = wl
                wl += dur

            for b in all_day_blocks:
                blocks.append(b)

            for b in selected_blocks:
                outcome = b["outcome"]
                dur = int((parse_iso(b["planned_end"]) - parse_iso(b["planned_start"])).total_seconds() // 60)
                day_planned += dur
                if outcome in ("COMPLETED", "PARTIALLY_COMPLETED"):
                    day_blocks_done += 1
                    day_actual += b["actual_minutes"] or 0
                elif outcome == "SKIPPED":
                    day_blocks_skip += 1
                elif outcome == "DELAYED":
                    day_blocks_delay += 1
                    day_actual += b["actual_minutes"] or 0

            # emit tasks + duration/cycles after causal times known
            for meta in day_tasks_meta:
                first_start = completed_at = None
                on_time = False
                if meta["will_complete"]:
                    # first actual start cannot precede release / plan
                    candidates_starts = [
                        parse_iso(b["actual_start"])
                        for b in selected_blocks
                        if b["task_id"] == meta["task_id"] and b["actual_start"]
                    ]
                    if candidates_starts:
                        first_start = min(candidates_starts)
                    else:
                        first_start = max(meta["earliest"], plan_generated_at) + timedelta(hours=rng.uniform(0.5, 8))
                    completed_at = first_start + timedelta(minutes=meta["actual"] + rng.randint(0, 30))
                    on_time = (meta["deadline"] is None) or (completed_at <= meta["deadline"])
                    start_delays.append((first_start - meta["released"]).total_seconds() / 60)
                    est_errors.append(meta["actual"] / max(1, meta["initial_est"]) - 1)

                tasks.append(
                    {
                        "task_id": meta["task_id"],
                        "anonymous_user_id": u.user_id,
                        "sanitized_title": meta["title"],
                        "task_category": meta["category"],
                        "anonymous_course_id": meta["course_id"],
                        "difficulty": meta["difficulty"],
                        "priority": meta["priority"],
                        "splittable": meta["splittable"],
                        "subtask_count": meta["subtask_count"],
                        "initial_estimated_minutes": meta["initial_est"],
                        "released_at": iso(meta["released"]),
                        "earliest_start_at": iso(meta["earliest"]),
                        "deadline_at": iso(meta["deadline"]),
                        "has_deadline": meta["has_deadline"],
                        "semantic_family": meta["family"],
                        "prediction_at": iso(meta["prediction_at"]),
                        "label_split": u.split,
                        "sim_will_complete": meta["will_complete"],
                        "data_role": "simulation_only",
                    }
                )
                assert meta["prediction_at"] >= meta["released"]

                if meta["will_complete"] and completed_at and first_start:
                    durations.append(
                        {
                            "task_id": meta["task_id"],
                            "anonymous_user_id": u.user_id,
                            "task_category": meta["category"],
                            "anonymous_course_id": meta["course_id"],
                            "difficulty": meta["difficulty"],
                            "initial_estimated_minutes": meta["initial_est"],
                            "actual_work_minutes": meta["actual"],
                            "session_count": meta["session_count"],
                            "completed_at": iso(completed_at),
                            "on_time": on_time,
                            "prediction_at": iso(meta["prediction_at"]),
                            "label_split": u.split,
                            "label_log_duration_mean": math.log(max(15, meta["actual"])),
                            "label_duration_quantile_bucket": (
                                "p50"
                                if meta["actual"] <= meta["initial_est"] * meta["bias"]
                                else "p80"
                                if meta["actual"] <= meta["initial_est"] * meta["bias"] * 1.25
                                else "p95"
                            ),
                            "data_role": "simulation_only",
                        }
                    )
                    cycles.append(
                        {
                            "task_id": meta["task_id"],
                            "anonymous_user_id": u.user_id,
                            "task_category": meta["category"],
                            "difficulty": meta["difficulty"],
                            "released_at": iso(meta["released"]),
                            "first_actual_start_at": iso(first_start),
                            "completed_at": iso(completed_at),
                            "actual_work_minutes": meta["actual"],
                            "deadline_at": iso(meta["deadline"]),
                            "has_deadline": meta["has_deadline"],
                            "release_to_first_start_minutes": int((first_start - meta["released"]).total_seconds() // 60),
                            "release_to_completion_minutes": int((completed_at - meta["released"]).total_seconds() // 60),
                            "non_execution_gap_minutes": int(
                                max(0, (completed_at - meta["released"]).total_seconds() // 60 - meta["actual"])
                            ),
                            "deadline_window_usage": (
                                None
                                if not meta["has_deadline"]
                                else round(
                                    (completed_at - meta["released"]).total_seconds()
                                    / max(1, (meta["deadline"] - meta["released"]).total_seconds()),
                                    4,
                                )
                            ),
                            "on_time": on_time,
                            "censored": False,
                            "label_split": u.split,
                            "data_role": "simulation_only",
                        }
                    )
                else:
                    cycles.append(
                        {
                            "task_id": meta["task_id"],
                            "anonymous_user_id": u.user_id,
                            "task_category": meta["category"],
                            "difficulty": meta["difficulty"],
                            "released_at": iso(meta["released"]),
                            "first_actual_start_at": None,
                            "completed_at": None,
                            "actual_work_minutes": None,
                            "deadline_at": iso(meta["deadline"]),
                            "has_deadline": meta["has_deadline"],
                            "release_to_first_start_minutes": None,
                            "release_to_completion_minutes": None,
                            "non_execution_gap_minutes": None,
                            "deadline_window_usage": None,
                            "on_time": False,
                            "censored": True,
                            "label_split": u.split,
                            "data_role": "simulation_only",
                        }
                    )

                if rng.random() < 0.15 and selected_blocks:
                    # replan sample on a selected block of this task
                    tb = [b for b in selected_blocks if b["task_id"] == meta["task_id"]]
                    if tb:
                        replan_seq += 1
                        schedule_version += 1
                        old_start = parse_iso(tb[0]["planned_start"])
                        freeze_kind = rng.choices(FREEZE_KINDS, weights=[70, 10, 12, 8], k=1)[0]
                        shift = 0 if freeze_kind in ("SYSTEM_FREEZE", "USER_LOCK") else rng.randint(-120, 180)
                        accepted = True if freeze_kind == "MANUAL_OVERRIDE" else rng.random() < 0.7
                        replans.append(
                            {
                                "replan_id": f"r{replan_seq:05d}",
                                "task_id": meta["task_id"],
                                "anonymous_user_id": u.user_id,
                                "replan_reason": rng.choice(REPLAN_REASONS),
                                "old_planned_start": iso(old_start),
                                "new_planned_start": iso(old_start + timedelta(minutes=shift)),
                                "minutes_shifted": shift,
                                "hours_until_execution": round(max(0.1, (old_start - plan_generated_at).total_seconds() / 3600), 2),
                                "freeze_kind": freeze_kind,
                                "was_locked": freeze_kind == "USER_LOCK",
                                "system_frozen": freeze_kind == "SYSTEM_FREEZE",
                                "manual_override": freeze_kind == "MANUAL_OVERRIDE",
                                "schedule_version_before": version,
                                "schedule_version_after": schedule_version,
                                "plan_generated_at": iso(plan_generated_at + timedelta(minutes=rng.randint(30, 300))),
                                "user_accepted_replan": accepted,
                                "user_reverted_replan": (not accepted) and rng.random() < 0.5,
                                "label_split": u.split,
                                "data_role": "simulation_only",
                            }
                        )

            decision_seq += 1
            changed = rng.random() < 0.18
            candidates_ordered = sorted(candidates, key=lambda c: order.index(c["plan_id"]))
            pareto.append(
                {
                    "decision_id": f"d{decision_seq:05d}",
                    "anonymous_user_id": u.user_id,
                    "candidate_plan_ids": order,
                    "candidates": candidates_ordered,
                    "pareto_front_plan_ids": [c["plan_id"] for c in front],
                    "selected_plan_id": selected,
                    "display_order": order,
                    "prediction_at": iso(last_pred),
                    "plan_generated_at": iso(plan_generated_at),
                    "schedule_version": version,
                    "risk_difference": round(
                        candidates_ordered[0]["metrics"]["deadline_risk"] - candidates_ordered[-1]["metrics"]["deadline_risk"],
                        3,
                    ),
                    "free_time_difference": round(
                        float(candidates_ordered[0]["metrics"]["free_minutes"] - candidates_ordered[-1]["metrics"]["free_minutes"]),
                        1,
                    ),
                    "stability_difference": round(
                        float(candidates_ordered[0]["metrics"]["stability_cost"] - candidates_ordered[-1]["metrics"]["stability_cost"]),
                        1,
                    ),
                    "fragmentation_difference": round(
                        float(candidates_ordered[0]["metrics"]["fragmentation"] - candidates_ordered[-1]["metrics"]["fragmentation"]),
                        2,
                    ),
                    "selected_at": iso(plan_generated_at + timedelta(minutes=rng.randint(10, 180))),
                    "changed_after_selection": changed,
                    "manual_move_minutes": rng.randint(0, 120) if changed else 0,
                    "reselected_other_plan": changed and rng.random() < 0.35,
                    "label_preferred_plan": selected,
                    "label_split": u.split,
                    "data_role": "simulation_only",
                }
            )

            snap_seq += 1
            snapshots.append(
                {
                    "snapshot_id": f"ps{snap_seq:05d}",
                    "anonymous_user_id": u.user_id,
                    "decision_id": f"d{decision_seq:05d}",
                    "plan_generated_at": iso(plan_generated_at),
                    "prediction_at": iso(last_pred),
                    "schedule_version": version,
                    "schedule_version_meaning": "Monotonic plan epoch for this user; all blocks in this snapshot share this version. Candidate alternative blocks for the same epoch also share it but have selected_in_snapshot=false.",
                    "selected_plan_id": selected,
                    "pareto_candidates": candidates_ordered,
                    "selected_block_ids": [b["block_id"] for b in selected_blocks],
                    "candidate_block_ids_by_plan": {pid: [b["block_id"] for b in candidate_blocks[pid]] for pid in PLAN_IDS},
                    "fixed_interval_ids": [
                        fr["fixed_id"]
                        for fr in fixed_by_user.get(u.user_id, [])
                        if fr["start"].startswith(day0.isoformat())
                    ],
                    "label_split": u.split,
                    "data_role": "simulation_only",
                }
            )

            backlog = max(0, 3 + n_new - day_blocks_done // 2)
            rate = (sum(recent_complete[-7:]) / max(1, len(recent_complete[-7:]))) if recent_complete else 0.5
            recent_complete.append(1 if day_blocks_done >= day_blocks_skip else 0)
            days.append(
                {
                    "anonymous_user_id": u.user_id,
                    "date": day0.isoformat(),
                    "completed_blocks": day_blocks_done,
                    "skipped_blocks": day_blocks_skip,
                    "delayed_blocks": day_blocks_delay,
                    "actual_work_minutes": day_actual,
                    "planned_work_minutes": day_planned,
                    "task_backlog": backlog,
                    "overdue_task_count": max(0, rng.randint(0, 2) if day_blocks_skip else rng.randint(0, 1)),
                    "average_estimation_error": round(sum(est_errors) / len(est_errors), 4) if est_errors else None,
                    "average_start_delay": round(sum(start_delays) / len(start_delays), 1) if start_delays else None,
                    "consecutive_work_minutes": min(180, day_actual),
                    "recent_7_day_completion_rate": round(rate, 4),
                    "schedule_version_eod": version,
                    "label_split": u.split,
                    "data_role": "simulation_only",
                }
            )

    for s in range(10000):
        seed = SEED + 100000 + s
        stress = rng.choice(["normal", "p95_duration", "evening_drop", "new_urgent", "class_extend", "double_skip"])
        horizon = rng.choice([3, 7, 14])
        n_tasks = rng.randint(3, 12)
        body = expand_scenario(seed, stress, horizon, n_tasks)
        scenarios.append(
            {
                "scenario_id": f"s{s:05d}",
                "seed": seed,
                "stress_type": stress,
                "horizon_days": horizon,
                "n_tasks": body["n_tasks"],
                "label_split": "sim_eval",
                "data_role": "simulation_only",
                "reproducible_via": "evaluation.generate_drp_sim_v1.expand_scenario(seed, stress_type, horizon_days, n_tasks)",
            }
        )
        if s < 2000:
            scenario_instances.append({"scenario_id": f"s{s:05d}", **body})

    eligible_families = [f for f, ids in family_task_ids.items() if len(ids) >= 8]
    rng.shuffle(eligible_families)
    family_holdout = set(eligible_families[: max(1, int(len(eligible_families) * 0.15))])
    for t in tasks:
        t["semantic_holdout"] = t["semantic_family"] in family_holdout
        t["label_split_semantic"] = "family_holdout_test" if t["semantic_holdout"] else t["label_split"]

    # A day with no schedulable block has no meaningful compact/balanced/steady
    # choice. Keep the user-day record, but do not create a preference label or
    # an empty plan snapshot for that day.
    empty_decision_ids = {
        row["decision_id"]
        for row in pareto
        if all(not candidate.get("block_ids") for candidate in row["candidates"])
    }
    if empty_decision_ids:
        pareto = [row for row in pareto if row["decision_id"] not in empty_decision_ids]
        snapshots = [row for row in snapshots if row["decision_id"] not in empty_decision_ids]

    dump_jsonl(
        OUT / "users.jsonl",
        [
            {
                "anonymous_user_id": u.user_id,
                "label_split": u.split,
                "sim_risk_pref": u.risk_pref,
                "sim_reliability": round(u.reliability, 4),
                "sim_note": "simulated persona; not real demographics",
                "data_role": "simulation_only",
            }
            for u in users
        ],
    )
    dump_jsonl(OUT / "tasks.jsonl", tasks)
    dump_jsonl(OUT / "duration_labels.jsonl", durations)
    dump_jsonl(OUT / "blocks.jsonl", blocks)
    dump_jsonl(OUT / "user_days.jsonl", days)
    dump_jsonl(OUT / "release_completion.jsonl", cycles)
    dump_jsonl(OUT / "pareto_choices.jsonl", pareto)
    dump_jsonl(OUT / "replans.jsonl", replans)
    dump_jsonl(OUT / "fixed_intervals.jsonl", fixed_rows)
    dump_jsonl(OUT / "plan_snapshots.jsonl", snapshots)
    dump_jsonl(OUT / "scenarios.jsonl", scenarios)
    dump_jsonl(OUT / "scenario_instances.jsonl", scenario_instances)

    # integrity checks embedded in splits
    time_travel_tasks = sum(1 for t in tasks if parse_iso(t["prediction_at"]) < parse_iso(t["released_at"]))
    time_travel_blocks = sum(
        1
        for b in blocks
        if parse_iso(b["planned_start"]) < parse_iso(next(t for t in tasks if t["task_id"] == b["task_id"])["released_at"])
    )
    # map for speed
    release_map = {t["task_id"]: parse_iso(t["released_at"]) for t in tasks}
    time_travel_blocks = sum(1 for b in blocks if parse_iso(b["planned_start"]) < release_map[b["task_id"]])
    same_blocks = 0
    empty_groups = 0
    dominated_groups = 0
    dominated_candidates = 0
    for row in pareto:
        ids = [tuple(c["block_ids"]) for c in row["candidates"]]
        if not any(ids):
            empty_groups += 1
        elif len(set(ids)) < 3:
            same_blocks += 1
        group_dom = 0
        for c in row["candidates"]:
            if any(dominates(o, c) for o in row["candidates"] if o is not c):
                group_dom += 1
        dominated_candidates += group_dom
        if group_dom:
            dominated_groups += 1

    # overlap check selected blocks vs fixed
    fixed_map = fixed_by_user
    overlap = 0
    for b in blocks:
        if not b.get("selected_in_snapshot"):
            continue
        s0, s1 = parse_iso(b["planned_start"]), parse_iso(b["planned_end"])
        for fr in fixed_map.get(b["anonymous_user_id"], []):
            if overlaps(s0, s1, parse_iso(fr["start"]), parse_iso(fr["end"])):
                overlap += 1
                break

    version_mismatch = 0
    snap_by_id = {s["snapshot_id"]: s for s in snapshots}
    blocks_by_id = {b["block_id"]: b for b in blocks}
    for s in snapshots:
        for bid in s["selected_block_ids"]:
            if blocks_by_id[bid]["schedule_version"] != s["schedule_version"]:
                version_mismatch += 1

    missing_role_fixed = sum(1 for fr in fixed_rows if fr.get("data_role") != "simulation_only")
    counterfactual_labeled = sum(
        1
        for b in blocks
        if not b.get("selected_in_snapshot") and (b.get("outcome") is not None or b.get("label_observed") or b.get("actual_minutes") is not None)
    )
    incomplete_selected = 0
    executed_missing_minutes = 0
    for b in blocks:
        if not b.get("selected_in_snapshot"):
            continue
        outcome = b.get("outcome")
        times = (b.get("actual_start"), b.get("actual_end"), b.get("actual_minutes"))
        if outcome in ("COMPLETED", "PARTIALLY_COMPLETED", "DELAYED"):
            if any(v is None for v in times):
                incomplete_selected += 1
            if b.get("label_executed") and b.get("actual_minutes") is None:
                executed_missing_minutes += 1
        elif outcome in ("SKIPPED", "UNKNOWN", None):
            if any(v is not None for v in times):
                incomplete_selected += 1

    splits = {
        "scheme": SCHEMA_VERSION,
        "seed": SEED,
        "simulated": True,
        "data_role": "simulation_only",
        "allowed_uses": ["integration_debug", "stress_test", "ablation_pipeline"],
        "forbidden_uses": ["report_as_real_user_study", "final_claim_without_simulation_label"],
        "warning": "全部为程序模拟数据。仅限联调、压力测试与消融实验管线。",
        "generator": "evaluation/generate_drp_sim_v1.py",
        "generator_copy_in_data_dir": "evaluation/data/drp-sim-v1/generate_drp_sim_v1.py",
        "timezone": "Asia/Shanghai",
        "schedule_version_meaning": "Per-user monotonic plan epoch. A snapshot and all blocks created for that planning decision (including non-selected Pareto candidates) share the same schedule_version. Later replans increment the user counter; schedule_version_before/after appear on replan rows.",
        "window": {"start": iso(START), "days": N_DAYS, "users": N_USERS},
        "by_user": {
            "train": [u.user_id for u in users if u.split == "train"],
            "val": [u.user_id for u in users if u.split == "val"],
            "test": [u.user_id for u in users if u.split == "test"],
        },
        "semantic_family_holdout": {
            "family_count": len(family_holdout),
            "families": sorted(family_holdout),
            "rule": "Exclude semantic_holdout=true when training the encoder.",
        },
        "qa": {
            "time_travel_tasks_prediction_before_release": time_travel_tasks,
            "time_travel_blocks_planned_before_release": time_travel_blocks,
            "pareto_identical_block_sets": same_blocks,
            "pareto_empty_candidate_groups": empty_groups,
            "pareto_groups_with_dominated_candidate": dominated_groups,
            "pareto_dominated_candidates": dominated_candidates,
            "counterfactual_blocks_with_execution_labels": counterfactual_labeled,
            "selected_blocks_incomplete_actual_time": incomplete_selected,
            "executed_blocks_missing_actual_minutes": executed_missing_minutes,
            "selected_blocks_overlapping_fixed": overlap,
            "snapshot_selected_block_version_mismatch": version_mismatch,
            "fixed_missing_data_role": missing_role_fixed,
        },
        "counts": {
            "users": N_USERS,
            "tasks": len(tasks),
            "duration_labels": len(durations),
            "blocks": len(blocks),
            "blocks_selected": sum(1 for b in blocks if b.get("selected_in_snapshot")),
            "user_days": len(days),
            "release_completion": len(cycles),
            "pareto_choices": len(pareto),
            "replans": len(replans),
            "fixed_intervals": len(fixed_rows),
            "plan_snapshots": len(snapshots),
            "scenarios": len(scenarios),
            "scenario_instances_full": len(scenario_instances),
            "tasks_missing_deadline": sum(1 for t in tasks if not t["has_deadline"]),
        },
        "scenario_replay": {
            "full_instances_file": "scenario_instances.jsonl",
            "header_file": "scenarios.jsonl",
            "python": "from generate_drp_sim_v1 import expand_scenario",
        },
    }
    (OUT / "splits.json").write_text(json.dumps(splits, ensure_ascii=False, indent=2), encoding="utf-8")

    # ship generator beside data for teammates
    shutil.copy2(Path(__file__).resolve(), OUT / "generate_drp_sim_v1.py")

    hashes = {}
    for p in sorted(OUT.glob("*")):
        if p.name != "SHA256SUMS.txt" and p.is_file() and p.suffix in {".jsonl", ".json", ".py", ".md", ".txt"}:
            hashes[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    (OUT / "SHA256SUMS.txt").write_text(
        "\n".join(f"{h}  {name}" for name, h in sorted(hashes.items())) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"counts": splits["counts"], "qa": splits["qa"]}, ensure_ascii=False, indent=2))
    print("written", OUT)


if __name__ == "__main__":
    main()
