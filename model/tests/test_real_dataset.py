from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('real_converter', ROOT/'scripts/convert_real_dataset.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def fixture():
    return {
        '参与者': [dict(_row=2, scenario_id='R1', user_id='U1', consent='是',
            start='2026-10-18 00:00', end='2026-10-20 00:00')],
        '任务': [dict(_row=2, scenario_id='R1', task_id='T1', title='课程实验报告', category='报告',
            course='C1', difficulty=3, priority=4, released='2026-10-18 09:00',
            known='2026-10-18 09:15', earliest='', deadline='2026-10-19 18:00', estimate=90,
            splittable='是', status='已完成', completed='2026-10-18 11:00', actual=60)],
        '固定安排': [dict(_row=2, scenario_id='R1', interval_id='F1', kind='课程',
            known='2026-10-17 12:00', start='2026-10-18 08:00', end='2026-10-18 09:00')],
        '执行记录': [dict(_row=2, scenario_id='R1', session_id='S1', task_id='T1',
            planned_start='2026-10-18 10:00', planned_end='2026-10-18 11:00',
            actual_start='2026-10-18 10:00', actual_end='2026-10-18 11:00', active=60, feedback='完成')],
    }


class RealDatasetTests(unittest.TestCase):
    def test_replay_loads_exact_observation_window_without_future_labels(self):
        import sys
        sys.path.insert(0, str(ROOT))
        from evaluation.domain import load_scenarios
        observed, scenarios, _, report = c.convert(fixture(), 1)
        self.assertEqual(observed[0]['release_to_completion_minutes'], 120)
        self.assertNotIn('completed_at', scenarios[0]['tasks'][0])
        self.assertEqual(report['users'], 1)
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder:
            path = Path(folder)/'scenario_instances.jsonl'
            path.write_text(json.dumps(scenarios[0]), encoding='utf-8')
            scene = list(load_scenarios(path, 'all'))[0]
        self.assertEqual(scene.origin.hour, 0)
        self.assertEqual(scene.horizon, 2880)
        self.assertEqual(scene.tasks[0].released, 540)
        self.assertEqual(scene.tasks[0].available, 555)
        self.assertEqual(scene.truth['T1']['duration'], 60)

    def test_missing_probability_is_not_invented(self):
        with self.assertRaisesRegex(ValueError, '显式指定'):
            c.convert(fixture())

    def test_censored_tasks_preserved_and_subset_requires_opt_in(self):
        data = fixture()
        row = deepcopy(data['任务'][0])
        row.update(_row=3, task_id='T2', status='进行中', completed='', actual=20)
        data['任务'].append(row)
        with self.assertRaisesRegex(ValueError, '不可静默删除'):
            c.convert(data, 1)
        observed, scenes, _, report = c.convert(data, 1, allow_subset=True)
        self.assertEqual(len(observed), 2)
        self.assertTrue(observed[1]['right_censored'])
        self.assertEqual(len(scenes[0]['tasks']), 1)
        self.assertEqual(len(report['excluded_from_replay']), 1)
        self.assertEqual(c.convert(data, observations_only=True)[1], [])

    def test_time_order_and_dynamic_fixed_events_rejected(self):
        data = fixture()
        data['任务'][0]['known'] = '2026-10-18 08:00'
        with self.assertRaisesRegex(ValueError, '首次获知'):
            c.convert(data, 1)
        data = fixture()
        data['固定安排'][0]['known'] = '2026-10-18 07:00'
        with self.assertRaisesRegex(ValueError, '动态新增'):
            c.convert(data, 1)

    def test_overlapping_sessions_and_impossible_duration_rejected(self):
        data = fixture()
        row = deepcopy(data['执行记录'][0])
        row.update(session_id='S2', _row=3)
        data['执行记录'].append(row)
        with self.assertRaisesRegex(ValueError, '重叠'):
            c.convert(data, 1)
        data = fixture()
        data['任务'][0]['actual'] = 300
        with self.assertRaisesRegex(ValueError, '自然时间'):
            c.convert(data, 1)

    def test_consent_and_duplicate_ids_rejected(self):
        data = fixture()
        data['参与者'][0]['consent'] = '否'
        with self.assertRaisesRegex(ValueError, '同意'):
            c.convert(data, 1)
        data = fixture()
        data['任务'].append(deepcopy(data['任务'][0]))
        with self.assertRaisesRegex(ValueError, '重复'):
            c.convert(data, 1)

    def test_excel_serial_matches_text_date(self):
        date = c.dt('2026-10-18 09:00')
        serial = (date-c.datetime(1899, 12, 30)).total_seconds()/86400
        self.assertEqual(c.dt(serial), date)
        self.assertEqual(c.dt('46301.333333333343'), c.datetime(2026, 10, 6, 8, 0))
        with self.assertRaisesRegex(ValueError, '秒'):
            c.dt('2026-10-18 09:00:01')

    def test_30_minute_fixture_replay_all_methods(self):
        import sys
        sys.path.insert(0, str(ROOT))
        from evaluation.domain import load_scenarios
        from evaluation.planners import METHODS
        from evaluation.predictor import Predictor
        from evaluation.replay import replay
        data = fixture()
        data['参与者'][0].update(start='2026-10-18 09:00', end='2026-10-18 12:00')
        data['固定安排'] = []
        data['任务'][0].update(known='2026-10-18 09:00', deadline='2026-10-18 12:00')
        _, scenes, _, _ = c.convert(data, 1)
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder:
            path = Path(folder)/'scenario_instances.jsonl'
            path.write_text(json.dumps(scenes[0]), encoding='utf-8')
            scene = next(load_scenarios(path, 'all'))
        config = json.loads((ROOT/'evaluation/config_integrated.json').read_text())
        for method in METHODS:
            row, _ = replay(scene, method, 11, config, Predictor(config))
            self.assertEqual(row['feasible'], 1, method)
            self.assertEqual(row['weighted_ontime_rate'], 1, method)


if __name__ == '__main__':
    unittest.main()
