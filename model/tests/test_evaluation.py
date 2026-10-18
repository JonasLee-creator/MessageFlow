from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from evaluation.domain import Block,Scenario,Task,uniform,scenario_split
from evaluation.metrics import cvar,disruption,feasibility,outcomes,paired_bootstrap,paired_tail_bootstrap
from evaluation.predictor import Predictor
from evaluation.prediction_metrics import binary_metrics,duration_metrics,hypervolume3
from evaluation.replay import replay
from evaluation.planners import METHODS,plan,build_schedule
from evaluation.improved_planner import rollout_loss


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT/'evaluation/config_integrated.json').read_text())
        self.config['planning_samples'] = 2
        self.origin = datetime(2026,10,17,8,tzinfo=timezone.utc)
        self.task = Task('a','report','报告','c',3,5,0,0,0,240,60,True)
        self.scenario = Scenario('test','normal',self.origin,480,[self.task],[(0,60)],
            {'a':{'duration':60.,'probabilities':dict.fromkeys(('morning','afternoon','evening','night'),1.)}})

    def test_fractional_cvar(self):
        self.assertAlmostEqual(cvar([0,1,2],.5),5/3)
        self.assertEqual(cvar([0,1,2],.9),2)

    def test_tied_auc_and_unknown_mask(self):
        metrics=binary_metrics([.5,.5,.9],[0,1,None])
        self.assertEqual(metrics['n'],2)
        self.assertEqual(metrics['auroc'],.5)
        self.assertAlmostEqual(metrics['risk_average_precision'],.5)
        self.assertIsNone(binary_metrics([.9],[1])['auroc'])

    def test_duration_metrics_and_hypervolume(self):
        m=duration_metrics([(math.log(60),.2)],[60])
        self.assertAlmostEqual(m['mae_minutes'],0)
        self.assertEqual(hypervolume3([(1,1,1),(2,2,2)],(3,3,3)),8)

    def test_censoring_not_deleted(self):
        m=outcomes([self.task],{}, {},{}, {'a':60},480)
        self.assertEqual(m['completion_rate'],0)
        self.assertEqual(m['normalized_restricted_latency'],1)
        self.assertEqual(m['censored_fraction'],1)
        self.assertEqual(m['weighted_ontime_rate'],0)

    def test_removed_and_frozen_blocks_count(self):
        cost,frozen=disruption([Block('a',60,90)],[],0,120)
        self.assertGreater(cost,0)
        self.assertEqual(frozen,1)

    def test_feasibility_checks(self):
        errors=feasibility([Block('a',0,90),Block('a',60,120)], [self.task],[(0,60)],60,self.scenario.at)
        self.assertIn('fixed_conflict',errors)
        self.assertIn('overlap',errors)
        self.assertIn('daily_capacity',errors)

    def test_insertion_does_not_move_frozen_commitment(self):
        locked=Block('a',90,120)
        cost,frozen=disruption([locked],[Block('a',0,30),locked],0,120)
        self.assertEqual(frozen,0)
        self.assertEqual(cost,30)

    def test_all_baselines_complete_tiny_case(self):
        for method in METHODS:
            row,trace=replay(self.scenario,method,11,self.config,Predictor(self.config))
            self.assertEqual(row['constraint_violations'],0,method)
            self.assertEqual(row['completion_rate'],1,method)
            self.assertGreaterEqual(trace['tasks'][0]['first_start'],60)

    def test_deterministic_replay_except_latency(self):
        a,ta=replay(self.scenario,'drp_full',11,self.config,Predictor(self.config))
        b,tb=replay(self.scenario,'drp_full',11,self.config,Predictor(self.config))
        for key in ('planning_seconds_mean','planning_seconds_max'):
            a.pop(key); b.pop(key)
        self.assertEqual(a,b)
        self.assertEqual(ta['attempts'],tb['attempts'])

    def test_plan_cannot_see_truth_or_future(self):
        predictor=Predictor(self.config)
        future=Task('future','future','其他','c',3,5,120,125,120,400,60,True)
        self.scenario.tasks.append(future)
        self.scenario.truth['future'] = {'duration':60.,'probabilities':dict.fromkeys(('morning','afternoon','evening','night'),1.)}
        row,trace=replay(self.scenario,'edf',11,self.config,predictor)
        for snapshot in trace['snapshots']:
            if snapshot['minute']<125:
                self.assertNotIn('future',[b['task_id'] for b in snapshot['blocks']])
        before,_=plan('drp_full',[self.task],{}, {},0,480,[],[],self.origin,self.config,predictor,{}, {})
        self.scenario.truth['a']['duration']=9999
        after,_=plan('drp_full',[self.task],{}, {},0,480,[],[],self.origin,self.config,predictor,{}, {})
        self.assertEqual(before,after)

    def test_common_random_numbers(self):
        self.assertEqual(uniform('s',1,'a',30),uniform('s',1,'a',30))
        self.assertNotEqual(uniform('s',1,'a',30),uniform('s',2,'a',30))
        self.assertIn(scenario_split('s001'),('train','validation','test'))

    def test_cluster_bootstrap_averages_seeds(self):
        rows=[{'scenario_id':'s','method':m,'seed':i%2,'x':v} for i,(m,v) in enumerate([('edf',1),('edf',3),('drp_full',4),('drp_full',6)])]
        result=paired_bootstrap(rows,'edf','drp_full','x',50,1)
        self.assertEqual(result['clusters'],1)
        self.assertEqual(result['difference'],3)
        self.assertEqual(result['ci95_low'],3)

    def test_tail_bootstrap_has_paired_sign(self):
        rows=[{'scenario_id':'s','seed':1,'method':'edf','deadline_loss':1.},
              {'scenario_id':'s','seed':1,'method':'drp_full','deadline_loss':.25}]
        result=paired_tail_bootstrap(rows,'edf','drp_full',20,1,.9)
        self.assertAlmostEqual(result['difference'],-.75)

    def test_prediction_empty_and_crps(self):
        self.assertEqual(binary_metrics([],[]),{'n':0})
        self.assertEqual(duration_metrics([],[]),{'n':0})
        self.assertGreater(duration_metrics([(math.log(60),.2)],[60])['crps_minutes'],0)

    def test_main_preserves_feasibility_and_exposes_candidates(self):
        config=json.loads((ROOT/'evaluation/config_integrated.json').read_text())
        config['planning_samples']=2
        row,trace=replay(self.scenario,'drp_full',11,config,Predictor(config))
        self.assertEqual(row['feasible'],1)
        self.assertEqual(row['completion_rate'],1)
        self.assertTrue(any('candidate_count' in e for e in trace['events']))
        for event in trace['events']:
            if 'primary_loss' in event:
                self.assertLessEqual(event['primary_loss'],event['best_primary_loss']+config['primary_loss_tolerance']+1e-9)

    def test_edf_receives_same_continuity_fix(self):
        from dataclasses import replace
        task=replace(self.task,splittable=False)
        blocks,_=plan('edf',[task],{'a':30},{},0,480,[(0,120)],[],self.origin,
                      self.config,Predictor(self.config),{},{})
        self.assertEqual(blocks,[Block('a',120,180)])

    def test_nonsplit_reservation_does_not_reuse_progress_after_gap(self):
        from dataclasses import replace
        task=replace(self.task,splittable=False)
        blocks=build_schedule([task],{'a':30},{},0,480,[(0,120)],[],self.origin,self.config,
            {'a':60},{'a':dict.fromkeys(('morning','afternoon','evening','night'),1.)},
            'edf',False,{},continuity=True)
        self.assertEqual(blocks,[Block('a',120,180)])

    def test_rollout_resets_nonsplit_progress_after_gap(self):
        from dataclasses import replace
        task=replace(self.task,splittable=False,deadline=150)
        config=json.loads((ROOT/'evaluation/config_integrated.json').read_text())
        predictions={'a':(math.log(60),.00001,dict.fromkeys(('morning','afternoon','evening','night'),1.))}
        loss=rollout_loss([Block('a',120,150)],[task],{'a':30},predictions,0,480,self.origin,config,1)
        self.assertGreaterEqual(loss,1.)


if __name__=='__main__':
    unittest.main()
