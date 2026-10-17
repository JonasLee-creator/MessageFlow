from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronoflow_model.config import load_config
from chronoflow_model.features import hashed_ngrams, normalize_title, stable_hash
from chronoflow_model.personalization import BetaPosterior, PersonalModelState
from chronoflow_model.planning import CandidateMetrics, CandidatePlan, PlanBlock, cvar, pareto_front, respects_fixed_intervals, stability_cost
from chronoflow_model.records import TaskRecord
from chronoflow_model.relational_adapter import CausalUserHistory, encode_slot, encode_user_day, outcome_label


class CoreModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(ROOT / "config" / "base.json")

    def test_stable_text_features(self) -> None:
        self.assertEqual(normalize_title(" 完成　实验报告 "), "完成 实验报告")
        self.assertEqual(stable_hash("实验"), stable_hash("实验"))
        vector = hashed_ngrams("完成实验报告", self.config.features)
        self.assertEqual(len(vector), 2048)
        self.assertAlmostEqual(sum(value * value for value in vector), 1.0)

    def test_record_requires_observation_time(self) -> None:
        raw = {
            "task_id": "1", "user_id": "u", "title": "实验", "category": "EXPERIMENT",
            "estimated_minutes": 60, "released_at": "2026-10-01T00:00:00Z",
            "user_state": [0] * 12, "slot_samples": []
        }
        with self.assertRaisesRegex(ValueError, "observed_at"):
            TaskRecord.from_dict(raw, 12, 12)

    def test_unknown_feedback_does_not_update_user(self) -> None:
        state = PersonalModelState()
        state.update_execution("EVENING", "UNKNOWN")
        self.assertEqual(state.sample_count, 0)
        self.assertEqual(state.execution_by_time_bucket["EVENING"].mean, 0.5)
        state.update_execution("EVENING", "COMPLETED")
        self.assertGreater(state.execution_by_time_bucket["EVENING"].mean, 0.5)

    def test_duration_personalization_is_shrunk_to_prior(self) -> None:
        state = PersonalModelState()
        state.update_duration("REPORT", 100, 200)
        multiplier = state.duration_by_category["REPORT"].multiplier
        self.assertGreater(multiplier, 1.0)
        self.assertLess(multiplier, 2.0)

    def test_risk_and_constraint_primitives(self) -> None:
        self.assertEqual(cvar([1, 2, 3, 100], .75), 100)
        self.assertTrue(respects_fixed_intervals([PlanBlock("a", 120, 180)], [(0, 60)]))
        self.assertFalse(respects_fixed_intervals([PlanBlock("a", 30, 90)], [(0, 60)]))
        self.assertEqual(stability_cost([PlanBlock("a", 60, 90)], [PlanBlock("a", 90, 120)], 120), float("inf"))

    def test_pareto_filter(self) -> None:
        def plan(name: str, first: float, second: float) -> CandidatePlan:
            metrics = CandidateMetrics(first, second, 0, 0, 0, 0, 0, 0)
            return CandidatePlan(name, (), metrics)
        result = pareto_front([plan("dominated", 2, 2), plan("risk", 0, 3), plan("balanced", 1, 1)])
        self.assertEqual({row.name for row in result}, {"risk", "balanced"})

    def test_relational_adapter_masks_unknown_and_has_fixed_dimensions(self) -> None:
        self.assertIsNone(outcome_label("UNKNOWN"))
        self.assertEqual(outcome_label("COMPLETED"), 1)
        self.assertEqual(outcome_label("DELAYED"), 0)
        state = encode_user_day({
            "recent_7_day_completion_rate": .8, "completed_blocks": 4, "skipped_blocks": 1,
            "delayed_blocks": 1, "actual_work_minutes": 240, "planned_work_minutes": 300,
            "task_backlog": 3, "overdue_task_count": 1, "average_estimation_error": .2,
            "average_start_delay": 60, "consecutive_work_minutes": 90,
        })
        self.assertEqual(len(state), 12)
        slot = encode_slot({
            "block_id": "b", "planned_start": "2026-10-17T08:00:00+08:00",
            "planned_end": "2026-10-17T09:00:00+08:00", "time_bucket": "morning",
            "daily_workload_before_block": 120, "continuous_work_minutes_before_block": 60,
            "deadline_distance_minutes": 1440, "task_release_age_minutes": 120,
            "predicted_duration_quantile": "p80",
        })
        self.assertEqual(len(slot), 12)

    def test_missing_deadline_is_not_encoded_as_immediate_deadline(self) -> None:
        slot = encode_slot({
            "block_id": "b", "planned_start": "2026-10-17T08:00:00+08:00",
            "planned_end": "2026-10-17T09:00:00+08:00", "time_bucket": "morning",
            "daily_workload_before_block": 0, "continuous_work_minutes_before_block": 0,
            "deadline_distance_minutes": None, "task_release_age_minutes": 120,
            "predicted_duration_quantile": "p80",
        })
        self.assertEqual(slot[9], 1.0)

    def test_user_history_never_reads_same_day_or_future(self) -> None:
        history = CausalUserHistory([
            {"anonymous_user_id": "u", "date": "2026-10-16", "completed_blocks": 2,
             "skipped_blocks": 0, "delayed_blocks": 0, "actual_work_minutes": 60,
             "planned_work_minutes": 90, "task_backlog": 2, "overdue_task_count": 0,
             "average_estimation_error": 0, "average_start_delay": 30,
             "consecutive_work_minutes": 60, "recent_7_day_completion_rate": .7},
            {"anonymous_user_id": "u", "date": "2026-10-17", "completed_blocks": 9,
             "skipped_blocks": 0, "delayed_blocks": 0, "actual_work_minutes": 500,
             "planned_work_minutes": 500, "task_backlog": 1, "overdue_task_count": 0,
             "average_estimation_error": 0, "average_start_delay": 30,
             "consecutive_work_minutes": 180, "recent_7_day_completion_rate": 1.0},
        ])
        state = history.state_before("u", datetime(2026, 10, 17, 20, tzinfo=timezone.utc))
        self.assertAlmostEqual(state[1], .2)


if __name__ == "__main__":
    unittest.main()

