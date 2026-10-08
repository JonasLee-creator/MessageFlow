from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.models import User, Task, Event, ScheduleBlock, ScheduleVersion
from app.scheduling import replan, overlap

CLOCK = datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc)  # Shanghai 08:00


def fixture(db):
    user = User(username="schedule", password_hash="unused")
    db.add(user); db.flush()
    return user


def task(db, user, title="Report", minutes=90, deadline=None, split=True):
    t = Task(user_id=user.id, title=title, remaining_duration=minutes, estimated_duration=minutes, deadline=deadline or CLOCK + timedelta(hours=6), splittable=split)
    db.add(t); db.flush()
    return t


def test_busy_events_and_deadline_end_boundary(env):
    _, db = env
    user = fixture(db)
    t = task(db, user, minutes=60, deadline=CLOCK + timedelta(minutes=135))
    db.add(Event(user_id=user.id, title="Lecture", start_at=CLOCK, end_at=CLOCK + timedelta(hours=1)))
    db.flush()
    result = replan(db, user.id, clock=CLOCK)
    assert result["status"] in ("OPTIMAL", "FEASIBLE")
    blocks = db.scalars(select(ScheduleBlock)).all()
    assert sum((b.end_at - b.start_at).total_seconds() / 60 for b in blocks) == 60
    assert all(b.start_at >= CLOCK + timedelta(hours=1) and b.end_at <= t.deadline for b in blocks)


def test_non_splittable_requires_contiguous_window(env):
    _, db = env
    user = fixture(db)
    task(db, user, minutes=120, deadline=CLOCK + timedelta(hours=3), split=False)
    db.add(Event(user_id=user.id, title="Meeting", start_at=CLOCK + timedelta(hours=1), end_at=CLOCK + timedelta(hours=2)))
    db.flush()
    result = replan(db, user.id, clock=CLOCK)
    assert result["status"] == "INFEASIBLE"
    assert not result["blocks"]
    assert result["risks"]


def test_locked_time_is_preserved_and_not_double_allocated(env):
    _, db = env
    user = fixture(db)
    t = task(db, user, minutes=90)
    locked = ScheduleBlock(user_id=user.id, task_id=t.id, start_at=CLOCK + timedelta(hours=2), end_at=CLOCK + timedelta(hours=3), locked=True, version=1)
    db.add(locked); db.flush()
    original_id = locked.id
    result = replan(db, user.id, clock=CLOCK)
    assert result["status"] in ("OPTIMAL", "FEASIBLE")
    blocks = db.scalars(select(ScheduleBlock)).all()
    assert any(b.id == original_id and b.start_at == CLOCK + timedelta(hours=2) for b in blocks)
    assert sum((b.end_at - b.start_at).total_seconds() / 60 for b in blocks) == 90


def test_shared_capacity_conflict_does_not_hard_schedule(env):
    _, db = env
    user = fixture(db)
    task(db, user, "A", 90, CLOCK + timedelta(hours=2))
    task(db, user, "B", 90, CLOCK + timedelta(hours=2))
    result = replan(db, user.id, clock=CLOCK)
    assert result["status"] == "INFEASIBLE"
    assert result["blocks"] == []


def test_completed_task_loses_future_blocks_and_versions_are_saved(env):
    _, db = env
    user = fixture(db)
    t = task(db, user)
    first = replan(db, user.id, clock=CLOCK)
    t.status = "completed"; t.remaining_duration = 0; db.flush()
    second = replan(db, user.id, "TASK_COMPLETED", clock=CLOCK)
    assert second["version"] == first["version"] + 1
    assert not second["blocks"]
    versions = db.scalars(select(ScheduleVersion).order_by(ScheduleVersion.version)).all()
    assert len(versions[0].snapshot) > 0


def test_overdue_task_has_risk_without_deadline_violation(env):
    _, db = env
    user = fixture(db)
    task(db, user, deadline=CLOCK - timedelta(hours=1))
    result = replan(db, user.id, clock=CLOCK)
    assert result["status"] == "INFEASIBLE"
    assert result["risks"][0]["available_minutes"] == 0


def test_two_tasks_never_overlap(env):
    _, db = env
    user = fixture(db)
    task(db, user, "A", 90)
    task(db, user, "B", 120)
    replan(db, user.id, clock=CLOCK)
    blocks = db.scalars(select(ScheduleBlock)).all()
    for i, a in enumerate(blocks):
        assert all(not overlap(a.start_at, a.end_at, b.start_at, b.end_at) for b in blocks[i + 1:])


def test_locked_block_conflicting_with_new_event_reports_risk(env):
    _, db = env
    user = fixture(db)
    t = task(db, user, minutes=60)
    db.add(ScheduleBlock(user_id=user.id, task_id=t.id, start_at=CLOCK, end_at=CLOCK + timedelta(hours=1), locked=True, version=1))
    db.add(Event(user_id=user.id, title="New class", start_at=CLOCK, end_at=CLOCK + timedelta(hours=1)))
    db.flush()
    result = replan(db, user.id, clock=CLOCK)
    assert result["status"] == "INFEASIBLE"
    assert len(result["blocks"]) == 1  # User lock is retained, conflict is visible.
