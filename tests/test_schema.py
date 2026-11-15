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
    assert version == 2
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

    assert schema.migrate(database) == 2
    assert database.execute("SELECT count(*) FROM sources").fetchone()[0] == 1


def test_migrate_refuses_a_database_newer_than_the_code(database: sqlite3.Connection) -> None:
    database.execute("PRAGMA user_version = 99")

    with pytest.raises(RuntimeError, match="schema version 99"):
        schema.migrate(database)


def test_tags_accept_exactly_the_python_tag_kinds(database: sqlite3.Connection) -> None:
    database.executemany(
        "INSERT INTO tags (name, kind) VALUES (?, ?)", [(kind, kind) for kind in schema.TAG_KINDS]
    )

    with pytest.raises(sqlite3.IntegrityError):
        database.execute("INSERT INTO tags (name, kind) VALUES ('beef', 'protein')")
    assert schema.TAG_KINDS == ("cuisine", "ingredient", "diet", "course", "style", "technique")


def test_the_database_holds_a_single_account(database: sqlite3.Connection) -> None:
    """A second account is refused; the one account can still change email and password."""
    database.execute("INSERT INTO users (email, password_hash) VALUES ('cook@example.com', 'a')")

    with pytest.raises(sqlite3.IntegrityError, match="single account"):
        database.execute(
            "INSERT INTO users (email, password_hash) VALUES ('other@example.com', 'b')"
        )
    database.execute("UPDATE users SET email = 'chef@example.com', password_hash = 'c'")

    rows = database.execute("SELECT email, password_hash FROM users").fetchall()
    assert [tuple(row) for row in rows] == [("chef@example.com", "c")]


def test_connect_enables_foreign_keys_and_wal(database: sqlite3.Connection) -> None:
    assert database.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert database.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
