from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from evaluation.domain import Task,Scenario
from evaluation.planners import plan
from evaluation.predictor import Predictor
from evaluation.replay import replay
from run_planner_ablations import build_configs,CASES,SWITCHES,CONTROL_PARAMETERS


class PlannerSwitchTests(unittest.TestCase):
    def setUp(self):
        self.base=json.loads((ROOT/'evaluation/config_v2.json').read_text())
        self.defaults=json.loads((ROOT/'evaluation/config_v3.json').read_text())
        self.base['planning_samples']=2
        self.configs=build_configs(self.base,self.defaults)
        self.origin=datetime(2026,10,17,8,tzinfo=timezone.utc)
        self.task=Task('a','report','报告','c',3,5,0,0,0,360,60,True)

    def test_only_control_switches_differ_between_cases(self):
        original=deepcopy(self.base)
        configs=build_configs(self.base,self.defaults)
        self.assertEqual(original,self.base)
        for name,config in configs.items():
            self.assertEqual(tuple(config[k] for k in SWITCHES),CASES[name])
            self.assertEqual(config['planner_version'],2)
            self.assertEqual(config['online_version'],1)
            for key,value in configs['reference'].items():
                if key not in SWITCHES and key!='ablation_case':
                    self.assertEqual(config[key],value,(name,key))

    def test_disabled_switches_reproduce_v2(self):
        def compute(config,old,now,control):
            return plan('drp_full',[self.task],{},{},now,480,[],old,self.origin,
                        config,Predictor(config),{},{},control=control)
        controls=[{},{}]
        old_a,detail_a=compute(self.base,[],0,controls[0])
        old_b,detail_b=compute(self.configs['reference'],[],0,controls[1])
        self.assertEqual((old_a,detail_a),(old_b,detail_b))
        self.assertEqual(compute(self.base,old_a,30,controls[0]),
                         compute(self.configs['reference'],old_b,30,controls[1]))

    def test_cooldown_is_independent_of_local_repair(self):
        config=self.configs['cooldown_only']
        control={}
        predictor=Predictor(config)
        blocks,_=plan('drp_full',[self.task],{},{},0,480,[],[],self.origin,
                       config,predictor,{},{},control=control)
        _,detail=plan('drp_full',[self.task],{},{},30,480,[],blocks,self.origin,
                       config,predictor,{},{},control=control)
        self.assertEqual(detail['global_search'],0)
        self.assertFalse(detail['candidate'].startswith('local_'))

    def test_disabling_v3_cooldown_enables_global_search(self):
        config=dict(self.defaults,enable_local_repair=False,enable_replan_cooldown=False,
                    enable_low_gain_rejection=False,planning_samples=2)
        control={}
        predictor=Predictor(config)
        blocks,_=plan('drp_full',[self.task],{},{},0,480,[],[],self.origin,
                       config,predictor,{},{},control=control)
        _,detail=plan('drp_full',[self.task],{},{},30,480,[],blocks,self.origin,
                       config,predictor,{},{},control=control)
        self.assertEqual(detail['global_search'],1)
        self.assertEqual(detail['rejected_low_gain'],0)
        self.assertFalse(detail['candidate'].startswith('local_'))

    def test_all_switch_cases_preserve_toy_feasibility(self):
        scenario=Scenario('switch-fixture','normal',self.origin,480,[self.task],[(0,60)],
            {'a':{'duration':60.,'probabilities':dict.fromkeys(('morning','afternoon','evening','night'),1.)}})
        for name,config in self.configs.items():
            row,_=replay(scenario,'drp_full',11,config,Predictor(config))
            self.assertEqual(row['feasible'],1,name)
            self.assertEqual(row['completion_rate'],1,name)

    def test_runner_prepare_does_not_evaluate(self):
        # Use the workspace: Windows sandbox child processes may not share a
        # parent process's private OS temporary directory.
        scratch=ROOT/'evaluation/results'
        scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            output=Path(folder)/'prepared'
            result=subprocess.run([sys.executable,str(ROOT/'scripts/run_planner_ablations.py'),
                '--output',str(output),'--cases','reference','local_only'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            manifest=json.loads((output/'experiment.json').read_text())
            self.assertEqual(manifest['status'],'prepared')
            self.assertFalse(manifest['training'])
            self.assertTrue((output/'configs/local_only.json').is_file())
            self.assertFalse((output/'reference/runs.jsonl').exists())


if __name__=='__main__':
    unittest.main()
