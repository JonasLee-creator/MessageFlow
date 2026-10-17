from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.domain import Task,Scenario,Block
from evaluation.integrated_planner import paired_upper_difference,passes_guard
from evaluation.improved_planner import rollout_loss
from evaluation.planners import plan
from evaluation.predictor import Predictor
from evaluation.replay import replay


class IntegratedPlannerTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads((ROOT/'evaluation/config_integrated.json').read_text())
        self.config['planning_samples']=4
        self.origin=datetime(2026,10,17,8,tzinfo=timezone.utc)
        self.task=Task('a','report','报告','c',3,5,0,0,0,360,60,True)

    def sample_row(self):
        return {'deadline_samples':[0.,0.,0.,0.],
            'response_samples':[.2,.2,.2,.2],
            'completion_samples':[0.,0.,0.,0.], 'deadline_cvar':0.}

    def test_guard_refuses_each_separate_regression(self):
        reference=self.sample_row()
        for key in ('deadline_samples','response_samples','completion_samples'):
            bad=deepcopy(reference)
            bad[key]=[v+.1 for v in bad[key]]
            self.assertFalse(passes_guard(bad,reference,self.config),key)
        bad=deepcopy(reference)
        bad['deadline_cvar']=.1
        self.assertFalse(passes_guard(bad,reference,self.config))
        self.assertTrue(passes_guard(reference,reference,self.config))

    def test_paired_uncertainty_guard(self):
        self.assertEqual(paired_upper_difference([1,2],[1,2],1.645),0)
        self.assertGreater(paired_upper_difference([0,1],[.5,.5],1.645),0)
        with self.assertRaises(ValueError):
            paired_upper_difference([1],[1,2],1.645)

    def test_cooldown_cannot_hold_a_risky_empty_plan(self):
        control={'last_change':0,'known_ids':['a']}
        blocks,detail=plan('drp_full',[self.task],{},{},30,480,[],[],self.origin,
            self.config,Predictor(self.config),{},{},control=control)
        self.assertTrue(blocks)
        self.assertEqual(detail['cooldown_bypassed_for_risk'],1)
        self.assertEqual(detail['guard_passed'],1)

    def test_reference_is_always_retained_and_audited(self):
        blocks,detail=plan('drp_full',[self.task],{},{},0,480,[],[],self.origin,
            self.config,Predictor(self.config),{},{},control={})
        self.assertEqual(detail['reference_recomputed'],1)
        self.assertIn('reference_candidate',detail)
        self.assertEqual(detail['guard_passed'],1)
        self.assertTrue(blocks)
        self.assertTrue(all(1<=size<=1 for size in detail['repair_scopes_tried']))

    def test_fixture_completes_with_no_constraint_violations(self):
        scenario=Scenario('integrated-fixture','normal',self.origin,480,[self.task],[(0,60)],
            {'a':{'duration':60.,'probabilities':dict.fromkeys(('morning','afternoon','evening','night'),1.)}})
        row,trace=replay(scenario,'drp_full',11,self.config,Predictor(self.config))
        self.assertEqual(row['completion_rate'],1)
        self.assertEqual(row['feasible'],1)
        self.assertEqual(row['online_sessions'],0)
        for event in trace['events']:
            if 'guard_passed' in event:
                self.assertEqual(event['guard_passed'],1)

    def test_no_ground_truth_is_accepted_by_planner(self):
        config=deepcopy(self.config)
        a=plan('drp_full',[self.task],{},{},0,480,[],[],self.origin,
               config,Predictor(config),{},{},control={})
        # Only the public task and past feedback are accepted by the interface.
        b=plan('drp_full',[self.task],{},{},0,480,[],[],self.origin,
               config,Predictor(config),{},{},control={})
        self.assertEqual(a,b)

    def test_audit_and_verification_use_disjoint_draws(self):
        with patch('evaluation.integrated_planner.rollout_loss',wraps=rollout_loss) as sampled:
            plan('drp_full',[self.task],{},{},0,480,[],[],self.origin,
                 self.config,Predictor(self.config),{},{},control={})
        draws={call.args[8] for call in sampled.call_args_list}
        n=self.config['planning_samples']
        self.assertEqual(draws,set(range(n,3*n)))

    def test_failed_final_verification_falls_back_without_reselection(self):
        n=self.config['planning_samples']
        def guard(candidate,reference,config):
            if candidate['name']=='keep_current':
                return candidate['audit_offset']==n
            return passes_guard(candidate,reference,config)
        with patch('evaluation.integrated_planner.passes_guard',side_effect=guard):
            _,detail=plan('drp_full',[self.task],{},{},30,480,[],[Block('a',300,360)],self.origin,
                self.config,Predictor(self.config),{},{},
                control={'last_change':0,'known_ids':['a']})
        self.assertEqual(detail['verification_fallback'],1)
        self.assertEqual(detail['stage'],'reference')
        self.assertEqual(detail['guard_passed'],1)


if __name__=='__main__':
    unittest.main()
