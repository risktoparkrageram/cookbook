import sqlite3
from pathlib import Path

import pytest

from cookbook import db, schema


def test_migrate_creates_every_table_on_an_empty_database(tmp_path: Path) -> None:
    connection = db.connect(tmp_path / "empty.db")

    version = schema.migrate(connection)

    tables = [
        name
        for (name,) in connection.execute(
            "SELECT name FROM sqlite_schema"
            " WHERE type = 'table' AND name NOT LIKE 'recipe_search_%' ORDER BY name"
        )
    ]
    assert version == 1
    assert tables == [
        "images",
        "ingredient_sections",
        "ingredients",
        "recipe_notes",
        "recipe_search",
        "recipe_tags",
        "recipes",
        "sources",
        "steps",
        "tags",
        "users",
    ]


def test_migrate_twice_changes_nothing(database: sqlite3.Connection) -> None:
    database.execute("INSERT INTO sources (publication) VALUES ('Allotment Weekly')")

    assert schema.migrate(database) == 1
    assert database.execute("SELECT count(*) FROM sources").fetchone()[0] == 1


def test_migrate_refuses_a_database_newer_than_the_code(database: sqlite3.Connection) -> None:
    database.execute("PRAGMA user_version = 99")

    with pytest.raises(RuntimeError, match="schema version 99"):
        schema.migrate(database)


def test_connect_enables_foreign_keys_and_wal(database: sqlite3.Connection) -> None:
    assert database.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert database.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
