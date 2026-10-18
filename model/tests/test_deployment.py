from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from deployment.planning import make_plan
from deployment.runtime import OnnxPredictor,verified_artifacts,ARTIFACTS
from evaluation.domain import Task
from evaluation.model_inputs import predictor_inputs
from evaluation.predictor import Predictor
from chronoflow_model.config import load_config


class FakeSession:
    def run(self,names,feed):
        import numpy as np
        self.feed=feed
        return np.array([[math.log(60),.3]],dtype=np.float32),np.array([[1.,2.,1.,0.]],dtype=np.float32)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.clock=datetime(2026,10,18,0,tzinfo=timezone.utc)
        self.payload=dict(consent=True,timezone='Asia/Shanghai',
            settings=dict(startHour=8,endHour=22,dailyCapacityMinutes=360),
            tasks=[dict(id='a',title='实验报告',category='REPORT',course='C1',difficulty=3,priority=5,
                minutes=60,remaining=60,releasedAt='2026-10-17T10:00:00+08:00',deadline='2026-10-19T18:00:00+08:00',splittable=True)],
            events=[dict(start='2026-10-18T08:00:00+08:00',end='2026-10-18T09:00:00+08:00')],blocks=[],history=[])

    def test_bundled_model_matches_archived_verified_export(self):
        manifest=verified_artifacts()
        self.assertEqual(manifest['chronoflow_predictor.onnx'],'7df73b81f440827ba3bbc6a2977b2769b2f9559ae53b89d31efc683caaa1eaa9')

    def test_onnx_feature_contract_shapes_and_integer_indices(self):
        import numpy as np
        config=json.loads((ROOT/'evaluation/config_integrated.json').read_text())
        session=FakeSession(); predictor=OnnxPredictor(config,session)
        task=Task('a','实验报告','报告','C1',3,5,0,0,0,480,60.,True)
        mu,sigma,prob=predictor.base(task,self.clock,0)
        self.assertAlmostEqual(mu,math.log(60),places=5)
        self.assertAlmostEqual(sigma,.3,places=5)
        self.assertEqual(session.feed['hashed_text'].shape,(1,2048))
        self.assertEqual(session.feed['slot_features'].shape,(1,4,12))
        self.assertEqual(session.feed['category_id'].dtype,np.int64)
        self.assertGreater(prob['afternoon'],prob['morning'])
        self.assertEqual(len(prob),4)

    def test_no_network_secret_or_notification_input_is_required(self):
        out=make_plan(self.payload,Predictor,now=self.clock)
        self.assertEqual(out['engine'],'chronoflow-v4')
        self.assertEqual(len(out['predictions']),1)
        self.assertTrue(out['blocks'])
        self.assertTrue(all(datetime.fromisoformat(b['start']).hour>=9 for b in out['blocks']))

    def test_consent_required(self):
        self.payload['consent']=False
        with self.assertRaisesRegex(ValueError,'consent'):
            make_plan(self.payload,Predictor,now=self.clock)

    def test_future_feedback_and_duplicate_tasks_rejected(self):
        self.payload['history']=[dict(id='h',recordedAt='2030-01-01T00:00:00Z')]
        with self.assertRaisesRegex(ValueError,'future'):
            make_plan(self.payload,Predictor,now=self.clock)
        self.payload['history']=[];self.payload['tasks']*=2
        with self.assertRaisesRegex(ValueError,'duplicate'):
            make_plan(self.payload,Predictor,now=self.clock)

    def test_long_range_user_lock_is_preserved(self):
        self.payload['blocks']=[dict(taskId='a',start='2026-10-18T18:00:00+08:00',end='2026-10-18T19:00:00+08:00',locked=True)]
        out=make_plan(self.payload,Predictor,now=self.clock)
        self.assertTrue(any(b['start']=='2026-10-18T18:00:00+08:00' and b['locked'] for b in out['blocks']))

    def test_no_simulator_truth_can_change_plan(self):
        a=make_plan(self.payload,Predictor,now=self.clock)
        self.payload.update(truth={'duration':999999},canvasAccessToken='secret',notification='private')
        b=make_plan(self.payload,Predictor,now=self.clock)
        self.assertEqual(a,b)

    def test_pending_remaining_and_empty_task_list(self):
        self.payload['tasks']=[]
        out=make_plan(self.payload,Predictor,now=self.clock)
        self.assertEqual(out['blocks'],[])

    def test_completed_actual_duration_personalizes_only_from_the_past(self):
        sample=dict(id='past',title='报告',category='REPORT',course='C1',minutes=60,actualMinutes=120,
            completedAt='2026-10-17T10:00:00+08:00',releasedAt='2026-10-17T08:00:00+08:00')
        baseline=make_plan(self.payload,Predictor,now=self.clock)
        self.payload['completedTasks']=[sample]
        personalized=make_plan(self.payload,Predictor,now=self.clock)
        self.assertGreater(personalized['predictions'][0]['p50Minutes'],baseline['predictions'][0]['p50Minutes'])
        sample['completedAt']='2030-01-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'future'):
            make_plan(self.payload,Predictor,now=self.clock)
