from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from deployment.android import AndroidPredictor, run
from deployment.planning import make_plan
from evaluation.predictor import Predictor
from evaluation.domain import Task


class Bridge:
    def infer(self, raw):
        self.inputs = json.loads(raw)
        return json.dumps(dict(duration_parameters=[math.log(60), .3], execution_logits=[1., 2., 1., 0.]))


class AndroidEmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.folder = ROOT / 'deployment/artifacts'
        self.config = json.loads((ROOT / 'evaluation/config_integrated.json').read_text())
        self.clock = datetime(2026, 10, 18, 0, tzinfo=timezone.utc)
        self.payload = dict(consent=True, timezone='Asia/Shanghai',
            tasks=[dict(id='a', title='实验报告', category='REPORT', course='C1',
                minutes=60, remaining=60, releasedAt='2026-10-17T08:00:00+08:00',
                deadline='2026-10-19T18:00:00+08:00')], events=[], blocks=[], history=[])

    def test_bridge_features_and_cached_inference(self):
        bridge = Bridge()
        predictor = AndroidPredictor(self.config, bridge, self.folder)
        task = Task('a', '实验报告😀', '报告', 'C1', 3, 5, 0, 0, 0, 1440, 60., True)
        value = predictor.base(task, self.clock, 0)
        self.assertAlmostEqual(value[0], math.log(60))
        self.assertAlmostEqual(value[2]['afternoon'], 1 / (1 + math.exp(-2)))
        self.assertEqual(len(bridge.inputs['hashed_text'][0]), 2048)
        self.assertEqual(len(bridge.inputs['slot_features'][0]), 4)
        self.assertEqual(len(bridge.inputs['slot_features'][0][0]), 12)
        self.assertEqual(predictor.base(task, self.clock, 0), value)

    def test_android_entry_uses_same_features_and_optimizer(self):
        android = json.loads(run(json.dumps(self.payload), Bridge(), str(self.folder), self.clock.isoformat()))
        expected = make_plan(self.payload, lambda c: AndroidPredictor(c, Bridge(), self.folder), now=self.clock)
        self.assertTrue(android['trained'])
        self.assertEqual(android['engine'], 'chronoflow-local')
        for key in ('blocks', 'risks', 'predictions', 'forecast'):
            self.assertEqual(android[key], expected[key])

    def test_running_commitment_does_not_become_unavailable(self):
        self.payload['blocks'] = [dict(taskId='a', start='2026-10-18T07:30:00+08:00',
            end='2026-10-18T08:30:00+08:00', locked=True)]
        self.payload['settings'] = dict(startHour=7, endHour=22)
        result = make_plan(self.payload, Predictor, now=self.clock)
        self.assertIn(self.payload['blocks'][0], result['blocks'])

    def test_nonfinite_model_output_is_rejected(self):
        class Bad:
            def infer(self, _):
                return '{"duration_parameters":[NaN,0.3],"execution_logits":[1,2,3,4]}'
        with self.assertRaisesRegex(ValueError, 'invalid trained model output'):
            run(json.dumps(self.payload), Bad(), str(self.folder), self.clock.isoformat())

    def test_empty_workspace_does_not_infer(self):
        self.payload['tasks'] = []
        class Never:
            def infer(self, _):
                raise AssertionError('empty workspace must not infer')
        result = json.loads(run(json.dumps(self.payload), Never(), str(self.folder), self.clock.isoformat()))
        self.assertEqual(result['blocks'], [])
