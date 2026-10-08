import os
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, DateTime
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Timestamp must include timezone")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value else None


class Base(DeclarativeBase):
    pass


url = os.getenv("DATABASE_URL", "sqlite:///./chronoflow.db")
engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)
