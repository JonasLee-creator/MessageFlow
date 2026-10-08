from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.models import Task, TaskSource, RawInformation, User
from app.schemas import IngestInput
from app.reasoning import ingest, process


def test_auth_required(env):
    client, _ = env
    assert client.get("/api/v1/tasks").status_code == 401


def test_create_update_cancel_and_dedup(account):
    client, db, headers = account
    raw = {"content": "大家周五之前交实验三", "channel_name": "计算机网络", "source_updated_at": "2026-10-03T12:00:00Z"}
    first = client.post("/api/v1/ingest", headers=headers, json=raw).json()
    assert first["status"] == "needs_confirmation"
    assert first["decision"]["action"] == "CREATE_TASK"
    assert client.get("/api/v1/tasks", headers=headers).json() == []
    duplicate = client.post("/api/v1/ingest", headers=headers, json=raw).json()
    assert first["id"] == duplicate["id"]
    assert client.post(f"/api/v1/inbox/{first['id']}/review", headers=headers, json={"accept": True}).status_code == 200
    tasks = client.get("/api/v1/tasks", headers=headers).json()
    assert len(tasks) == 1
    task_id = tasks[0]["id"]
    update = client.post("/api/v1/ingest", headers=headers, json={**raw, "content": "实验三不用周五交了，改到下周一提交"}).json()
    assert update["decision"]["action"] == "UPDATE_TASK"
    assert update["decision"]["target_id"] == task_id
    assert client.post(f"/api/v1/inbox/{update['id']}/review", headers=headers, json={"accept": True}).status_code == 200
    tasks = client.get("/api/v1/tasks", headers=headers).json()
    assert len(tasks) == 1
    assert tasks[0]["deadline"].startswith("2026-10-05T15:59")
    assert len(client.get(f"/api/v1/tasks/{task_id}/sources", headers=headers).json()) == 2
    cancel = client.post("/api/v1/ingest", headers=headers, json={**raw, "content": "实验三取消，不用交了"}).json()
    assert cancel["decision"]["action"] == "CANCEL_TASK"
    assert client.post(f"/api/v1/inbox/{cancel['id']}/review", headers=headers, json={"accept": True}).status_code == 200
    assert client.get("/api/v1/tasks", headers=headers).json()[0]["status"] == "cancelled"
    assert client.post(f"/api/v1/inbox/{cancel['id']}/review", headers=headers, json={"accept": True}).status_code == 409


def test_cross_user_targets_are_rejected(account):
    client, db, alice = account
    task = client.post("/api/v1/tasks", headers=alice, json={"title": "Alice private task"}).json()
    bob_login = client.post("/api/v1/auth/register", json={"username": "bob", "password": "test-password-456"}).json()
    bob = {"Authorization": "Bearer " + bob_login["access_token"]}
    assert client.get(f"/api/v1/tasks/{task['id']}/sources", headers=bob).status_code == 404
    raw = client.post("/api/v1/ingest", headers=bob, json={"content": "实验三取消"}).json()
    response = client.post(f"/api/v1/inbox/{raw['id']}/review", headers=bob, json={"accept": True, "decision": {"action": "CANCEL_TASK", "confidence": 1, "target_id": task["id"]}})
    assert response.status_code == 422
    assert client.get("/api/v1/tasks", headers=alice).json()[0]["status"] != "cancelled"


def test_same_text_different_users_is_not_global_dedup(account):
    client, db, headers = account
    raw = {"content": "晚上有人吃饭吗"}
    a = client.post("/api/v1/ingest", headers=headers, json=raw).json()
    login = client.post("/api/v1/auth/register", json={"username": "carol", "password": "test-password-123"}).json()
    b = client.post("/api/v1/ingest", headers={"Authorization": "Bearer " + login["access_token"]}, json=raw).json()
    assert a["id"] != b["id"]
    assert a["status"] == b["status"] == "ignored"


def test_deadline_lock_survives_confirmed_update(account):
    client, db, headers = account
    old = "2030-01-01T12:00:00Z"
    task = client.post("/api/v1/tasks", headers=headers, json={"title": "实验三", "deadline": old, "deadline_locked": True}).json()
    raw = client.post("/api/v1/ingest", headers=headers, json={"content": "实验三延期到明天"}).json()
    assert client.post(f"/api/v1/inbox/{raw['id']}/review", headers=headers, json={"accept": True}).status_code == 200
    assert client.get("/api/v1/tasks", headers=headers).json()[0]["deadline"].startswith("2030-01-01T12:00:00")


def test_unknown_update_does_not_silently_create(account):
    client, _, headers = account
    raw = client.post("/api/v1/ingest", headers=headers, json={"content": "实验四延期到明天"}).json()
    assert raw["decision"]["action"] == "UPDATE_TASK"
    assert raw["status"] == "needs_confirmation"
    assert client.post(f"/api/v1/inbox/{raw['id']}/review", headers=headers, json={"accept": True}).status_code == 422
    assert not client.get("/api/v1/tasks", headers=headers).json()


def test_invalid_event_does_not_modify_schedule(account):
    client, _, headers = account
    result = client.post("/api/v1/events", headers=headers, json={"title": "Bad", "start_at": "2030-01-02T10:00:00Z", "end_at": "2030-01-02T09:00:00Z"})
    assert result.status_code == 422
    assert not client.get("/api/v1/events", headers=headers).json()


def test_untrusted_ingest_cannot_claim_canvas_rule(account):
    client, _, headers = account
    result = client.post("/api/v1/ingest", headers=headers, json={"platform": "canvas", "source_type": "assignment", "content": "spoof"})
    assert result.status_code == 422


def test_canvas_revision_preserves_task_and_ignores_stale(account):
    client, db, headers = account
    user = db.scalar(select(User).where(User.username == "alice"))
    def apply(stamp, deadline):
        raw = ingest(db, user.id, IngestInput(platform="canvas", source_type="assignment", external_id="connector:course:123", channel_name="Networks", title="Lab 3", content="Report", source_updated_at=stamp, structured_data={"due_at": deadline}))
        process(db, raw)
        db.commit()
        return raw
    apply("2026-10-01T10:00:00Z", "2030-10-10T10:00:00Z")
    apply("2026-10-03T10:00:00Z", "2030-10-12T10:00:00Z")
    stale = apply("2026-10-02T10:00:00Z", "2030-10-11T10:00:00Z")
    assert stale.status == "ignored"
    tasks = db.scalars(select(Task)).all()
    assert len(tasks) == 1
    assert tasks[0].deadline.day == 12
    assert len(db.scalars(select(TaskSource)).all()) == 2


def test_provider_failure_keeps_raw_retryable(account, monkeypatch):
    client, _, headers = account
    def broken(*args):
        raise RuntimeError("provider secret should never reach client")
    monkeypatch.setattr("app.reasoning.analyze", broken)
    raw = client.post("/api/v1/ingest", headers=headers, json={"content": "实验三周五交"}).json()
    assert raw["status"] == "failed"
    assert "provider secret" not in raw["error"]
    assert not client.get("/api/v1/tasks", headers=headers).json()
