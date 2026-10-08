import os
os.environ["AUTO_CREATE_TABLES"] = "0"
os.environ["CANVAS_POLL"] = "0"
os.environ["SECRET_KEY"] = "test-only-secret-do-not-use-outside-tests-12345"
os.environ.pop("LLM_API_KEY", None)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base
from app.main import app, session


@pytest.fixture
def env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        def override():
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
        app.dependency_overrides[session] = override
        with TestClient(app) as client:
            yield client, db
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def account(env):
    client, db = env
    result = client.post("/api/v1/auth/register", json={"username": "alice", "password": "test-password-123"})
    assert result.status_code == 201
    headers = {"Authorization": "Bearer " + result.json()["access_token"]}
    return client, db, headers
