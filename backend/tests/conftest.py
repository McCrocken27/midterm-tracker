"""Every test gets its own empty database, and no test calls the real model."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
os.environ.setdefault("PORTKEY_API_KEY", "test-key-not-real")


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    import config
    import db
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    import main
    main.ask_per_user.events.clear(); main.ask_per_ip.events.clear(); main.signups_per_ip.events.clear()
    with TestClient(main.app) as c:
        yield c
