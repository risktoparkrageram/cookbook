import sqlite3

import pytest
from pytest_cases import case, parametrize_with_cases

from cookbook import search
from cookbook.search import SearchFilters

# what someone typed, the FTS5 expression it becomes
type ExpressionCase = tuple[str, str | None]
# the search, the slugs it finds in order
type FindCase = tuple[SearchFilters, list[str]]


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
        INSERT INTO steps (recipe_id, position, title, text) VALUES
            (7, 2, 'Simmer', 'Simmer for 20 minutes.'),
            (7, 1, 'Rinse', 'Rinse the lentils.');
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
        "steps": "Rinse\nRinse the lentils.\nSimmer\nSimmer for 20 minutes.",
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


@case(tags="expression")
def case_words_are_quoted_and_the_last_is_a_prefix() -> ExpressionCase:
    return "spring onion", '"spring" "onion"*'


@case(tags="expression")
def case_a_trailing_space_ends_the_prefix() -> ExpressionCase:
    return "onion ", '"onion"'


@case(tags="expression")
def case_a_closed_phrase_stays_whole() -> ExpressionCase:
    return '"spring onion"', '"spring onion"'


@case(tags="expression")
def case_an_unclosed_phrase_is_a_prefix() -> ExpressionCase:
    return 'lime "spring on', '"lime" "spring on"*'


@case(tags="expression")
def case_operators_are_plain_words() -> ExpressionCase:
    return "salt OR NOT pepper", '"salt" "OR" "NOT" "pepper"*'


@case(tags="expression")
def case_fts_syntax_is_quoted() -> ExpressionCase:
    return "title:soup NEAR(a b) ^x", '"title:soup" "NEAR(a" "b)" "^x"*'


@case(tags="expression")
def case_quotes_inside_a_word_are_doubled() -> ExpressionCase:
    return 'say"cheese', '"say""cheese"*'


@case(tags="expression")
def case_punctuation_alone_is_dropped() -> ExpressionCase:
    return '- * " ( ', None


@case(tags="expression")
def case_nothing_typed() -> ExpressionCase:
    return "", None


@parametrize_with_cases("text, expected", cases=".", has_tag="expression")
def test_match_expression(text: str, expected: str | None) -> None:
    assert search.match_expression(text) == expected


@pytest.mark.parametrize(
    "text", ['"', '""', 'a"b"c', "*", "tofu*", "(tofu", "tofu)", "NOT", "-tofu", "tofu:", "'"]
)
def test_awkward_input_never_breaks_the_query(recipes: sqlite3.Connection, text: str) -> None:
    """Whatever is typed, FTS5 gets a valid expression: no OperationalError."""
    search.find(recipes, SearchFilters(q=text))


@case(tags="find")
def case_find_everything_not_archived_by_title() -> FindCase:
    return SearchFilters(), ["almond_biscuits", "chilli_oil_noodles", "tofu_rice_bowl"]


@case(tags="find")
def case_find_ranks_title_and_tags_above_a_step() -> FindCase:
    return SearchFilters(q="tofu"), ["tofu_rice_bowl", "chilli_oil_noodles"]


@case(tags="find")
def case_find_by_prefix_of_the_last_word() -> FindCase:
    return SearchFilters(q="noodl"), ["chilli_oil_noodles"]


@case(tags="find")
def case_find_terms_are_anded() -> FindCase:
    return SearchFilters(q="tofu golden"), ["tofu_rice_bowl"]


@case(tags="find")
def case_find_in_notes() -> FindCase:
    return SearchFilters(q="cast iron"), ["tofu_rice_bowl"]


@case(tags="find")
def case_find_query_sorted_by_title() -> FindCase:
    return SearchFilters(q="tofu", sort="title"), ["chilli_oil_noodles", "tofu_rice_bowl"]


@case(tags="find")
def case_find_archived_only_when_asked() -> FindCase:
    return SearchFilters(q="turnip", archived=True), ["old_turnip_stew"]


@case(tags="find")
def case_find_archived_hidden_by_default() -> FindCase:
    return SearchFilters(q="turnip"), []


@case(tags="find")
def case_find_by_one_tag() -> FindCase:
    return SearchFilters(tag=["asian"]), ["chilli_oil_noodles", "tofu_rice_bowl"]


@case(tags="find")
def case_find_tags_are_anded() -> FindCase:
    return SearchFilters(tag=["asian", "korean"]), ["tofu_rice_bowl"]


@case(tags="find")
def case_find_tags_from_different_recipes_find_nothing() -> FindCase:
    return SearchFilters(tag=["korean", "quick"]), []


@case(tags="find")
def case_find_query_and_tag_together() -> FindCase:
    return SearchFilters(q="tofu", tag=["quick"]), ["chilli_oil_noodles"]


@case(tags="find")
def case_find_by_publication() -> FindCase:
    return SearchFilters(publication="Allotment Weekly"), ["chilli_oil_noodles", "tofu_rice_bowl"]


@case(tags="find")
def case_find_by_author() -> FindCase:
    return SearchFilters(author="Ada Example"), ["tofu_rice_bowl"]


@case(tags="find")
def case_find_by_ingredient_not_step_text() -> FindCase:
    return SearchFilters(ingredient="TOFU"), ["tofu_rice_bowl"]


@case(tags="find")
def case_find_ingredient_wildcards_are_literal() -> FindCase:
    return SearchFilters(ingredient="%"), []


@case(tags="find")
def case_find_total_time_limit_includes_the_bound() -> FindCase:
    return SearchFilters(max_total=32), ["almond_biscuits", "chilli_oil_noodles"]


@case(tags="find")
def case_find_by_hands_on_time() -> FindCase:
    return SearchFilters(max_prep=10), ["chilli_oil_noodles"]


@case(tags="find")
def case_find_serves_from_overlaps_the_range() -> FindCase:
    return SearchFilters(serves_from=3), ["almond_biscuits", "tofu_rice_bowl"]


@case(tags="find")
def case_find_serves_to_overlaps_the_range() -> FindCase:
    return SearchFilters(serves_to=2), ["chilli_oil_noodles", "tofu_rice_bowl"]


@case(tags="find")
def case_find_with_notes() -> FindCase:
    return SearchFilters(has_notes=True), ["almond_biscuits", "tofu_rice_bowl"]


@case(tags="find")
def case_find_quickest_first_untimed_last() -> FindCase:
    return SearchFilters(sort="time", archived=True), [
        "chilli_oil_noodles",
        "almond_biscuits",
        "tofu_rice_bowl",
        "old_turnip_stew",
    ]


@case(tags="find")
def case_find_most_recently_edited_note_first() -> FindCase:
    return SearchFilters(sort="noted"), ["almond_biscuits", "tofu_rice_bowl", "chilli_oil_noodles"]


@case(tags="find")
def case_find_cooked() -> FindCase:
    return SearchFilters(cooked="yes"), ["almond_biscuits"]


@case(tags="find")
def case_find_not_cooked_yet() -> FindCase:
    return SearchFilters(cooked="no"), ["chilli_oil_noodles", "tofu_rice_bowl"]


@parametrize_with_cases("filters, slugs", cases=".", has_tag="find")
def test_find(recipes: sqlite3.Connection, filters: SearchFilters, slugs: list[str]) -> None:
    found = search.find(recipes, filters)

    slug_by_id = dict(recipes.execute("SELECT id, slug FROM recipes").fetchall())
    assert [slug_by_id[recipe_id] for recipe_id in found] == slugs
