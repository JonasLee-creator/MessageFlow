import asyncio
import os
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select

from .db import Base, engine, Session, now
from .models import User, Task, TaskSource, RawInformation, ExtractionResult, Event, ScheduleBlock, ScheduleVersion, Connector, Course
from .schemas import Credentials, TaskInput, EventInput, IngestInput, Review, CanvasInput
from .security import password_hash, password_matches, token, decode, vault
from .reasoning import ingest, process, apply_action
from .scheduling import replan, block_json
from .canvas import public_origin, sync

# V1 runs one Uvicorn process. Serialize state mutations including the polling worker.
# PostgreSQL permits future multi-worker deployment after introducing per-user locks.
state_lock = asyncio.Lock()
bearer = HTTPBearer(auto_error=False)


async def session():
    # Wait outside the threadpool: concurrent HTTP requests cannot exhaust workers
    # while the request that owns the database lock is trying to resume.
    async with state_lock:
        with Session() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise


def current_user(auth: HTTPAuthorizationCredentials = Depends(bearer), db=Depends(session)):
    if not auth:
        raise HTTPException(401, "请先登录")
    user = db.get(User, decode(auth.credentials))
    if not user:
        raise HTTPException(401, "账户不存在")
    return user


def owned(db, cls, item_id, user):
    item = db.get(cls, item_id)
    if not item or item.user_id != user.id:
        raise HTTPException(404, "记录不存在")
    return item


def as_dict(item):
    return {c.name: getattr(item, c.name) for c in item.__table__.columns}


def inbox_item(db, raw):
    extraction = db.scalar(select(ExtractionResult).where(ExtractionResult.raw_id == raw.id))
    return {**as_dict(raw), "decision": extraction.decision if extraction else None, "engine": extraction.engine if extraction else None}


def poll_canvas():
    with Session() as db:
        for connector in db.scalars(select(Connector).where(Connector.enabled.is_(True))).all():
            if connector.last_synced_at is None or now() - connector.last_synced_at >= timedelta(minutes=5):
                sync(db, connector)
                db.commit()


async def poll_loop():
    while True:
        await asyncio.sleep(300)
        try:
            async with state_lock:
                await asyncio.to_thread(poll_canvas)
        except Exception:
            # Next polling cycle retries. Connector errors are visible in the UI.
            pass


@asynccontextmanager
async def lifespan(app):
    if os.getenv("AUTO_CREATE_TABLES", "1") == "1":
        Base.metadata.create_all(engine)
    worker = asyncio.create_task(poll_loop()) if os.getenv("CANVAS_POLL", "1") == "1" else None
    yield
    if worker:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass


