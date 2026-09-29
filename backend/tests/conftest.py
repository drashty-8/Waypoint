import importlib
import os
import pkgutil
from collections import defaultdict
from unittest.mock import MagicMock

import pytest

# database.py and claude_client.py read these when they're imported. Set
# fake values first so the tests never need a real .env, connect to a real
# Supabase project, or make a billed Claude call.
# (load_dotenv doesn't overwrite variables that are already set.)
os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_SECRET_KEY"] = "sb_secret_fake_for_tests"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-fake-for-tests"

from fastapi.testclient import TestClient  # noqa: E402

import claude_client  # noqa: E402
import routers  # noqa: E402
import tagging  # noqa: E402
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
    """Swap the real Supabase client for a FakeSupabase in tagging.py and every router.

    Each of those modules does `from database import supabase`, which gives
    it its own reference to the client, so each one has to be patched
    separately. This finds every module in routers/ automatically, so new
    routers (e.g. routers/query.py) are covered without changing this.
    """
    fake = FakeSupabase()

    modules = [tagging]
    for module_info in pkgutil.iter_modules(routers.__path__):
        modules.append(importlib.import_module(f"routers.{module_info.name}"))

    for module in modules:
        if hasattr(module, "supabase"):
            monkeypatch.setattr(module, "supabase", fake.client)

    return fake


@pytest.fixture
def fake_claude(monkeypatch):
    """Swap the real Claude client for a MagicMock, so tests never make billed calls.

    Set up what Claude "returns" on the fake, e.g.:

        fake_claude.messages.create.return_value = <a fake response>
        fake_claude.messages.create.side_effect = Exception("API down")

    Any module that does `from claude_client import client` has its own
    reference to the client, so like fake_supabase this patches each one.
    It checks tagging.py and every module in routers/, and only patches a
    `client` that really is the Claude client, since "client" is a common
    name. claude_client.client itself is patched too, for code that does
    `import claude_client`.
    """
    fake = MagicMock()
    real_client = claude_client.client

    modules = [tagging]
    for module_info in pkgutil.iter_modules(routers.__path__):
        modules.append(importlib.import_module(f"routers.{module_info.name}"))

    for module in modules:
        if getattr(module, "client", None) is real_client:
            monkeypatch.setattr(module, "client", fake)

    monkeypatch.setattr(claude_client, "client", fake)

    return fake


@pytest.fixture
def client():
    """A test client that sends requests to the app without starting a server."""
    return TestClient(app)
