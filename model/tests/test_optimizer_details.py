from dataclasses import replace
from datetime import datetime,timezone,timedelta
import json
import math
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.domain import Task,Block,Scenario
from evaluation.incremental_repairs import conditional_total,duration_budgets,trim_unfrozen_tails,feasible_execution_rates,incremental_candidates
from evaluation.improved_planner import rollout_loss
from evaluation.metrics import feasibility,disruption,paired_bootstrap
from evaluation.planners import plan
from evaluation.predictor import Predictor
from evaluation.prediction_metrics import binary_metrics,duration_metrics
from evaluation.replay import replay


class OptimizerDetailTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads((ROOT/'evaluation/config_integrated_plus.json').read_text())
        self.config['planning_samples']=4
        self.origin=datetime(2026,10,17,8,tzinfo=timezone.utc)
        self.task=Task('a','report','报告','c',3,5,0,0,0,360,60,True)
        self.at=lambda m:self.origin+timedelta(minutes=m)
        self.predictions={'a':(math.log(60),.4,dict.fromkeys(('morning','afternoon','evening','night'),.8))}

    def test_survival_budget_exceeds_unconditional_overrun(self):
        from evaluation.predictor import quantile
        total=conditional_total(math.log(60),.8,120,.8,30)
        self.assertGreater(total,max(quantile(math.log(60),.8,.8),150))

    def test_progress_is_not_added_twice_to_remaining_budget(self):
        total=conditional_total(math.log(60),.4,30,.8,30)
        budget=duration_budgets([self.task],{'a':30},self.predictions,.8,30)['a']
        self.assertEqual(total,budget)
        self.assertNotEqual(budget,total+30)

    def test_execution_buffer_ignores_unavailable_night(self):
        predictions={'a':(math.log(60),.4,{'morning':.8,'afternoon':.8,'evening':.8,'night':.01})}
        rates=feasible_execution_rates([self.task],predictions,0,480,[],[],self.origin,self.config,{})
        self.assertAlmostEqual(rates['a'],.8)
        budget=duration_budgets([self.task],{},predictions,.8,30,True,rates)['a']
        self.assertAlmostEqual(budget,conditional_total(math.log(60),.4,0,.8,30)/.8)

    def test_trim_keeps_frozen_prefix_and_nonsplittable_work(self):
        b=replace(self.task,id='b',splittable=False)
        old=[Block('a',0,30),Block('a',180,210),Block('a',210,240),Block('b',300,360)]
        result=trim_unfrozen_tails(old,[self.task,b],{}, {'a':60,'b':30},0,120,30)
        self.assertEqual(result,[Block('a',0,30),Block('a',180,210),Block('b',300,360)])

    def test_topups_never_remove_existing_commitments(self):
        old=[Block('a',60,90)]
        candidates=incremental_candidates([self.task],{}, {},0,480,[],old,self.origin,self.config,self.predictions,{})
        for name,blocks,_ in candidates:
            if name.startswith('topup'):
                self.assertIn(old[0],blocks)
                self.assertFalse(feasibility(blocks,[self.task],[],360,self.at))

    def test_preindexed_rollouts_are_identical(self):
        tasks=[self.task,replace(self.task,id='b',splittable=False)]
        predictions={**self.predictions,'b':self.predictions['a']}
        blocks=[Block('a',0,30),Block('b',30,60),Block('a',60,90),Block('b',120,180)]
        prepared={t.id:[b for b in blocks if b.task_id==t.id] for t in tasks}
        for sample in range(8):
            raw=rollout_loss(blocks,tasks,{},predictions,0,480,self.origin,self.config,sample,components=True)
            indexed=rollout_loss(blocks,tasks,{},predictions,0,480,self.origin,self.config,sample,components=True,prepared_blocks=prepared)
            self.assertEqual(raw,indexed)

    def test_active_commitment_is_frozen_for_list_and_generator(self):
        for old in ([Block('a',0,90)],iter([Block('a',0,90)])):
            _,violations=disruption(old,[Block('a',30,60)],30,120)
            self.assertEqual(violations,1)

    def test_capacity_includes_time_already_used(self):
        errors=feasibility([Block('a',120,180)],[self.task],[],360,self.at,
            now=120,used={self.at(0).date().isoformat():330},horizon=480,working_hours=[8,22])
        self.assertIn('daily_capacity',errors)

    def test_unknown_task_horizon_and_working_hours_are_checked(self):
        self.assertIn('unknown_task',feasibility([Block('x',0,30)],[self.task],[],360,self.at))
        self.assertIn('outside_horizon',feasibility([Block('a',450,510)],[self.task],[],360,self.at,horizon=480))
        self.assertIn('outside_working_hours',feasibility([Block('a',840,870)],[self.task],[],360,self.at,working_hours=[8,22]))

    def test_mismatched_predictions_fail_instead_of_truncating(self):
        with self.assertRaises(ValueError):
            binary_metrics([.5],[1,0])
        with self.assertRaises(ValueError):
            duration_metrics([(0.,1.)],[10,20])
        with self.assertRaises(ValueError):
            binary_metrics([float('nan')],[1])
        with self.assertRaises(ValueError):
            duration_metrics([(0.,0.)],[10])

    def test_statistics_pair_exact_seeds(self):
        rows=[{'scenario_id':'s','seed':1,'method':'edf','x':0},
              {'scenario_id':'s','seed':2,'method':'drp_full','x':100}]
        self.assertEqual(paired_bootstrap(rows,'edf','drp_full','x',20,1)['clusters'],0)
        rows.append({'scenario_id':'s','seed':1,'method':'drp_full','x':1})
        self.assertEqual(paired_bootstrap(rows,'edf','drp_full','x',20,1)['difference'],1)
        rows.append(dict(rows[0]))
        with self.assertRaises(ValueError):
            paired_bootstrap(rows,'edf','drp_full','x',20,1)

    def test_plus_fixture_remains_feasible_and_guarded(self):
        scenario=Scenario('plus-fixture','normal',self.origin,480,[self.task],[(0,60)],
            {'a':{'duration':60.,'probabilities':dict.fromkeys(('morning','afternoon','evening','night'),1.)}})
        row,trace=replay(scenario,'drp_full',11,self.config,Predictor(self.config))
        self.assertEqual(row['feasible'],1)
        self.assertEqual(row['completion_rate'],1)
        for event in trace['events']:
            if 'guard_passed' in event:
                self.assertEqual(event['guard_passed'],1)
                self.assertEqual(event['optimizer_revision'],2)


if __name__=='__main__':
    unittest.main()