app = FastAPI(title="ChronoFlow", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0", "ai_mode": "llm" if os.getenv("LLM_API_KEY") else "local-rules"}


@app.post("/api/v1/auth/register", status_code=201)
def register(payload: Credentials, db=Depends(session)):
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(409, "用户名已存在")
    user = User(username=payload.username, password_hash=password_hash(payload.password))
    db.add(user)
    db.flush()
    return {"access_token": token(user.id), "token_type": "bearer", "username": user.username}


@app.post("/api/v1/auth/login")
def login(payload: Credentials, db=Depends(session)):
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not password_matches(payload.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    return {"access_token": token(user.id), "token_type": "bearer", "username": user.username}


@app.get("/api/v1/tasks")
def tasks(user=Depends(current_user), db=Depends(session)):
    return [as_dict(t) for t in db.scalars(select(Task).where(Task.user_id == user.id).order_by(Task.created_at.desc())).all()]


@app.post("/api/v1/tasks", status_code=201)
def create_task(payload: TaskInput, user=Depends(current_user), db=Depends(session)):
    data = payload.model_dump()
    data["remaining_duration"] = payload.remaining_duration if payload.remaining_duration is not None else payload.estimated_duration
    task = Task(user_id=user.id, **data)
    db.add(task)
    db.flush()
    replan(db, user.id, "TASK_CREATED")
    return as_dict(task)


@app.put("/api/v1/tasks/{task_id}")
def update_task(task_id: str, payload: TaskInput, user=Depends(current_user), db=Depends(session)):
    task = owned(db, Task, task_id, user)
    for k, v in payload.model_dump().items():
        if k == "remaining_duration" and v is None:
            continue
        setattr(task, k, v)
    db.flush()
    replan(db, user.id, "TASK_UPDATED")
    return as_dict(task)


@app.post("/api/v1/tasks/{task_id}/complete")
def complete(task_id: str, user=Depends(current_user), db=Depends(session)):
    task = owned(db, Task, task_id, user)
    task.status, task.remaining_duration = "completed", 0
    db.flush()
    replan(db, user.id, "TASK_COMPLETED")
    return as_dict(task)


@app.delete("/api/v1/tasks/{task_id}")
def cancel_task(task_id: str, user=Depends(current_user), db=Depends(session)):
    task = owned(db, Task, task_id, user)
    task.status = "cancelled"
    db.flush()
    replan(db, user.id, "TASK_CANCELLED")
    return {"status": "cancelled"}


@app.get("/api/v1/tasks/{task_id}/sources")
def sources(task_id: str, user=Depends(current_user), db=Depends(session)):
    owned(db, Task, task_id, user)
    raws = db.scalars(select(RawInformation).join(TaskSource, TaskSource.raw_information_id == RawInformation.id).where(TaskSource.task_id == task_id)).all()
    return [inbox_item(db, raw) for raw in raws]


@app.get("/api/v1/events")
def events(user=Depends(current_user), db=Depends(session)):
    return [as_dict(e) for e in db.scalars(select(Event).where(Event.user_id == user.id, Event.status == "active").order_by(Event.start_at)).all()]


@app.post("/api/v1/events", status_code=201)
def create_event(payload: EventInput, user=Depends(current_user), db=Depends(session)):
    event = Event(user_id=user.id, **payload.model_dump())
    db.add(event)
    db.flush()
    replan(db, user.id, "EVENT_CREATED")
    return as_dict(event)


@app.put("/api/v1/events/{event_id}")
def update_event(event_id: str, payload: EventInput, user=Depends(current_user), db=Depends(session)):
    event = owned(db, Event, event_id, user)
    for k, v in payload.model_dump().items():
        setattr(event, k, v)
    db.flush()
    replan(db, user.id, "EVENT_UPDATED")
    return as_dict(event)


@app.delete("/api/v1/events/{event_id}")
def cancel_event(event_id: str, user=Depends(current_user), db=Depends(session)):
    event = owned(db, Event, event_id, user)
    event.status = "cancelled"
    db.flush()
    replan(db, user.id, "EVENT_CANCELLED")
    return {"status": "cancelled"}


@app.post("/api/v1/ingest")
@app.post("/api/v1/ingest/notification")
def receive(payload: IngestInput, user=Depends(current_user), db=Depends(session)):
    # Canvas structured fields are accepted only from the trusted server connector.
    if payload.platform == "canvas" or payload.source_type in ("assignment", "announcement"):
        raise HTTPException(422, "Canvas 数据请通过连接器同步")
    raw = ingest(db, user.id, payload)
    process(db, raw)
    return inbox_item(db, raw)


@app.get("/api/v1/inbox")
def inbox(user=Depends(current_user), db=Depends(session)):
    return [inbox_item(db, raw) for raw in db.scalars(select(RawInformation).where(RawInformation.user_id == user.id).order_by(RawInformation.received_at.desc()).limit(200)).all()]


@app.post("/api/v1/inbox/{raw_id}/review")
def review(raw_id: str, payload: Review, user=Depends(current_user), db=Depends(session)):
    raw = owned(db, RawInformation, raw_id, user)
    extraction = db.scalar(select(ExtractionResult).where(ExtractionResult.raw_id == raw.id))
    if raw.status != "needs_confirmation" or not extraction:
        raise HTTPException(409, "这条信息已处理，请刷新")
    if not payload.accept:
        raw.status, extraction.status = "ignored", "rejected"
    else:
        from .schemas import AIAction
        decision = payload.decision or AIAction.model_validate(extraction.decision)
        try:
            apply_action(db, raw, decision)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        extraction.decision = decision.model_dump(mode="json", exclude_unset=True)
        extraction.status = "applied"
    return inbox_item(db, raw)


@app.post("/api/v1/inbox/{raw_id}/retry")
def retry(raw_id: str, user=Depends(current_user), db=Depends(session)):
    raw = owned(db, RawInformation, raw_id, user)
    if raw.status != "failed":
        raise HTTPException(409, "仅可重试失败的信息")
    raw.status, raw.error = "queued", None
    process(db, raw)
    return inbox_item(db, raw)


@app.get("/api/v1/schedule")
def schedule(user=Depends(current_user), db=Depends(session)):
    version = db.scalar(select(ScheduleVersion).where(ScheduleVersion.user_id == user.id).order_by(ScheduleVersion.version.desc()))
    blocks = db.scalars(select(ScheduleBlock).where(ScheduleBlock.user_id == user.id, ScheduleBlock.end_at > now() - timedelta(days=30)).order_by(ScheduleBlock.start_at)).all()
    return {"version": version.version if version else 0, "status": version.status if version else "EMPTY", "risks": version.risks if version else [], "blocks": [block_json(b) for b in blocks]}


@app.post("/api/v1/schedule/replan")
def replan_api(user=Depends(current_user), db=Depends(session)):
    return replan(db, user.id)


@app.get("/api/v1/schedule/versions")
def versions(user=Depends(current_user), db=Depends(session)):
    return [as_dict(v) for v in db.scalars(select(ScheduleVersion).where(ScheduleVersion.user_id == user.id).order_by(ScheduleVersion.version.desc()).limit(30)).all()]


class LockInput(BaseModel):
    locked: bool


@app.put("/api/v1/schedule/blocks/{block_id}/lock")
def lock_block(block_id: str, payload: LockInput, user=Depends(current_user), db=Depends(session)):
    block = owned(db, ScheduleBlock, block_id, user)
    block.locked = payload.locked
    db.flush()
    return replan(db, user.id, "BLOCK_LOCK_CHANGED")


@app.get("/api/v1/connectors")
def connectors(user=Depends(current_user), db=Depends(session)):
    return [{"id": c.id, "base_url": c.base_url, "enabled": c.enabled, "last_synced_at": c.last_synced_at, "error": c.error} for c in db.scalars(select(Connector).where(Connector.user_id == user.id)).all()]


@app.post("/api/v1/connectors/canvas", status_code=201)
def connect_canvas(payload: CanvasInput, user=Depends(current_user), db=Depends(session)):
    try:
        origin = public_origin(payload.base_url.strip().rstrip("/"))
    except (ValueError, OSError):
        raise HTTPException(422, "无法验证 Canvas 地址，请填写学校的 HTTPS 公网域名")
    existing = db.scalar(select(Connector).where(Connector.user_id == user.id, Connector.base_url == origin))
    if existing:
        existing.encrypted_token = vault().encrypt(payload.access_token.encode()).decode()
        existing.enabled = True
        existing.error = None
        return {"id": existing.id, "base_url": origin}
    connector = Connector(user_id=user.id, base_url=origin, encrypted_token=vault().encrypt(payload.access_token.encode()).decode())
    db.add(connector)
    db.flush()
    return {"id": connector.id, "base_url": origin}


@app.post("/api/v1/connectors/{connector_id}/sync")
def sync_connector(connector_id: str, user=Depends(current_user), db=Depends(session)):
    connector = owned(db, Connector, connector_id, user)
    return sync(db, connector)


@app.delete("/api/v1/connectors/{connector_id}")
def disconnect(connector_id: str, user=Depends(current_user), db=Depends(session)):
    connector = owned(db, Connector, connector_id, user)
    connector.enabled = False
    connector.encrypted_token = ""
    return {"status": "disconnected"}


@app.get("/api/v1/courses")
def courses(user=Depends(current_user), db=Depends(session)):
    return [as_dict(c) for c in db.scalars(select(Course).where(Course.user_id == user.id)).all()]
