import sqlite3
from pathlib import Path

from cookbook import schema

BUSY_TIMEOUT_MS = 5000


def connect(path: Path | str) -> sqlite3.Connection:
    """
    Open the cookbook database with the settings every reader and writer relies on.

    WAL lets the web app read while an import writes; foreign keys are off by default in
    SQLite and the schema's cascades depend on them. The web app opens one connection per
    request but may run the request's dependency and handler on different threads, so
    sqlite3's same-thread check is off; a connection is still never shared between requests.
    """
    connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def require_current_schema(connection: sqlite3.Connection, migrate: bool) -> None:
    """
    Stop the app from starting on a database whose schema version differs from the code's.

    With migrate set, pending migrations are applied first.
    """
    if migrate:
        schema.migrate(connection)
    version = schema.current_version(connection)
    if version != schema.latest_version():
        raise RuntimeError(
            f"database is at schema version {version}, this code expects"
            f" {schema.latest_version()}; run the migrations or set COOKBOOK_MIGRATE=1"
        )
