"""Convert the real-study workbook using only the Python standard library.

No training, no inferred durations for censored tasks, and no learned simulator
probabilities from the held-out study. See real_data/README.md.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

SHEETS = {
    '参与者': [
        ('scenario_id', '观察编号', '同一用户一段连续观察期一个编号，如 R001'),
        ('user_id', '匿名用户编号', '仅填匿名编号，如 U001；不要填姓名、学号'),
        ('consent', '已获同意', '是/否；仅在取得参与者同意后填是'),
        ('start', '观察开始时间', '北京时间 YYYY-MM-DD HH:MM；30分钟对齐；开始前已有任务不纳入本轮'),
        ('end', '观察结束时间', '统一预先约定的截止观察时刻；30分钟对齐'),
    ],
    '任务': [
        ('scenario_id', '观察编号', '对应参与者表'),
        ('task_id', '任务编号', '观察内唯一，如 T001'),
        ('title', '脱敏任务标题', '保留任务语义，不填聊天原文、姓名或账号'),
        ('category', '任务类别', '实验/报告/编程/复习/背诵/阅读/考试准备/其他'),
        ('course', '匿名课程编号', '如 C001，不填教师姓名'),
        ('difficulty', '难度1至5', '发布时填写，1最容易，5最难'),
        ('priority', '优先级1至5', '发布时填写，5最高'),
        ('released', '任务发布时间', '实际发布时刻；用于发布到完成的延迟分析'),
        ('known', '首次获知时间', '本人首次看到并可录入计划的时间，不早于发布时间'),
        ('earliest', '最早可开始时间', '可空，默认首次获知；绝不是实际开始时间'),
        ('deadline', '截止时间', '可空；只填当时已知的期限，不能事后修改'),
        ('estimate', '初始预计分钟', '在执行前记录，正数；不填实际耗时'),
        ('splittable', '允许拆分', '是/否；能否分多次完成'),
        ('status', '观察结束状态', '已完成/进行中/未开始/已取消；未完成也必须保留'),
        ('completed', '实际完成时间', '已完成必填；否则留空；不是截止时间'),
        ('actual', '实际有效工作分钟', '已完成必填正数；可由完整执行记录求和；不含休息、等待'),
    ],
    '固定安排': [
        ('scenario_id', '观察编号', '对应参与者表；没有固定安排可整表留空'),
        ('interval_id', '安排编号', '观察内唯一，如 F001'),
        ('kind', '安排类型', '课程/睡眠/兼职/其他；一节课一行，重复课逐次填写'),
        ('known', '获知安排时间', '必须不晚于观察开始；动态新增安排当前回放不支持'),
        ('start', '开始时间', '具体日期时间，不写每周一；不能做任务的时段'),
        ('end', '结束时间', '晚于开始，且在观察期内'),
    ],
    '执行记录': [
        ('scenario_id', '观察编号', '可选，但推荐；对应参与者表'),
        ('session_id', '记录编号', '观察内唯一，如 S001'),
        ('task_id', '任务编号', '对应任务表'),
        ('planned_start', '原计划开始时间', '可空；记录当时的计划，不能事后补成实际时间'),
        ('planned_end', '原计划结束时间', '有计划开始则必填'),
        ('actual_start', '实际开始时间', '完成/部分执行必填；跳过留空'),
        ('actual_end', '实际结束时间', '本次工作结束或暂停时刻，不等于任务完成'),
        ('active', '本次有效分钟', '完成/部分执行必填；剔除休息，不能超过实际起止间隔'),
        ('feedback', '执行反馈', '完成/部分执行/跳过/未知；一次暂停后再开始另起一行'),
    ],
}
CATEGORIES = dict(zip(
    ('实验', '报告', '编程', '复习', '背诵', '阅读', '考试准备', '其他'),
    ('EXPERIMENT', 'REPORT', 'PROGRAMMING', 'REVIEW', 'MEMORIZATION', 'READING', 'EXAM_PREPARATION', 'OTHER')))
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def read_workbook(path):
    """Read values from XLSX; refuse formulas to avoid stale cached labels."""
    with zipfile.ZipFile(path) as z:
        book = ET.fromstring(z.read('xl/workbook.xml'))
        props = book.find('m:workbookPr', NS)
        if props is not None and props.get('date1904') in ('1', 'true'):
            raise ValueError('不支持1904日期系统，请另存为使用1900日期系统的xlsx')
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            strings = [''.join(e.itertext()) for e in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        result = {}
        for sheet in book.find('m:sheets', NS):
            name = sheet.get('name')
            if name not in SHEETS:
                continue
            rid = sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
            target = rels[rid]
            target = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
            rows = []
            for row in ET.fromstring(z.read(target)).findall('.//m:sheetData/m:row', NS):
                cells = {}
                for cell in row:
                    if cell.find('m:f', NS) is not None:
                        raise ValueError(f'{name}!{cell.get("r")}: 请填原始值，不要填公式')
                    letters = re.match(r'[A-Z]+', cell.get('r')).group()
                    col = 0
                    for letter in letters:
                        col = col * 26 + ord(letter) - 64
                    val = cell.findtext('m:v', default='', namespaces=NS)
                    typ = cell.get('t')
                    if typ == 's':
                        val = strings[int(val)]
                    elif typ == 'inlineStr':
                        val = ''.join(cell.find('m:is', NS).itertext())
                    elif typ == 'e':
                        raise ValueError(f'{name}!{cell.get("r")}: Excel错误值')
                    cells[col - 1] = val
                rows.append((int(row.get('r')), cells))
            if not rows:
                raise ValueError(f'{name}: 缺少表头')
            headers = [c[1] for c in SHEETS[name]]
            if [rows[0][1].get(i, '') for i in range(len(headers))] != headers:
                raise ValueError(f'{name}: 第1行表头被修改，请使用模板原始表头')
            result[name] = []
            for number, cells in rows[1:]:
                if not any(str(v).strip() for v in cells.values()):
                    continue
                record = {key: cells.get(i, '') for i, (key, _, _) in enumerate(SHEETS[name])}
                record['_row'] = number
                result[name].append(record)
        if set(SHEETS) != set(result):
            raise ValueError('缺少工作表: ' + ', '.join(set(SHEETS) - set(result)))
        return result


def dt(value):
    if value in ('', None):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        try:
            parsed = datetime(1899, 12, 30) + timedelta(days=float(text))
            # XLSX serials have binary/decimal roundoff (e.g. 08:00 becomes
            # 08:00:00.000001). Normalize only sub-10ms storage noise, never
            # silently round a genuinely recorded second to a minute.
            rounded = (parsed + timedelta(seconds=30)).replace(second=0, microsecond=0)
            if abs((parsed-rounded).total_seconds()) < .01:
                parsed = rounded
        except (ValueError, OverflowError):
            parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is not None:
        raise ValueError('时间统一填写无时区的北京时间，不混用UTC或带偏移格式')
    if parsed.second or parsed.microsecond:
        raise ValueError('时间精确到分钟，不包含秒')
    return parsed


def num(value, low=0, high=math.inf, integer=False):
    val = float(value)
    if not math.isfinite(val) or not low <= val <= high or (integer and val != int(val)):
        raise ValueError(f'数字必须在{low}至{high}之间' + ('且为整数' if integer else ''))
    return int(val) if integer else val


def yes(value):
    if str(value).strip() not in ('是', '否'):
        raise ValueError('请填写是或否')
    return str(value).strip() == '是'


def convert(tables, probability=None, allow_subset=False, observations_only=False):
    if probability is not None:
        probability = num(probability, 0, 1)
    if probability is None and not observations_only:
        raise ValueError('回放须显式指定 --execution-probability（如1），或用 --observations-only 仅导出观测数据')
    users, tasks, fixed, sessions = {}, defaultdict(list), defaultdict(list), defaultdict(list)
    errors, warnings, observed, scenarios, excluded = [], [], [], [], []

    def located(sheet, row, action):
        try:
            action()
        except (ValueError, TypeError, KeyError) as exc:
            errors.append(f'{sheet}第{row["_row"]}行: {exc}')

    for row in tables['参与者']:
        def add_user():
            sid, uid = str(row['scenario_id']).strip(), str(row['user_id']).strip()
            if not sid or not uid or sid in users:
                raise ValueError('观察编号/用户编号为空，或观察编号重复')
            if not yes(row['consent']):
                raise ValueError('未获得参与者同意，不可导出')
            start, end = dt(row['start']), dt(row['end'])
            if start is None or end is None or end <= start:
                raise ValueError('观察起止时间缺失或顺序错误')
            if start.minute % 30 or end.minute % 30:
                raise ValueError('观察起止时间须30分钟对齐')
            if any(u['user_id'] == uid and start < u['end'] and u['start'] < end for u in users.values()):
                raise ValueError('同一用户观察期重叠，可能重复计数')
            users[sid] = dict(user_id=uid, start=start, end=end)
        located('参与者', row, add_user)

    seen = set()
    for row in tables['任务']:
        def add_task():
            sid, tid = str(row['scenario_id']).strip(), str(row['task_id']).strip()
            if sid not in users or not tid or (sid, tid) in seen:
                raise ValueError('未知观察编号、任务编号为空或重复')
            u = users[sid]
            release, known = dt(row['released']), dt(row['known'])
            earliest = dt(row['earliest']) or known
            deadline, completion = dt(row['deadline']), dt(row['completed'])
            if release is None or known is None or not u['start'] <= release <= known < u['end']:
                raise ValueError('须满足观察开始≤发布时间≤首次获知时间<观察结束；开始前积压任务暂不支持')
            if earliest < known:
                raise ValueError('最早可开始时间不得早于首次获知时间')
            if deadline is not None and deadline < release:
                raise ValueError('截止时间早于发布时间')
            status = str(row['status']).strip()
            if status not in ('已完成', '进行中', '未开始', '已取消'):
                raise ValueError('观察结束状态不合法')
            if (status == '已完成') != (completion is not None):
                raise ValueError('仅已完成任务填写实际完成时间，且必须填写')
            if completion is not None and not earliest <= completion <= u['end']:
                raise ValueError('完成时间不在可执行观察范围内')
            category = str(row['category']).strip()
            if category not in CATEGORIES or not str(row['title']).strip() or not str(row['course']).strip():
                raise ValueError('类别无效，或标题/匿名课程编号为空')
            actual = num(row['actual'], 0) if row['actual'] != '' else None
            if status == '未开始' and actual not in (None, 0):
                raise ValueError('未开始任务不能有实际有效工作耗时')
            if actual is not None and completion is not None and actual > (completion - earliest).total_seconds()/60:
                raise ValueError('有效工作耗时超过可用自然时间')
            item = dict(local_task_id=tid, sanitized_title=str(row['title']).strip(),
                task_category=CATEGORIES[category], anonymous_course_id=str(row['course']).strip(),
                difficulty=num(row['difficulty'], 1, 5, True), priority=num(row['priority'], 1, 5, True),
                released_at=release.isoformat(), prediction_at=known.isoformat(),
                earliest_start_at=earliest.isoformat(), deadline_at=deadline.isoformat() if deadline else None,
                initial_estimated_minutes=num(row['estimate'], .001), splittable=yes(row['splittable']),
                status=status, completed_at=completion.isoformat() if completion else None,
                actual_work_minutes=actual)
            tasks[sid].append(item)
            seen.add((sid, tid))
        located('任务', row, add_task)

    interval_ids, session_ids = set(), set()
    for row in tables['固定安排']:
        def add_fixed():
            sid, iid = str(row['scenario_id']).strip(), str(row['interval_id']).strip()
            u = users[sid]
            if not iid or (sid, iid) in interval_ids:
                raise ValueError('安排编号为空或重复')
            start, end, known = dt(row['start']), dt(row['end']), dt(row['known'])
            if None in (start, end, known) or not u['start'] <= start < end <= u['end'] or known > u['start']:
                raise ValueError('固定安排须在观察期内且观察开始前已知；动态新增不支持')
            fixed[sid].append(dict(start=start.isoformat(), end=end.isoformat(), kind=row['kind']))
            interval_ids.add((sid, iid))
        located('固定安排', row, add_fixed)

    for row in tables['执行记录']:
        def add_session():
            sid, tid, iid = str(row['scenario_id']).strip(), str(row['task_id']).strip(), str(row['session_id']).strip()
            if (sid, tid) not in seen or not iid or (sid, iid) in session_ids:
                raise ValueError('任务引用无效、记录编号为空或重复')
            u = users[sid]
            task = next(t for t in tasks[sid] if t['local_task_id'] == tid)
            ps, pe, start, end = [dt(row[k]) for k in ('planned_start', 'planned_end', 'actual_start', 'actual_end')]
            if (ps is None) != (pe is None) or (ps is not None and not u['start'] <= ps < pe <= u['end']):
                raise ValueError('原计划起止必须成对填写且在观察期内')
            feedback = row['feedback']
            if feedback not in ('完成', '部分执行', '跳过', '未知'):
                raise ValueError('执行反馈无效')
            active = num(row['active'], 0) if row['active'] != '' else None
            if feedback in ('完成', '部分执行'):
                if start is None or end is None or not dt(task['earliest_start_at']) <= start < end <= u['end']:
                    raise ValueError('实际执行须有合法起止且不早于最早可开始时间')
                if active is None or not 0 < active <= (end-start).total_seconds()/60:
                    raise ValueError('本次有效分钟须为正数且不超过实际起止间隔')
                if task['completed_at'] and end > dt(task['completed_at']):
                    raise ValueError('执行记录晚于任务完成时间')
                for other in sessions[sid]:
                    if other['actual_start'] and start < dt(other['actual_end']) and dt(other['actual_start']) < end:
                        raise ValueError('同一用户实际执行记录重叠，请拆开记录')
            elif start is not None or end is not None or active not in (None, 0):
                raise ValueError('跳过/未知不填实际起止或有效分钟')
            if feedback == '跳过' and ps is None:
                raise ValueError('跳过须有原计划起止')
            sessions[sid].append(dict(task_id=tid, session_id=iid, planned_start=ps.isoformat() if ps else None,
                planned_end=pe.isoformat() if pe else None, actual_start=start.isoformat() if start else None,
                actual_end=end.isoformat() if end else None, active_minutes=active, feedback=feedback))
            session_ids.add((sid, iid))
        located('执行记录', row, add_session)

    for sid, u in users.items():
        if not tasks[sid]:
            errors.append(f'{sid}: 没有合法任务')
        exported = []
        for task in tasks[sid]:
            entries = [s for s in sessions[sid] if s['task_id'] == task['local_task_id']]
            total = sum(s['active_minutes'] or 0 for s in entries)
            actual = task['actual_work_minutes']
            if actual is not None and total > actual + .001:
                errors.append(f'{sid}/{task["local_task_id"]}: 执行记录累计大于填写的有效工作总耗时')
            observed.append(dict(scenario_id=sid, user_id=u['user_id'], observation_end=u['end'].isoformat(),
                **task, right_censored=task['status'] in ('未开始', '进行中'),
                release_to_completion_minutes=(dt(task['completed_at'])-dt(task['released_at'])).total_seconds()/60 if task['completed_at'] else None,
                observed_release_followup_minutes=(u['end']-dt(task['released_at'])).total_seconds()/60))
            if task['status'] != '已完成' or actual is None or actual <= 0:
                excluded.append(dict(scenario_id=sid, task_id=task['local_task_id'], reason='未完成/取消或缺少正的有效工作总耗时'))
                continue
            row = {k:v for k,v in task.items() if k not in ('status', 'completed_at', 'actual_work_minutes')}
            row.update(sampled_duration_minutes=actual,
                execution_prob_by_bucket={b:probability for b in ('morning', 'afternoon', 'evening', 'night')})
            exported.append(row)
        if exported:
            scenarios.append(dict(scenario_id=sid, anonymous_user_id=u['user_id'], stress_type='real_replay',
                observation_start=u['start'].isoformat(), horizon_minutes=int((u['end']-u['start']).total_seconds()/60),
                horizon_days=math.ceil((u['end']-u['start']).total_seconds()/86400),
                tasks=exported, fixed_intervals=fixed[sid], simulated=False,
                evaluation_type='real_task_measured_duration_assumed_execution_replay'))
    if errors:
        raise ValueError('\n'.join(errors))
    if not users:
        raise ValueError('模板尚未填写参与者和任务')
    if excluded and not allow_subset and not observations_only:
        raise ValueError('存在未完成/取消/缺少耗时任务。不可静默删除。先用 --observations-only 保留全部观测；'
            '仅在接受完成任务选择偏差时使用 --allow-completed-subset。受影响: '
            + ', '.join(f'{r["scenario_id"]}/{r["task_id"]}' for r in excluded))
    if allow_subset and excluded:
        warnings.append('仅已完成且耗时已知的任务子集参与反事实回放；存在选择偏差，不代表完整任务流表现')
    if not observations_only and not scenarios:
        raise ValueError('没有可回放的任务')
    warnings.extend(['执行概率是显式情景假设，不是从真实测试集估计的用户执行模型',
        '真实完成时刻仅用于观测延迟；各方法的完成时刻由回放重新计算',
        '多观察期若属于同一用户并不独立；现有bootstrap按场景聚类，不能当作用户级显著性证据',
        '回放使用配置中的统一工作时间和每日容量；固定安排在观察开始已知；无历史个性化热启动'])
    report = dict(kind='real_observations' if observations_only else 'real_data_driven_replay',
        users=len({u['user_id'] for u in users.values()}), observation_windows=len(users),
        observed_tasks=len(observed), replay_tasks=sum(len(s['tasks']) for s in scenarios) if not observations_only else 0,
        replay_scenarios=len(scenarios) if not observations_only else 0,
        completed_tasks=sum(t['status']=='已完成' for t in observed),
        right_censored_tasks=sum(t['right_censored'] for t in observed),
        cancelled_tasks=sum(t['status']=='已取消' for t in observed),
        execution_records=sum(len(rows) for rows in sessions.values()),
        replay_tasks_due_within_window=sum(
            t['deadline_at'] is not None and dt(t['deadline_at'])<=users[s['scenario_id']]['end']
            for s in scenarios for t in s['tasks']) if not observations_only else 0,
        execution_probability_assumption=probability, excluded_from_replay=excluded, warnings=warnings,
        timezone='Asia/Shanghai', required_evaluation_split='all')
    return observed, ([] if observations_only else scenarios), sessions, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='新目录；不覆盖已有数据')
    parser.add_argument('--execution-probability', type=float)
    parser.add_argument('--allow-completed-subset', action='store_true')
    parser.add_argument('--observations-only', action='store_true')
    args = parser.parse_args()
    try:
        tables = read_workbook(args.input)
        observed, scenarios, sessions, report = convert(tables, args.execution_probability,
            args.allow_completed_subset, args.observations_only)
        report['source_sha256'] = hashlib.sha256(args.input.read_bytes()).hexdigest()
        report['converter_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        args.output.mkdir(parents=True, exist_ok=False)
        def write_rows(name, rows):
            with (args.output/name).open('w', encoding='utf-8') as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
        write_rows('observed_tasks.jsonl', observed)
        write_rows('observed_sessions.jsonl', [dict(scenario_id=sid, **s) for sid, rows in sessions.items() for s in rows])
        if not args.observations_only:
            write_rows('scenario_instances.jsonl', scenarios)
        (args.output/'conversion_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        parser.exit(2, f'转换未完成: {exc}\n')


if __name__ == '__main__':
    main()
