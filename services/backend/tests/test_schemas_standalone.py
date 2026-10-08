"""Runnable with Python + Pydantic only; no database/web/solver dependency."""
import unittest
from pydantic import ValidationError
from app.schemas import AIAction, EventInput, TaskInput, IngestInput


class SchemaTests(unittest.TestCase):
    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValidationError):
            TaskInput(title="Task", deadline="2026-10-05T12:00:00")

    def test_duration_and_priority_bounds(self):
        for values in ({"estimated_duration": -1}, {"priority": 11}, {"remaining_duration": -1}):
            with self.assertRaises(ValidationError):
                TaskInput(title="Task", **values)

    def test_event_must_have_positive_duration(self):
        with self.assertRaises(ValidationError):
            EventInput(title="Meeting", start_at="2026-10-05T12:00:00Z", end_at="2026-10-05T11:00:00Z")

    def test_action_and_confidence_strict(self):
        with self.assertRaises(ValidationError):
            AIAction(action="DELETE_DATABASE", confidence=1)
        with self.assertRaises(ValidationError):
            AIAction(action="IGNORE", confidence=1.1)

    def test_unknown_fields_rejected(self):
        with self.assertRaises(ValidationError):
            AIAction(action="IGNORE", confidence=0.8, arbitrary_code="bad")

    def test_valid_zoned_deadline(self):
        task = TaskInput(title="Task", deadline="2026-10-05T12:00:00+08:00")
        self.assertIsNotNone(task.deadline.tzinfo)

    def test_missing_and_null_deadline_are_distinct(self):
        omitted = AIAction(action="UPDATE_TASK", confidence=1, task={"title": "Task"})
        cleared = AIAction(action="UPDATE_TASK", confidence=1, task={"deadline": None})
        self.assertNotIn("deadline", omitted.task.model_fields_set)
        self.assertIn("deadline", cleared.task.model_fields_set)

    def test_empty_input_rejected(self):
        with self.assertRaises(ValidationError):
            IngestInput(content="   ")


if __name__ == "__main__":
    unittest.main()
