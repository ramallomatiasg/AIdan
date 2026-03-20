"""Shared fixtures for AIdan test suite."""
import os
import sys
import sqlite3
import pytest
from unittest.mock import MagicMock

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def mock_logger():
    """Provide a mock logger matching AIdan's logging interface."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    logger.warning = MagicMock()
    logger.debug = MagicMock()
    return logger


@pytest.fixture
def in_memory_db(tmp_path, monkeypatch):
    """Provide an in-memory SQLite DB by patching DB_PATH to a temp file.

    Returns the temp DB path so tests can connect to the same file.
    """
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("src.common.db.DB_PATH", db_path)

    # Also patch os.makedirs to avoid 'state/' creation
    original_makedirs = os.makedirs
    def safe_makedirs(path, exist_ok=False):
        if path == "state":
            original_makedirs(str(tmp_path), exist_ok=True)
        else:
            original_makedirs(path, exist_ok=True)
    monkeypatch.setattr("os.makedirs", safe_makedirs)

    # Initialize tables
    from src.common.db import init_db
    init_db()

    return db_path
