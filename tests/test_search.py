import sqlite3

import pytest

from cookbook import search


@pytest.fixture
def soup_id(database: sqlite3.Connection) -> int:
    database.executescript(
        """
        INSERT INTO sources (id, publication, author) VALUES (1, 'Allotment Weekly', 'Ada Example');
        INSERT INTO recipes (id, slug, title, source_id)
            VALUES (7, 'lentil_soup', 'Lentil Soup', 1);
        INSERT INTO ingredient_sections (id, recipe_id, position, name) VALUES
            (1, 7, 1, NULL),
            (2, 7, 2, 'To serve');
        INSERT INTO ingredients (section_id, position, quantity, item) VALUES
            (1, 2, '1 l', 'vegetable stock'),
            (1, 1, '200 g', 'red lentils'),
            (2, 1, '', 'crème fraîche');
        INSERT INTO steps (recipe_id, position, text) VALUES
            (7, 2, 'Simmer for 20 minutes.'),
            (7, 1, 'Rinse the lentils.');
        INSERT INTO tags (id, name) VALUES (1, 'vegetarian'), (2, 'quick');
        INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (7, 1), (7, 2);
        """
    )
    return 7


def test_refresh_writes_every_column_in_recipe_order(
    database: sqlite3.Connection, soup_id: int
) -> None:
    """Rows are inserted out of order, so a missing ORDER BY changes the expected text."""
    database.execute("INSERT INTO recipe_notes (recipe_id, body) VALUES (7, 'Add extra chilli')")

    search.refresh(database, soup_id)

    row = database.execute(
        "SELECT slug, title, source, ingredients, steps, tags, notes FROM recipe_search"
        " WHERE rowid = ?",
        (soup_id,),
    ).fetchone()
    assert dict(row) == {
        "slug": "lentil_soup",
        "title": "Lentil Soup",
        "source": "Allotment Weekly Ada Example",
        "ingredients": "200 g red lentils\n1 l vegetable stock\nTo serve\ncrème fraîche",
        "steps": "Rinse the lentils.\nSimmer for 20 minutes.",
        "tags": "quick vegetarian",
        "notes": "Add extra chilli",
    }


def test_refresh_replaces_the_previous_row(database: sqlite3.Connection, soup_id: int) -> None:
    search.refresh(database, soup_id)
    database.execute("UPDATE recipes SET title = 'Red Lentil Soup' WHERE id = 7")

    search.refresh(database, soup_id)

    titles = [title for (title,) in database.execute("SELECT title FROM recipe_search")]
    assert titles == ["Red Lentil Soup"]


def test_note_triggers_keep_the_notes_column_current(
    database: sqlite3.Connection, soup_id: int
) -> None:
    """The triggers and search.refresh must produce the same notes text."""
    search.refresh(database, soup_id)
    notes_query = "SELECT notes FROM recipe_search WHERE rowid = 7"

    database.execute("INSERT INTO recipe_notes (id, recipe_id, body) VALUES (1, 7, 'More lemon')")
    database.execute("INSERT INTO recipe_notes (id, recipe_id, body) VALUES (2, 7, 'Freezes well')")
    after_insert = database.execute(notes_query).fetchone()[0]
    database.execute("UPDATE recipe_notes SET body = 'Much more lemon' WHERE id = 1")
    after_update = database.execute(notes_query).fetchone()[0]
    database.execute("DELETE FROM recipe_notes WHERE id = 2")
    after_delete = database.execute(notes_query).fetchone()[0]
    search.refresh(database, soup_id)
    after_refresh = database.execute(notes_query).fetchone()[0]

    assert after_insert == "More lemon\nFreezes well"
    assert after_update == "Much more lemon\nFreezes well"
    assert after_delete == "Much more lemon"
    assert after_refresh == "Much more lemon"


def test_deleting_a_recipe_removes_its_search_row(
    database: sqlite3.Connection, soup_id: int
) -> None:
    search.refresh(database, soup_id)

    database.execute("DELETE FROM recipes WHERE id = 7")

    assert database.execute("SELECT count(*) FROM recipe_search").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("query", "slugs"),
    [
        ("cumin", ["lentil_soup"]),
        ("creme", ["lentil_soup"]),
        ("ada", ["lentil_soup"]),
        ("chickpea", []),
    ],
)
def test_search_matches_notes_sources_and_ignores_accents(
    database: sqlite3.Connection, soup_id: int, query: str, slugs: list[str]
) -> None:
    search.refresh(database, soup_id)
    database.execute("INSERT INTO recipe_notes (recipe_id, body) VALUES (7, 'Double the cumin')")

    found = database.execute(
        "SELECT slug FROM recipe_search WHERE recipe_search MATCH ?", (query,)
    ).fetchall()

    assert [slug for (slug,) in found] == slugs
