"""Security & robustness regression tests for ResearchPal.

These encode the "抗打" hardening applied after studying open-source peers
(open-webui, paper-qa, RAGFlow, AnythingLLM) so regressions are caught in CI.
"""
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import Settings


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _token_for(client: TestClient, email: str, password: str = "test1234") -> str:
    """Register (or log in) a user and return a JWT."""
    reg = client.post(
        "/api/auth/register",
        json={"email": email, "username": email.split("@")[0], "password": password},
    )
    if reg.status_code == 400:  # already registered
        login = client.post("/api/auth/login", json={"email": email, "password": password})
    else:
        login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


# --------------------------------------------------------------------------- #
# 1. Download endpoint: authentication + ownership + path-traversal
# --------------------------------------------------------------------------- #
def test_download_requires_authentication(client: TestClient):
    """Unauthenticated download must be rejected (no enumeration of task files)."""
    r = client.get("/api/tasks/does-not-exist/download")
    assert r.status_code == 401


def test_download_blocks_path_traversal(client: TestClient):
    """A task pointing outside the working dir must be rejected, not served."""
    from app.models.database import SessionLocal, engine, Base
    from app.models import Task
    from app.models.user import User

    Base.metadata.create_all(bind=engine)
    token = _token_for(client, "traversal@test.com")

    db = SessionLocal()
    user = db.query(User).filter(User.email == "traversal@test.com").first()
    db.add(Task(id="evil", user_id=user.id, task_type="ppt", status="done",
                result_path="../../../../etc/passwd"))
    db.commit()
    db.close()

    r = client.get(
        "/api/tasks/evil/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Either 400 (path traversal guard) or 404 (file not found) — never 200 serving /etc/passwd
    assert r.status_code in (400, 404)
    assert r.status_code != 200

    db = SessionLocal()
    db.query(Task).filter(Task.id == "evil").delete()
    db.commit()
    db.close()


def test_download_enforces_ownership(client: TestClient):
    """One user must not be able to download another user's task artifact."""
    from app.models.database import SessionLocal, engine, Base
    from app.models import Task
    from app.models.user import User

    Base.metadata.create_all(bind=engine)
    owner = _token_for(client, "owner@test.com")
    intruder = _token_for(client, "intruder@test.com")

    db = SessionLocal()
    owner_user = db.query(User).filter(User.email == "owner@test.com").first()
    db.add(Task(id="owned", user_id=owner_user.id, task_type="ppt", status="done",
                result_path="outputs/owned.pptx"))
    db.commit()
    db.close()

    # Intruder tries to fetch owner's task
    r = client.get(
        "/api/tasks/owned/download",
        headers={"Authorization": f"Bearer {intruder}"},
    )
    assert r.status_code in (403, 404)  # 403 preferred; 404 also safe

    db = SessionLocal()
    db.query(Task).filter(Task.id == "owned").delete()
    db.commit()
    db.close()


# --------------------------------------------------------------------------- #
# 2. Sandbox must never leak server secrets into the subprocess
# --------------------------------------------------------------------------- #
def test_sandbox_strips_server_secrets():
    from app.services.sandbox import run_python

    code = (
        "import os, json\n"
        "print(json.dumps({"
        "'has_secret': 'SECRET_KEY' in os.environ, "
        "'has_db': 'DATABASE_URL' in os.environ, "
        "'has_openai': 'OPENAI_API_KEY' in os.environ"
        "}))"
    )
    res = run_python(code=code)
    assert res["error"] is None, res.get("error")
    assert '"has_secret": false' in res["stdout"].lower()
    assert '"has_db": false' in res["stdout"].lower()


# --------------------------------------------------------------------------- #
# 3. Production configuration must refuse to start without a real SECRET_KEY
# --------------------------------------------------------------------------- #
def test_production_requires_strong_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DEBUG", "false")
    # With no SECRET_KEY and production mode, the app must refuse to start.
    with pytest.raises(ValueError):
        Settings()


def test_dev_allows_empty_secret_key(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("SECRET_KEY", "")
    # Should NOT raise in dev mode
    s = Settings()
    assert s.SECRET_KEY == ""
