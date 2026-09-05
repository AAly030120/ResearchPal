"""Pytest configuration for ResearchPal backend tests.

Sets a safe, isolated environment BEFORE the application modules are imported,
so that `app.core.config.settings` picks up test values (dev mode, temp DB).
"""
import os
import sys

# Make the backend package importable (so `from app...` works in tests)
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

# Must be set before importing `app` so the module-level `settings` singleton
# is built with test values.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_researchpal.db")
os.environ.setdefault("CORS_ORIGINS", "*")

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """Fresh TestClient with the app's lifespan (DB tables) initialized."""
    with TestClient(app) as c:
        yield c
