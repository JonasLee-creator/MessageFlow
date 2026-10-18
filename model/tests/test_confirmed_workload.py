"""Product regressions: confirmed remaining work is not a retry budget."""
from datetime import datetime, timezone
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'src')]
from deployment.planning import make_plan
from evaluation.predictor import Predictor, BUCKETS


class LongForecast(Predictor):
    def base(self, task, origin, now):
        return math.log(600), .8, dict.fromkeys(BUCKETS, .65)


class ShortForecast(Predictor):
    def base(self, task, origin, now):
        return math.log(5), .08, dict.fromkeys(BUCKETS, .99)


class ConfirmedWorkloadTests(unittest.TestCase):
    def setUp(self):
        self.clock = datetime(2026, 10, 18, 12, 48, tzinfo=timezone.utc)
        self.payload = dict(consent=True, timezone='Asia/Shanghai',
            settings=dict(workloadPolicy='confirmed', startHour=8, endHour=22),
            tasks=[dict(id='math', title='高等数学复习', category='REVIEW', course='高等数学',
                minutes=60, remaining=60, releasedAt='2026-10-18T20:46:00+08:00',
                deadline='2026-10-20T22:00:00+08:00', splittable=True)],
            events=[], blocks=[], history=[])

    def planned_minutes(self, result, task='math'):
        return sum((datetime.fromisoformat(b['end'])-datetime.fromisoformat(b['start'])).total_seconds()/60
                   for b in result['blocks'] if b['taskId']==task)

    def block(self, a, b, locked=False):
        return dict(taskId='math', start=a, end=b, locked=locked)

    def test_60_minutes_are_not_repeated_on_monday_for_long_forecast(self):
        out = make_plan(self.payload, LongForecast, now=self.clock)
        self.assertEqual(self.planned_minutes(out), 60)
        self.assertTrue(all(datetime.fromisoformat(b['start']).day==18 for b in out['blocks']))
        self.assertGreater(out['predictions'][0]['p80Minutes'], 60)  # Advice remains visible.

    def test_small_prediction_does_not_erase_confirmed_work(self):
        out = make_plan(self.payload, ShortForecast, now=self.clock)
        self.assertEqual(self.planned_minutes(out), 60)

    def test_old_extra_reservations_are_cleaned_without_accumulating(self):
        sunday = [self.block('2026-10-18T21:00:00+08:00', '2026-10-18T21:30:00+08:00'),
                  self.block('2026-10-18T21:30:00+08:00', '2026-10-18T22:00:00+08:00')]
        self.payload['blocks'] = sunday + [self.block(f'2026-10-19T{hour:02d}:00:00+08:00',
            f'2026-10-19T{hour+1:02d}:00:00+08:00') for hour in range(8,14)]
        for _ in range(3):
            out = make_plan(self.payload, LongForecast, now=self.clock)
            self.assertEqual(self.planned_minutes(out), 60)
            self.assertEqual(out['blocks'], sunday)
            self.payload['blocks'] = out['blocks']

    def test_partial_nonsplittable_work_does_not_restore_full_estimate(self):
        self.payload['tasks'][0].update(minutes=120, remaining=30, splittable=False)
        out = make_plan(self.payload, LongForecast, now=self.clock)
        self.assertEqual(self.planned_minutes(out), 30)

    def test_rounding_is_once_per_task_and_fixed_class_is_avoided(self):
        self.payload['tasks'][0].update(minutes=45, remaining=45)
        self.payload['events'] = [dict(start='2026-10-18T21:00:00+08:00', end='2026-10-18T22:00:00+08:00')]
        out = make_plan(self.payload, LongForecast, now=self.clock)
        self.assertEqual(self.planned_minutes(out), 60)
        self.assertTrue(all(datetime.fromisoformat(b['start']).day>=19 for b in out['blocks']))

    def test_lock_is_preserved_and_extra_unlocked_work_removed(self):
        lock = self.block('2026-10-19T09:00:00+08:00', '2026-10-19T09:30:00+08:00', True)
        self.payload['blocks'] = [lock, self.block('2026-10-19T10:00:00+08:00', '2026-10-19T12:00:00+08:00')]
        out = make_plan(self.payload, LongForecast, now=self.clock)
        self.assertIn(lock, out['blocks'])
        self.assertEqual(self.planned_minutes(out), 60)

    def test_conflicting_lock_is_reported_not_silently_deleted(self):
        self.payload['blocks'] = [self.block('2026-10-19T09:00:00+08:00', '2026-10-19T11:00:00+08:00', True)]
        with self.assertRaisesRegex(ValueError, '锁定'):
            make_plan(self.payload, LongForecast, now=self.clock)

    def test_no_new_work_after_deadline_when_confirmed(self):
        self.payload['tasks'][0]['deadline'] = '2026-10-18T21:30:00+08:00'
        out = make_plan(self.payload, LongForecast, now=self.clock)
        self.assertEqual(self.planned_minutes(out), 30)
        self.assertEqual(out['risks'][0]['missingMinutes'], 30)

    def test_task_budgets_are_independent(self):
        self.payload['tasks'].append(dict(self.payload['tasks'][0], id='second', title='英语阅读',
                                          minutes=90, remaining=90))
        out = make_plan(self.payload, LongForecast, now=self.clock)
        self.assertEqual(self.planned_minutes(out), 60)
        self.assertEqual(self.planned_minutes(out, 'second'), 90)
