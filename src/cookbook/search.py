import json
import re
import sqlite3
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

type Sort = Literal["relevance", "title", "time", "noted"]


def blank_to_none(value: object) -> object:
    """
    Read an empty form field as not given.

    A form sends every field, empty or not, and the value arrives before pydantic has
    checked its type, hence object.
    """
    return None if value == "" else value


type OptionalText = Annotated[str | None, BeforeValidator(blank_to_none)]
type OptionalCount = Annotated[Annotated[int, Field(ge=0)] | None, BeforeValidator(blank_to_none)]


class SearchFilters(BaseModel):
    """
    A search as it appears in the query string of the home page.

    Every tag must be on a recipe. Time and serves limits include their bounds; a recipe
    without the time or serves never matches a limit on it. sort defaults to relevance when
    there is a query, else title.
    """

    model_config = ConfigDict(frozen=True)

    q: str = Field(default="", max_length=200)
    tag: list[str] = []
    publication: OptionalText = None
    author: OptionalText = None
    source: OptionalCount = None
    ingredient: OptionalText = None
    max_total: OptionalCount = None
    max_prep: OptionalCount = None
    serves_from: OptionalCount = None
    serves_to: OptionalCount = None
    has_notes: bool = False
    archived: bool = False
    sort: Annotated[Sort | None, BeforeValidator(blank_to_none)] = None

    def filter_count(self) -> int:
        """Count the filters set besides the query and sort, for the Filters button."""
        values = [
            self.publication,
            self.author,
            self.source,
            self.ingredient,
            self.max_total,
            self.max_prep,
            self.serves_from,
            self.serves_to,
        ]
        flags = [self.has_notes, self.archived]
        return len(self.tag) + sum(value is not None for value in values) + sum(flags)


QUERY_TERM = re.compile(r'"(?P<phrase>[^"]*)(?P<closed>"?)|(?P<word>\S+)')

# bm25 takes one weight per column: slug (unindexed), title, source, ingredients, steps,
# tags, notes. A word in the title or tags says more about a recipe than one in a step.
RANK = "bm25(recipe_search, 0, 10, 3, 4, 1, 6, 2)"
ORDER_BY: dict[Sort, str] = {
    "relevance": "hits.rank, recipes.title COLLATE NOCASE",
    "title": "recipes.title COLLATE NOCASE",
    "time": "recipes.total_min IS NULL, recipes.total_min, recipes.title COLLATE NOCASE",
    "noted": """(SELECT max(updated_at) FROM recipe_notes WHERE recipe_id = recipes.id)
                 DESC NULLS LAST, recipes.title COLLATE NOCASE""",
}


def match_expression(text: str) -> str | None:
    """
    Turn what someone typed into an FTS5 query, or None when nothing searchable is left.

    Every word and "quoted phrase" becomes a quoted FTS5 string, so FTS5 operators and
    punctuation are only ever text; FTS5 ANDs them. The last word, or an unclosed phrase,
    matches as a prefix because it may still be being typed, unless the text ends in a space.
    Terms without a letter or digit are dropped: FTS5 has nothing to match them against.
    """
    terms: list[str] = []
    open_ended = False
    for match in QUERY_TERM.finditer(text):
        term = match["word"] if match["word"] is not None else match["phrase"]
        if not any(character.isalnum() for character in term):
            continue
        terms.append('"' + term.replace('"', '""') + '"')
        open_ended = match["word"] is not None or not match["closed"]
    if not terms:
        return None
    if open_ended and not text[-1].isspace():
        terms[-1] += "*"
    return " ".join(terms)


