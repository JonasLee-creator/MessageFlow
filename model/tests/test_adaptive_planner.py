from dataclasses import replace
from datetime import datetime
import importlib.util
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.adaptive_planner import complexity, validate_config
from evaluation.domain import Task, Block, Scenario
from evaluation.planners import plan, METHODS
from evaluation.predictor import Predictor
from evaluation.replay import replay
from evaluation.improved_planner import rollout_loss

spec = importlib.util.spec_from_file_location('adaptive_validation', ROOT/'scripts/validate_adaptive_planner.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


class CertainPredictor:
    """Fixture only, not a trained predictor or a measured user model."""
    def __init__(self):
        self.cache = {}

    def predict(self, task, origin, now, history, personal):
        return math.log(task.estimate*.8), .00001, dict.fromkeys(('morning','afternoon','evening','night'), 1.)

    def base(self, task, origin, now):
        return self.predict(task, origin, now, {}, False)


class AdaptivePlannerTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT/'evaluation/config_adaptive.json').read_text())
        self.config['planning_samples'] = 4
        self.config['cold_start_model_weight'] = 1.
        self.origin = datetime(2026, 10, 18, 8)
        self.task = Task('a', '报告', 'REPORT', 'C1', 3, 3, 0, 0, 0, 600, 60., True)

    def call(self, tasks=None, old=None, control=None, predictor=None, fixed=None):
        return plan('drp_full', tasks or [self.task], {}, {}, 0, 840, fixed or [], old or [],
            self.origin, self.config, predictor or CertainPredictor(), {}, {}, control=control if control is not None else {})

    def test_low_load_can_skip_complex_reference(self):
        blocks, detail = self.call()
        self.assertTrue(blocks)
        self.assertEqual(detail['adaptive_low_complexity'], 1)
        self.assertEqual(detail['adaptive_complex_reference'], 0)
        self.assertEqual(detail['adaptive_simple_selected'], 1)
        self.assertEqual(blocks[0].start, 0)

    def test_urgent_deadline_and_fixed_capacity_route_to_complex(self):
        task = replace(self.task, deadline=90)
        _, detail = self.call([task])
        self.assertEqual(detail['adaptive_low_complexity'], 0)
        self.assertEqual(detail['adaptive_complex_reference'], 1)
        _, detail = self.call(fixed=[(0, 570)])
        self.assertEqual(detail['adaptive_low_complexity'], 0)

    def test_late_earliest_start_cannot_borrow_morning_capacity(self):
        task = replace(self.task, earliest=570, deadline=600)
        predictions = {'a':CertainPredictor().predict(task,None,None,None,None)}
        low, features = complexity([task], {}, 0, 840, [], [], self.origin, self.config, predictions, {})
        self.assertFalse(low)
        self.assertGreater(features['load'], 1)

    def test_frozen_and_active_commitments_are_preserved(self):
        old = [Block('a', 0, 60)]
        blocks, _ = self.call(old=old, control={'last_change':-20})
        self.assertIn(old[0], blocks)

    def test_evening_capacity_does_not_disappear_into_unused_morning_budget(self):
        task = replace(self.task, earliest=600, deadline=840)
        predictions = {'a':CertainPredictor().predict(task,None,None,None,None)}
        _, features = complexity([task], {}, 0, 840, [], [], self.origin, self.config, predictions, {})
        self.assertLess(features['load'], 1)

    def test_failed_cheap_verification_falls_back_to_original(self):
        original = rollout_loss
        n = self.config['planning_samples']
        def fail(*args, **kwargs):
            row = original(*args, **kwargs)
            if args[8] >= 4*n:
                row = dict(row, deadline=1., completion_loss=1.)
            return row
        with patch('evaluation.adaptive_planner.rollout_loss', side_effect=fail):
            _, detail = self.call()
        self.assertEqual(detail['adaptive_complex_reference'], 1)
        self.assertEqual(detail['adaptive_verification_fallback'], 1)
        self.assertEqual(detail['candidate'], 'integrated_reference')
        self.assertEqual(detail['adaptive_simple_selected'], 0)

    def test_complex_reference_does_not_mutate_final_unchanged_commitment_clock(self):
        control = {'last_change':-123, 'known_ids':['a']}
        self.config['adaptive_max_load'] = 0.
        self.call(old=[Block('a', 0, 60)], control=control)
        self.assertEqual(control['last_change'], -123)

    def test_search_and_verification_samples_disjoint_from_original(self):
        with patch('evaluation.adaptive_planner.rollout_loss', wraps=rollout_loss) as sampled:
            self.call()
        n = self.config['planning_samples']
        draws = {call.args[8] for call in sampled.call_args_list}
        self.assertEqual(draws, set(range(3*n, 5*n)))

    def test_determinism_and_truth_not_in_interface(self):
        self.assertEqual(self.call(), self.call())

    def test_invalid_thresholds_and_plus_anchor_rejected(self):
        for value in (-1, float('nan'), 2, True):
            with self.assertRaises(ValueError):
                validate_config(dict(self.config, adaptive_max_load=value))
        with self.assertRaises(ValueError):
            validate_config(dict(self.config, optimizer_revision=2))

    def test_selection_keeps_original_when_any_primary_metric_worsens(self):
        ref = dict(weighted_ontime_rate=.8, cvar_deadline_loss=.5,
            normalized_restricted_latency=.4, disruption_minutes=100., feasible=1.)
        rows = {'reference':ref, 'bad':dict(ref, weighted_ontime_rate=.79, disruption_minutes=1.)}
        self.assertEqual(driver.select_case(rows)[0], 'reference')
        rows['good'] = dict(ref, normalized_restricted_latency=.39)
        self.assertEqual(driver.select_case(rows)[0], 'good')

    def test_all_baselines_unaffected_by_version_five_config(self):
        ref = dict(self.config, planner_version=4)
        for method in METHODS:
            if method == 'drp_full':
                continue
            args = (method, [self.task], {}, {}, 0, 600, [], [], self.origin)
            a = plan(*args, self.config, Predictor(self.config), {}, {})
            b = plan(*args, ref, Predictor(ref), {}, {})
            self.assertEqual(a,b,method)

    def test_toy_replay_completes_with_constraints(self):
        scene = Scenario('adaptive-toy', 'normal', self.origin, 600, [self.task], [],
            {'a':dict(duration=60., probabilities=dict.fromkeys(('morning','afternoon','evening','night'),1.))})
        row, _ = replay(scene, 'drp_full', 11, self.config, CertainPredictor())
        self.assertEqual(row['feasible'], 1.)
        self.assertEqual(row['weighted_ontime_rate'], 1.)
        self.assertGreater(row['adaptive_simple_selections'], 0)


if __name__ == '__main__':
    unittest.main()
