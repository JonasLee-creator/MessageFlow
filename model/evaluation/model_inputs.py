"""The frozen predictor feature contract, shared by PyTorch and ONNX serving."""
from datetime import timedelta
import math

from chronoflow_model.features import hashed_ngrams, category_index, course_bucket, numeric_features
from chronoflow_model.records import TaskRecord


def predictor_inputs(task, origin, now, features):
    categories = {'实验':'EXPERIMENT','报告':'REPORT','编程':'PROGRAMMING','复习':'REVIEW',
        '背诵':'MEMORIZATION','阅读':'READING','考试准备':'EXAM_PREPARATION','其他':'OTHER'}
    at = lambda minute: origin+timedelta(minutes=minute)
    record = TaskRecord(task.id, 'scenario-cold-start', task.title, categories.get(task.category, 'OTHER'),
        task.course, task.difficulty, task.priority, task.splittable, 0, int(task.estimate),
        at(task.released), at(now), at(task.earliest), at(task.deadline) if task.deadline is not None else None,
        None, None, (0.,)*12, ())
    weekday = 2*math.pi*at(now).weekday()/7
    deadline = 1. if task.deadline is None else max(-1., min(1., (task.deadline-now)/20160))
    slots = [[float(i==j) for i in range(4)]+[math.sin(weekday),math.cos(weekday),
        min(1.,task.estimate/180),0.,0.,deadline,min(1.,(now-task.released)/20160),.5] for j in range(4)]
    return dict(hashed_text=[hashed_ngrams(task.title,features)],
        category_id=[category_index(record.category)], course_id=[course_bucket(task.course,features)],
        numeric_features=[numeric_features(record,at(now),features.numeric_feature_dim)],
        user_state=[[0.]*12], slot_features=[slots], slot_user_state=[[[0.]*12 for _ in range(4)]])
