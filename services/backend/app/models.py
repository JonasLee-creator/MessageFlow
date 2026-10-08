from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, UTCDateTime, now, uid


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")


class Connector(Base):
    __tablename__ = "connectors"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    base_url: Mapped[str] = mapped_column(Text)
    encrypted_token: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at = mapped_column(UTCDateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text)


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("user_id", "connector_id", "external_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    connector_id: Mapped[str] = mapped_column(ForeignKey("connectors.id"))
    external_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(512))


class RawInformation(Base):
    __tablename__ = "raw_information"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    source_type: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str | None] = mapped_column(String(512))
    channel_name: Mapped[str] = mapped_column(String(512), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text)
    structured_data: Mapped[dict] = mapped_column(JSON, default=dict)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    source_updated_at = mapped_column(UTCDateTime, default=now)
    received_at = mapped_column(UTCDateTime, default=now)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    error: Mapped[str | None] = mapped_column(Text)


class ExtractionResult(Base):
    __tablename__ = "extraction_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    raw_id: Mapped[str] = mapped_column(ForeignKey("raw_information.id"), unique=True)
    decision: Mapped[dict] = mapped_column(JSON)
    engine: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(32), default="pending")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(512))
    course: Mapped[str] = mapped_column(String(512), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    deadline = mapped_column(UTCDateTime, nullable=True)
    estimated_duration: Mapped[int] = mapped_column(Integer, default=60)
    remaining_duration: Mapped[int] = mapped_column(Integer, default=60)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    splittable: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    deadline_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at = mapped_column(UTCDateTime, default=now)
    updated_at = mapped_column(UTCDateTime, default=now, onupdate=now)


class TaskSource(Base):
    __tablename__ = "task_sources"
    __table_args__ = (UniqueConstraint("task_id", "raw_information_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    raw_information_id: Mapped[str] = mapped_column(ForeignKey("raw_information.id"))
    relation: Mapped[str] = mapped_column(String(32))


class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(512))
    start_at = mapped_column(UTCDateTime)
    end_at = mapped_column(UTCDateTime)
    event_type: Mapped[str] = mapped_column(String(32), default="course")
    status: Mapped[str] = mapped_column(String(32), default="active")
    source_raw_id: Mapped[str | None] = mapped_column(ForeignKey("raw_information.id"))


class ScheduleBlock(Base):
    __tablename__ = "schedule_blocks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    start_at = mapped_column(UTCDateTime)
    end_at = mapped_column(UTCDateTime)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer)


class ScheduleVersion(Base):
    __tablename__ = "schedule_versions"
    __table_args__ = (UniqueConstraint("user_id", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32))
    risks: Mapped[list] = mapped_column(JSON, default=list)
    snapshot: Mapped[list] = mapped_column(JSON, default=list)
    created_at = mapped_column(UTCDateTime, default=now)
