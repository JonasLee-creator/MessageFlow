# -*- coding: utf-8 -*-
"""Generate synthetic ChronoFlow notification annotations.

These rows are template-generated. They are not consented student data and
must not be reported as a real pilot or as double-annotated gold.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parent
WEEK = "一二三四五六日"

DEV_COUNTS = {
    "new_task": 90,
    "update_or_cancel": 70,
    "event": 60,
    "multi": 50,
    "ambiguous": 50,
    "irrelevant": 50,
    "hard": 30,
}
TEST_COUNTS = {
    "new_task": 25,
    "update_or_cancel": 15,
    "event": 15,
    "multi": 15,
    "ambiguous": 15,
    "irrelevant": 15,
}


def iso(moment: datetime) -> str:
    return moment.astimezone(TZ).isoformat(timespec="seconds")


def at(day: datetime, hour: int, minute: int) -> datetime:
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def weekday_on(ref: datetime, label: str, prefix: str) -> datetime:
    day = WEEK.index(label) + 1
    delta = day - (ref.weekday() + 1)
    if prefix.startswith("下"):
        delta += 7
    elif delta < 0 and prefix not in ("本周", "这周"):
        delta += 7
    return at(ref + timedelta(days=delta), ref.hour, ref.minute)


def unique_label(pool: list[str], i: int) -> str:
    base = pool[i % len(pool)]
    if i < len(pool):
        return base
    return f"{base}{i // len(pool) + 1}"


def quota_sources(n: int) -> list[str]:
    target = {
        "wechat": round(n * 0.45),
        "qq": round(n * 0.30),
        "canvas": round(n * 0.15),
    }
    target["manual"] = n - sum(target.values())
    pool = []
    for name, count in target.items():
        pool.extend([name] * count)
    if len(pool) != n:
        raise SystemExit(f"source quota mismatch: {target}")
    return [pool[(i * 7) % n] for i in range(n)]


def item(action, title, evidence, target_id=None, deadline=None, start=None, end=None,
         minutes=None, ambiguous=None, question=False):
    return {
        "action": action,
        "title": title,
        "target_id": target_id,
        "deadline": iso(deadline) if deadline else None,
        "start": iso(start) if start else None,
        "end": iso(end) if end else None,
        "minutes": minutes,
        "evidence": evidence,
        "ambiguous_fields": ambiguous or [],
        "requires_question": question,
    }


def record(idx, split, scene, source, ref, text, course, group, gold_items, ignore=False, tasks=None):
    prefix = "dev" if split == "development" else "test"
    for snippet in [e for row in gold_items for e in row["evidence"]]:
        if snippet not in text:
            raise AssertionError(f"evidence not in text: {snippet} :: {text}")
    return {
        "id": f"{prefix}-{idx:04d}",
        "split": split,
        "scene": scene,
        "source": source,
        "reference_time": iso(ref),
        "timezone": "Asia/Shanghai",
        "text": text,
        "context": {
            "group": group,
            "course": course,
            "candidate_tasks": tasks or [],
        },
        "gold": {"items": gold_items, "should_ignore": ignore},
        "provenance": "synthetic",
        "annotators": ["template-generator"],
        "adjudicated": False,
    }


def new_task(i, ref, course, title, source, group):
    kind = i % 6
    hours = (i % 4) + 1
    if kind == 0:
        deadline = at(ref + timedelta(days=1), 18, 0)
        text = f"{course}：{title}明天18:00前提交，预计{hours}小时"
        evidence = [title, "明天18:00前提交", f"预计{hours}小时"]
    elif kind == 1:
        deadline = at(ref + timedelta(days=2), 23, 59)
        text = f"请完成{title}，后天之前提交，预计耗时{hours * 60}分钟"
        evidence = [title, "后天之前提交", f"{hours * 60}分钟"]
        hours_minutes = hours * 60
        return record(0, "", "new_task", source, ref, text, course, group, [
            item("CREATE_TASK", title, evidence, deadline=deadline, minutes=hours_minutes)
        ])
    elif kind == 2:
        when = weekday_on(ref, "五", "周")
        deadline = at(when, 23, 59)
        text = f"{title}周五之前提交，大约需要{hours}小时"
        evidence = [title, "周五之前提交", f"{hours}小时"]
    elif kind == 3:
        deadline = at(ref + timedelta(days=3), 12, 0)
        text = f"【{course}】{title}截止到{deadline.month}月{deadline.day}日12:00，预计{hours}小时"
        evidence = [title, f"{deadline.month}月{deadline.day}日12:00", f"预计{hours}小时"]
    elif kind == 4:
        deadline = at(ref + timedelta(days=1), 23, 59)
        text = f"{title}明天交，预计{hours}小时"
        evidence = [title, "明天交", f"预计{hours}小时"]
    else:
        when = weekday_on(ref, "一", "下周")
        deadline = at(when, 18, 0)
        text = f"下周一18:00前完成{title}，需要{hours}小时"
        evidence = [title, "下周一18:00前", f"{hours}小时"]
    return record(0, "", "new_task", source, ref, text, course, group, [
        item("CREATE_TASK", title, evidence, deadline=deadline, minutes=hours * 60)
    ])


def update_or_cancel(i, ref, course, title, source, group):
    task_id = f"task-{group}-{i:03d}"
    tasks = [{"id": task_id, "title": title, "course": course}]
    if i % 5 == 0:
        text = f"{title}取消，不用交了"
        gold = [item("CANCEL_TASK", title, [title, "取消", "不用交了"], target_id=task_id)]
    elif i % 5 == 1:
        when = weekday_on(ref, "一", "下周")
        deadline = at(when, 18, 0)
        text = f"{title}不用周五交了，改到下周一18:00提交"
        gold = [item("UPDATE_TASK", title, [title, "改到下周一18:00提交"], target_id=task_id, deadline=deadline)]
    elif i % 5 == 2:
        deadline = at(ref + timedelta(days=4), 20, 0)
        text = f"{title}延期到{deadline.month}月{deadline.day}日20:00"
        gold = [item("UPDATE_TASK", title, [title, f"{deadline.month}月{deadline.day}日20:00"], target_id=task_id, deadline=deadline)]
    elif i % 5 == 3:
        text = f"通知：{title}无需提交"
        gold = [item("CANCEL_TASK", title, [title, "无需提交"], target_id=task_id)]
    else:
        when = weekday_on(ref, "三", "下周")
        deadline = at(when, 17, 0)
        text = f"{course}：{title}提前到下周三17:00提交"
        gold = [item("UPDATE_TASK", title, [title, "下周三17:00"], target_id=task_id, deadline=deadline)]
    return record(0, "", "update_or_cancel", source, ref, text, course, group, gold, tasks=tasks)


def event(i, ref, course, title, source, group):
    task_id = f"event-{group}-{i:03d}"
    if i % 6 == 0:
        start = at(ref + timedelta(days=1), 15, 0)
        end = at(ref + timedelta(days=1), 16, 0)
        text = f"明天下午三点到四点{title}"
        gold = [item("CREATE_EVENT", title, ["明天下午三点到四点", title], start=start, end=end)]
        tasks = []
    elif i % 6 == 1:
        start = at(weekday_on(ref, "四", "周"), 19, 0)
        end = at(weekday_on(ref, "四", "周"), 20, 30)
        text = f"周四晚上七点到八点半{title}"
        gold = [item("CREATE_EVENT", title, ["周四晚上七点到八点半", title], start=start, end=end)]
        tasks = []
    elif i % 6 == 2:
        start = at(ref + timedelta(days=2), 10, 0)
        end = at(ref + timedelta(days=2), 11, 30)
        text = f"后天上午十点到十一点半{title}"
        gold = [item("CREATE_EVENT", title, ["后天上午十点到十一点半", title], start=start, end=end)]
        tasks = []
    elif i % 6 == 3:
        start = at(ref + timedelta(days=1), 14, 0)
        end = at(ref + timedelta(days=1), 15, 30)
        text = f"{title}改到明天下午两点到三点半"
        gold = [item("UPDATE_EVENT", title, [title, "明天下午两点到三点半"], target_id=task_id, start=start, end=end)]
        tasks = [{"id": task_id, "title": title, "course": course}]
    elif i % 6 == 4:
        text = f"明天{title}取消"
        gold = [item("CANCEL_EVENT", title, ["明天", title, "取消"], target_id=task_id)]
        tasks = [{"id": task_id, "title": title, "course": course}]
    else:
        start = at(weekday_on(ref, "二", "下周"), 9, 0)
        end = at(weekday_on(ref, "二", "下周"), 10, 0)
        text = f"下周二上午九点到十点{title}"
        gold = [item("CREATE_EVENT", title, ["下周二上午九点到十点", title], start=start, end=end)]
        tasks = []
    return record(0, "", "event", source, ref, text, course, group, gold, tasks=tasks)


def multi(i, ref, course, title_a, title_b, source, group):
    d1 = at(ref + timedelta(days=1), 18, 0)
    d2 = at(ref + timedelta(days=3), 23, 59)
    start = at(ref + timedelta(days=2), 15, 0)
    end = at(ref + timedelta(days=2), 16, 0)
    if i % 2 == 0:
        text = f"{title_a}明天18:00前提交，预计2小时；另外{title_b}三天内提交，预计1小时"
        gold = [
            item("CREATE_TASK", title_a, [title_a, "明天18:00前提交", "预计2小时"], deadline=d1, minutes=120),
            item("CREATE_TASK", title_b, [title_b, "三天内提交", "预计1小时"], deadline=d2, minutes=60),
        ]
    else:
        text = f"{title_a}明天18:00前提交，预计2小时。后天下午三点到四点{title_b}"
        gold = [
            item("CREATE_TASK", title_a, [title_a, "明天18:00前提交", "预计2小时"], deadline=d1, minutes=120),
            item("CREATE_EVENT", title_b, [title_b, "后天下午三点到四点"], start=start, end=end),
        ]
    return record(0, "", "multi", source, ref, text, course, group, gold)


def ambiguous(i, ref, course, title, source, group):
    kind = i % 5
    if kind == 0:
        text = f"明天三点{title}"
        gold = [item("CREATE_EVENT", title, ["明天三点", title], ambiguous=["period", "end"], question=True)]
    elif kind == 1:
        text = f"{title}周五之前提交"
        deadline = at(weekday_on(ref, "五", "周"), 23, 59)
        gold = [item("CREATE_TASK", title, [title, "周五之前提交"], deadline=deadline, ambiguous=["deadline_time", "minutes"], question=True)]
    elif kind == 2:
        text = f"可能要开{title}，时间再说"
        gold = [item("CREATE_EVENT", title, [title, "时间再说"], ambiguous=["date", "start", "end"], question=True)]
    elif kind == 3:
        text = f"{title}尽快完成"
        gold = [item("CREATE_TASK", title, [title, "尽快完成"], ambiguous=["deadline", "minutes"], question=True)]
    else:
        text = f"下周{title}，下午或者晚上"
        gold = [item("CREATE_EVENT", title, [title, "下午或者晚上"], ambiguous=["date", "period"], question=True)]
    return record(0, "", "ambiguous", source, ref, text, course, group, gold)


def irrelevant(i, ref, course, source, group):
    lines = [
        "晚上有人吃饭吗",
        "收到，谢谢老师",
        "这个表情包好好笑",
        "链接点开是广告，别点",
        "谁带了充电器",
        "群里别发无关链接",
        "今天下雨记得带伞",
        "投票截止前记得选一下班长",
    ]
    text = f"{lines[i % len(lines)]} {group}-{i}"
    return record(0, "", "irrelevant", source, ref, text, course, group, [
        item("IGNORE", "无关消息", [lines[i % len(lines)]], ambiguous=[], question=False)
    ], ignore=True)


def hard(i, ref, course, title, source, group):
    kind = i % 3
    if kind == 0:
        deadline = at(ref + timedelta(days=1), 18, 0)
        shown = title.replace("实验", "实验").replace("三", "叁") if "三" in title else title + " "
        # Keep a visible fragment that is also the title stem.
        text = f"{title}明天18：00前提交，预计2小…"
        gold = [item("CREATE_TASK", title, [title, "明天18：00前提交"], deadline=deadline, ambiguous=["minutes"], question=True)]
    elif kind == 1:
        deadline = at(ref + timedelta(days=1), 18, 0)
        text = f"  {title}   明天18:00前提交！！预计2小时  "
        gold = [item("CREATE_TASK", title, [title, "明天18:00前提交", "预计2小时"], deadline=deadline, minutes=120)]
    else:
        deadline = at(weekday_on(ref, "一", "下周"), 18, 0)
        text = f"{course}/{title}/改到/下周一18:00/提交"
        gold = [item("UPDATE_TASK", title, [title, "下周一18:00"], target_id=f"task-{group}-hard-{i:03d}", deadline=deadline)]
        return record(0, "", "hard", source, ref, text, course, group, gold, tasks=[
            {"id": f"task-{group}-hard-{i:03d}", "title": title, "course": course}
        ])
    return record(0, "", "hard", source, ref, text, course, group, gold)


DEV_TITLES = [
    "实验一", "实验二", "实验三", "实验四", "读书报告", "链表作业", "排序练习", "期中复习",
    "单词默写", "文献阅读", "接口实验", "数据库报告", "进程作业", "树结构练习", "语法复习",
    "口语展示提纲", "编译实验", "网络报告", "缓存作业", "递归练习",
]
TEST_TITLES = [
    "课程设计", "文献综述", "上机练习", "期末复习", "口试准备", "动态规划作业", "协议实验",
    "系统报告", "图论练习", "展示周材料", "汇编实验", "密码学报告", "并发作业", "搜索练习",
    "听力复习", "开题阅读", "驱动实验", "存储报告", "脚本作业", "证明练习",
]
DEV_EVENTS = ["班会", "实验讲解", "答疑", "小组讨论", "讲座", "验收会"]
TEST_EVENTS = ["开题会", "展示会", "补课", "口试", "研讨", "检查会"]


def build(split: str, counts: dict, titles: list[str], events: list[str], salt: int, start: datetime):
    rows = []
    source_plan = []
    for scene, count in counts.items():
        source_plan.extend((scene, "wechat") for _ in range(count))
    planned_sources = quota_sources(len(source_plan))
    source_plan = [(scene, planned_sources[i]) for i, (scene, _) in enumerate(source_plan)]
    scene_i = {name: 0 for name in counts}
    for scene, source in source_plan:
        i = scene_i[scene]
        scene_i[scene] += 1
        ref = at(start + timedelta(days=i * 2 + salt % 5), 9, 0)
        course = f"<COURSE_{'DEV' if split == 'development' else 'TEST'}_{(i % 12) + 1:02d}>"
        group = f"<GROUP_{'DEV' if split == 'development' else 'TEST'}_{(i % 8) + 1:02d}>"
        title = unique_label(titles, i)
        if scene == "new_task":
            row = new_task(i, ref, course, title, source, group)
        elif scene == "update_or_cancel":
            row = update_or_cancel(i, ref, course, title, source, group)
        elif scene == "event":
            row = event(i, ref, course, unique_label(events, i), source, group)
        elif scene == "multi":
            other = unique_label(titles, i + 3)
            if other == title:
                other = unique_label(titles, i + 5)
            row = multi(i, ref, course, title, other, source, group)
        elif scene == "ambiguous":
            label = unique_label(events, i) if i % 2 == 0 else title
            row = ambiguous(i, ref, course, label, source, group)
        elif scene == "irrelevant":
            row = irrelevant(i, ref, course, source, group)
        else:
            row = hard(i, ref, course, title, source, group)
        rows.append(row)
    return rows


def stamp(rows, split):
    prefix = "dev" if split == "development" else "test"
    for n, row in enumerate(rows, start=1):
        row["id"] = f"{prefix}-{n:04d}"
        row["split"] = split
    return rows


def public_view(row):
    return {key: row[key] for key in ("id", "split", "source", "reference_time", "timezone", "text", "context")}


def main():
    dev_start = datetime(2026, 9, 7, 9, 0, tzinfo=TZ)
    test_start = datetime(2026, 11, 2, 9, 0, tzinfo=TZ)
    dev = stamp(build("development", DEV_COUNTS, DEV_TITLES, DEV_EVENTS, 3, dev_start), "development")
    test = stamp(build("sealed-test", TEST_COUNTS, TEST_TITLES, TEST_EVENTS, 11, test_start), "sealed-test")
    dev_text = {row["text"] for row in dev}
    test_text = {row["text"] for row in test}
    overlap = dev_text & test_text
    if overlap:
        raise SystemExit(f"text overlap: {len(overlap)}")
    if len(dev_text) != len(dev) or len(test_text) != len(test):
        raise SystemExit("duplicate text inside a split")

    data = ROOT / "data"
    (data / "development").mkdir(parents=True, exist_ok=True)
    (data / "sealed-test").mkdir(parents=True, exist_ok=True)
    (data / "raw-private").mkdir(parents=True, exist_ok=True)
    for name in ("experiments/rule-only", "experiments/deepseek-only", "experiments/full-system",
                 "pilot/consent", "pilot/daily-records", "pilot/questionnaires", "figures", "reports"):
        (ROOT / name).mkdir(parents=True, exist_ok=True)

    dev_path = data / "development" / "development-v1.jsonl"
    test_in = data / "sealed-test" / "sealed-test-input.jsonl"
    test_gold = data / "sealed-test" / "sealed-test-gold.jsonl"
    write_jsonl(dev_path, dev)
    write_jsonl(test_in, [public_view(row) for row in test])
    write_jsonl(test_gold, test)

    hashes = {path.name: sha(path) for path in (dev_path, test_in, test_gold)}
    (ROOT / "reports" / "dataset-hashes.txt").write_text(
        "\n".join(f"{digest}  {name}" for name, digest in hashes.items()) + "\n",
        encoding="utf-8",
    )
    summary = {
        "provenance": "synthetic",
        "development": len(dev),
        "sealed_test": len(test),
        "development_scenes": count_by(dev, "scene"),
        "test_scenes": count_by(test, "scene"),
        "development_sources": count_by(dev, "source"),
        "test_sources": count_by(test, "source"),
        "hashes": hashes,
    }
    (ROOT / "reports" / "dataset-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def write_jsonl(path: Path, rows: list[dict]):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_by(rows, key):
    out = {}
    for row in rows:
        out[row[key]] = out.get(row[key], 0) + 1
    return out


if __name__ == "__main__":
    main()
