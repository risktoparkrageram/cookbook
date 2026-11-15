import sqlite3
from pathlib import Path

BUSY_TIMEOUT_MS = 5000


def connect(path: Path | str) -> sqlite3.Connection:
    """
    Open the cookbook database with the settings every reader and writer relies on.

    WAL lets the web app read while an import writes; foreign keys are off by default in
    SQLite and the schema's cascades depend on them.
    """
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection
