import importlib
import os
import pkgutil
from collections import defaultdict
from unittest.mock import MagicMock

import pytest

# database.py reads these when it's imported. Set fake values first so
# the tests never need a real .env or connect to a real Supabase project.
# (load_dotenv doesn't overwrite variables that are already set.)
os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_SECRET_KEY"] = "sb_secret_fake_for_tests"

from fastapi.testclient import TestClient  # noqa: E402

import routers  # noqa: E402
from main import app  # noqa: E402


class FakeSupabase:
    """A stand-in for the Supabase client that records every call.

    Each table and Storage bucket gets its own MagicMock, created the
    first time it's used, so a test can set up just the tables it cares
    about:

        fake_supabase.tables["photos"].insert.return_value.execute.return_value.data = [...]
        fake_supabase.buckets["photos"].upload.side_effect = Exception("down")
    """

    def __init__(self):
        self.client = MagicMock()
        self.tables = defaultdict(MagicMock)
        self.buckets = defaultdict(MagicMock)

        self.client.table.side_effect = lambda name: self.tables[name]
        self.client.storage.from_.side_effect = lambda name: self.buckets[name]


@pytest.fixture
def fake_supabase(monkeypatch):
    """Swap the real Supabase client for a FakeSupabase in every router.

    Each router does `from database import supabase`, which gives it its
    own reference to the client, so each router module has to be patched
    separately. This finds every module in routers/ automatically, so new
    routers (e.g. routers/query.py) are covered without changing this.
    """
    fake = FakeSupabase()

    for module_info in pkgutil.iter_modules(routers.__path__):
        module = importlib.import_module(f"routers.{module_info.name}")
        if hasattr(module, "supabase"):
            monkeypatch.setattr(module, "supabase", fake.client)

    return fake


@pytest.fixture
def client():
    """A test client that sends requests to the app without starting a server."""
    return TestClient(app)
