import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('release_cleanup', ROOT/'scripts/clean_retired_evaluations.py')
clean = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clean)


class V4ReleaseTests(unittest.TestCase):
    def test_main_configuration_and_only_current_entry(self):
        config = json.loads((ROOT/'evaluation/config_integrated.json').read_text())
        self.assertEqual(config['planner_version'], 4)
        self.assertEqual(config['online_version'], 1)
        self.assertEqual(config.get('optimizer_revision', 1), 1)
        self.assertFalse((ROOT/'evaluation/config_adaptive.json').exists())
        self.assertFalse((ROOT/'evaluation/config_v3.json').exists())

    def test_cleanup_keeps_main_results_and_raw_inputs(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder:
            root = Path(folder)
            result = root/'evaluation/results'
            for name in ('v4-test', 'test-seed11-20261017', 'validation-seed11-20261017', 'adaptive-validation20', 'real-replay-20261018'):
                (result/name).mkdir(parents=True)
            (result/'v4-test/config.json').write_text(json.dumps({'planner_version':4}),encoding='utf-8')
            chosen = {p.name for p,_,_ in clean.candidates(root)}
            self.assertEqual(chosen, {'adaptive-validation20', 'real-replay-20261018'})

    def test_cleanup_rejects_parent_target(self):
        with self.assertRaises(ValueError):
            clean.checked_target(ROOT/'tests', ROOT/'tests')
        with self.assertRaises(ValueError):
            clean.checked_target(ROOT/'scripts', ROOT/'tests')