def find(connection: sqlite3.Connection, filters: SearchFilters) -> list[int]:
    """Return the ids of the recipes that match a search, in the order it asks for."""
    match = match_expression(filters.q)
    sort = filters.sort or ("relevance" if match else "title")
    if sort == "relevance" and match is None:
        sort = "title"
    hits = (
        f"""JOIN (SELECT rowid, {RANK} AS rank FROM recipe_search
                  WHERE recipe_search MATCH :match) AS hits ON hits.rowid = recipes.id"""
        if match
        else ""
    )
    ingredient = re.sub(r"([\\%_])", r"\\\1", filters.ingredient) if filters.ingredient else None
    rows = connection.execute(
        f"""
        SELECT recipes.id FROM recipes
        {hits}
        LEFT JOIN sources ON sources.id = recipes.source_id
        WHERE (:archived OR NOT recipes.archived)
          AND (SELECT count(DISTINCT tags.name) FROM recipe_tags
               JOIN tags ON tags.id = recipe_tags.tag_id
               WHERE recipe_tags.recipe_id = recipes.id
                 AND tags.name IN (SELECT value FROM json_each(:tags)))
              = json_array_length(:tags)
          AND (:publication IS NULL OR sources.publication = :publication)
          AND (:author IS NULL OR sources.author = :author)
          AND (:source IS NULL OR recipes.source_id = :source)
          AND (:ingredient IS NULL OR EXISTS (
                SELECT 1 FROM ingredients
                JOIN ingredient_sections ON ingredient_sections.id = ingredients.section_id
                WHERE ingredient_sections.recipe_id = recipes.id
                  AND ingredients.item LIKE '%' || :ingredient || '%' ESCAPE '\\'))
          AND (:max_total IS NULL OR recipes.total_min <= :max_total)
          AND (:max_prep IS NULL OR recipes.prep_min <= :max_prep)
          AND (:serves_from IS NULL OR recipes.serves_max >= :serves_from)
          AND (:serves_to IS NULL OR recipes.serves_min <= :serves_to)
          AND (NOT :has_notes
               OR EXISTS (SELECT 1 FROM recipe_notes WHERE recipe_id = recipes.id))
        ORDER BY {ORDER_BY[sort]}
        """,
        {
            "match": match,
            "archived": filters.archived,
            "tags": json.dumps(sorted(set(filters.tag))),
            "publication": filters.publication,
            "author": filters.author,
            "source": filters.source,
            "ingredient": ingredient,
            "max_total": filters.max_total,
            "max_prep": filters.max_prep,
            "serves_from": filters.serves_from,
            "serves_to": filters.serves_to,
            "has_notes": filters.has_notes,
        },
    ).fetchall()
    return [recipe_id for (recipe_id,) in rows]


NOTES_SQL = """
SELECT coalesce(group_concat(body, char(10)), '')
FROM (SELECT body FROM recipe_notes WHERE recipe_id = ? ORDER BY id)
"""


def refresh(connection: sqlite3.Connection, recipe_id: int) -> None:
    """
    Rewrite one recipe's recipe_search row from the recipe tables and its notes.

    Call after any change to a recipe's own tables; note changes are kept current by the
    schema's triggers, which use the same expression as NOTES_SQL. A recipe that no longer
    exists loses its row.
    """
    recipe = connection.execute(
        """
        SELECT recipes.slug, recipes.title,
               trim(coalesce(sources.publication, '') || ' ' || coalesce(sources.author, ''))
        FROM recipes LEFT JOIN sources ON sources.id = recipes.source_id
        WHERE recipes.id = ?
        """,
        (recipe_id,),
    ).fetchone()
    connection.execute("DELETE FROM recipe_search WHERE rowid = ?", (recipe_id,))
    if recipe is None:
        return
    slug, title, source = recipe

    ingredient_lines: list[str] = []
    current_section = None
    for section_id, section_name, quantity, item in connection.execute(
        """
        SELECT ingredient_sections.id, ingredient_sections.name,
               ingredients.quantity, ingredients.item
        FROM ingredient_sections
        JOIN ingredients ON ingredients.section_id = ingredient_sections.id
        WHERE ingredient_sections.recipe_id = ?
        ORDER BY ingredient_sections.position, ingredients.position
        """,
        (recipe_id,),
    ):
        if section_id != current_section:
            current_section = section_id
            if section_name:
                ingredient_lines.append(section_name)
        ingredient_lines.append(f"{quantity} {item}".strip())

    steps = [
        f"{step_title}\n{step_text}"
        for step_title, step_text in connection.execute(
            "SELECT title, text FROM steps WHERE recipe_id = ? ORDER BY position", (recipe_id,)
        )
    ]
    tags = [
        name
        for (name,) in connection.execute(
            """
            SELECT tags.name FROM recipe_tags JOIN tags ON tags.id = recipe_tags.tag_id
            WHERE recipe_tags.recipe_id = ? ORDER BY tags.name
            """,
            (recipe_id,),
        )
    ]
    (notes,) = connection.execute(NOTES_SQL, (recipe_id,)).fetchone()

    connection.execute(
        """
        INSERT INTO recipe_search (rowid, slug, title, source, ingredients, steps, tags, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            recipe_id,
            slug,
            title,
            source,
            "\n".join(ingredient_lines),
            "\n".join(steps),
            " ".join(tags),
            notes,
        ),
    )
