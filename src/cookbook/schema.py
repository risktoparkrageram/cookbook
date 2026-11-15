import sqlite3
from importlib import resources

MIGRATIONS_PACKAGE = "cookbook.migrations"


def migration_scripts() -> list[tuple[int, str]]:
    """
    Return every migration as (version, SQL), in version order.

    A migration file is named NNNN_description.sql; NNNN is the user_version the
    database has once that file has been applied.
    """
    scripts = []
    for entry in resources.files(MIGRATIONS_PACKAGE).iterdir():
        if entry.name.endswith(".sql"):
            scripts.append((int(entry.name.split("_", 1)[0]), entry.read_text(encoding="utf-8")))
    scripts.sort()
    versions = [version for version, _ in scripts]
    if versions != list(range(1, len(scripts) + 1)):
        raise RuntimeError(f"migration versions must run 1..n without gaps, found {versions}")
    return scripts


def latest_version() -> int:
    return len(migration_scripts())


def current_version(connection: sqlite3.Connection) -> int:
    version: int = connection.execute("PRAGMA user_version").fetchone()[0]
    return version


def migrate(connection: sqlite3.Connection) -> int:
    """
    Apply every migration newer than the database's user_version and return the new version.

    Each migration and its user_version bump run between one BEGIN and COMMIT, so a failure
    leaves the database at the last fully applied version.
    """
    version = current_version(connection)
    latest = latest_version()
    if version > latest:
        raise RuntimeError(
            f"database is at schema version {version}, newer than this code ({latest})"
        )
    for script_version, sql in migration_scripts():
        if script_version <= version:
            continue
        connection.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {script_version};\nCOMMIT;")
    return current_version(connection)
