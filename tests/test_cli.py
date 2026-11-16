import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cookbook import db, schema
from cookbook.cli import back_up_database, main, migrate_database


def test_migrate_backs_up_first_then_brings_an_old_database_up_to_date(tmp_path: Path) -> None:
    """A database made by the first migration only, as recipe-db's copy is, with a recipe."""
    path = tmp_path / "recipes.db"
    connection = sqlite3.connect(path)
    (_, first_migration) = schema.migration_scripts()[0]
    connection.executescript(f"BEGIN;\n{first_migration}\nPRAGMA user_version = 1;\nCOMMIT;")
    connection.execute("INSERT INTO recipes (slug, title) VALUES ('dal', 'Dal')")
    connection.commit()
    connection.close()

    versions = migrate_database(path)

    migrated = db.connect(path)
    backup = sqlite3.connect(tmp_path / "recipes.db.bak")
    assert versions == (1, 3)
    assert schema.current_version(migrated) == 3
    assert [tuple(row) for row in migrated.execute("SELECT slug FROM recipes")] == [("dal",)]
    assert backup.execute("PRAGMA user_version").fetchone() == (1,)
    assert backup.execute("SELECT slug FROM recipes").fetchall() == [("dal",)]


def test_migrate_refuses_a_path_without_a_database(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no database at"):
        migrate_database(tmp_path / "typo.db")

    assert list(tmp_path.iterdir()) == []


def test_backup_adds_a_checked_copy_and_keeps_only_the_newest(
    database: sqlite3.Connection, database_path: Path, tmp_path: Path
) -> None:
    """Older backups beyond keep go; files that aren't backups are left alone."""
    database.execute("INSERT INTO recipes (slug, title) VALUES ('dal', 'Dal')")
    backups = tmp_path / "backups"
    backups.mkdir()
    for name in [
        "recipes-20261113T033000Z.db",
        "recipes-20261114T033000Z.db",
        "recipes-20261115T033000Z.db",
        "notes.txt",
    ]:
        (backups / name).write_bytes(b"older")

    target = back_up_database(
        database_path, backups, keep=2, now=datetime(2026, 11, 16, 3, 30, tzinfo=UTC)
    )

    assert target == backups / "recipes-20261116T033000Z.db"
    assert sorted(path.name for path in backups.iterdir()) == [
        "notes.txt",
        "recipes-20261115T033000Z.db",
        "recipes-20261116T033000Z.db",
    ]
    copy = sqlite3.connect(target)
    assert copy.execute("SELECT slug FROM recipes").fetchall() == [("dal",)]


def test_backup_writes_nothing_when_the_backup_directory_is_missing(
    database: sqlite3.Connection, database_path: Path, tmp_path: Path
) -> None:
    """An unmounted backup disk leaves no directory: nothing may land on the disk below."""
    with pytest.raises(FileNotFoundError, match="no backup directory at"):
        back_up_database(
            database_path, tmp_path / "unmounted" / "backups", keep=30, now=datetime.now(UTC)
        )

    assert not (tmp_path / "unmounted").exists()


def test_command_line_reports_errors_on_stderr_with_status_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["migrate", "--db", str(tmp_path / "typo.db")])

    assert exit_info.value.code == 1
    assert capsys.readouterr().err == f"cookbook: no database at {tmp_path / 'typo.db'}\n"
