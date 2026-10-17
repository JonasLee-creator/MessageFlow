from datetime import datetime,timezone
import json
import math
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.domain import Block,Task,Scenario
from evaluation.online import OnlineHistory
from evaluation.planners import plan
from evaluation.predictor import Predictor
from evaluation.replay import replay
from evaluation.stable_planner import changed_tasks,guarded_choice


class StablePlannerTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads((ROOT/'evaluation/config_v3.json').read_text())
        self.config['planning_samples']=2
        self.origin=datetime(2026,10,17,8,tzinfo=timezone.utc)
        self.task=Task('a','report','报告','c',3,5,0,0,0,360,60,True)

    def test_session_does_not_count_each_slot_as_independent(self):
        state=OnlineHistory(self.config)
        for m in (0,30,60,90):
            state.observe('a','morning',m,30,True,.75,.75)
        self.assertEqual(state.get('morning',(0,0)),(0,0))
        state.flush(120)
        self.assertEqual(state['morning'],(1.,1.))
        self.assertEqual(state.session_count,1)

    def test_session_boundary_and_missing_feedback(self):
        state=OnlineHistory(self.config)
        state.flush(0)
        self.assertEqual(state.session_count,0)
        state.observe('a','morning',0,30,True,.75,.75)
        state.observe('b','morning',30,30,False,.75,.75)
        self.assertEqual(state.session_count,1)
        state.flush(60)
        self.assertEqual(state.session_count,2)

    def test_cold_start_bounded_update_and_forgetting(self):
        state=OnlineHistory(self.config)
        self.assertEqual(state.adjust(1.,{'morning':.75},0),(1.,{'morning':.75}))
        for i in range(20):
            state.observe(str(i),'morning',i*30,30,False,.75,.75)
            state.flush((i+1)*30)
        early=state.adjust(1.,{'morning':.75},600)[1]['morning']
        later=state.adjust(1.,{'morning':.75},600+100*self.config['online_half_life_minutes'])[1]['morning']
        self.assertGreaterEqual(early,.75-self.config['online_probability_limit'])
        self.assertGreater(later,early)
        self.assertAlmostEqual(later,.75)

    def test_prequential_gate_reverts_harmful_personalization(self):
        state=OnlineHistory(self.config)
        for i in range(6):
            state.observe(str(i),'morning',i*30,30,False,.2,.8)
            state.flush((i+1)*30)
        self.assertAlmostEqual(state.adjust(0.,{'morning':.2},180)[1]['morning'],.2)

    def test_duration_outlier_is_clipped_and_shrunk(self):
        state=OnlineHistory(self.config)
        state.record_duration(1000000,0.,30)
        mu,_=state.adjust(0.,{'morning':.75},30)
        self.assertLessEqual(mu,self.config['online_duration_shift_limit'])
        self.assertAlmostEqual(state['_duration'][0],self.config['online_duration_residual_limit'])

    def test_guard_protects_mean_and_tail_independently(self):
        rows=[dict(name='best',primary=.3,movement=100.,score=.5,deadline_mean=.2,deadline_cvar=.4),
              dict(name='stable-but-risky',primary=.31,movement=0.,score=.31,deadline_mean=.25,deadline_cvar=.6)]
        chosen,_,_=guarded_choice(rows,self.config)
        self.assertEqual(chosen['name'],'best')

    def test_equivalent_fragment_encoding_has_no_physical_changes(self):
        self.assertEqual(changed_tasks([Block('a',0,60)],[Block('a',0,30),Block('a',30,60)],0,30),set())

    def test_global_search_cooldown(self):
        predictor=Predictor(self.config)
        history=OnlineHistory(self.config)
        control={}
        blocks,_=plan('drp_full',[self.task],{},{},0,480,[],[],self.origin,
                      self.config,predictor,history,{},control=control)
        _,detail=plan('drp_full',[self.task],{},{},30,480,[],blocks,self.origin,
                      self.config,predictor,history,{},control=control)
        self.assertTrue(detail['cooldown_active'])
        self.assertEqual(detail['global_search'],0)

    def test_v3_small_fixture_preserves_constraints(self):
        scenario=Scenario('fixture','normal',self.origin,480,[self.task],[(0,60)],
            {'a':{'duration':60.,'probabilities':dict.fromkeys(('morning','afternoon','evening','night'),1.)}})
        row,trace=replay(scenario,'drp_full',11,self.config,Predictor(self.config))
        self.assertEqual(row['feasible'],1)
        self.assertEqual(row['completion_rate'],1)
        self.assertGreater(row['online_sessions'],0)
        for e in trace['events']:
            if 'guard_deadline_mean' in e:
                self.assertLessEqual(e['deadline_mean'],e['guard_deadline_mean']+self.config['deadline_mean_tolerance']+1e-9)
                self.assertLessEqual(e['deadline_cvar'],e['guard_deadline_cvar']+self.config['deadline_tail_tolerance']+1e-9)


if __name__=='__main__':
    unittest.main()
