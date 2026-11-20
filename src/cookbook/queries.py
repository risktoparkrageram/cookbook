import json
import sqlite3
from collections import defaultdict

from pydantic import BaseModel, ConfigDict

from cookbook.schema import TAG_KINDS, TagKind
from cookbook.units import (
    Amount,
    MeasureSystem,
    MetricAmount,
    QuantityToken,
    ServesOption,
    TextPiece,
    convert_text,
    metric_amount,
    quantity_tokens,
    serves_options,
)

DEFAULT_COURSE = "main"


class ImageLink(BaseModel):
    """An image as a page shows it; the URL holds the image's hash so it can be cached forever."""

    model_config = ConfigDict(frozen=True)

    url: str
    width: int
    height: int
    alt: str | None
    credit: str | None


class Source(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    publication: str
    author: str


class Tag(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    kind: TagKind | None


class RecipeCard(BaseModel):
    """A recipe as listed: what a card on the home, tag and source pages shows."""

    model_config = ConfigDict(frozen=True)

    slug: str
    title: str
    kicker: str
    total_min: int | None
    card: ImageLink | None
    cooked: bool


class Ingredient(BaseModel):
    """
    An ingredient as the recipe page shows it.

    quantity_tokens mark the numbers the browser scales, item_pieces the inches in the
    item, and metric is what the Metric view shows instead of the quantity, if anything.
    """

    model_config = ConfigDict(frozen=True)

    quantity: str
    item: str
    quantity_tokens: list[QuantityToken]
    item_pieces: list[TextPiece]
    metric: MetricAmount | None


class IngredientSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None
    ingredients: list[Ingredient]


class Note(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    body: str
    created_at: str
    updated_at: str


class Step(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    position: int
    title: str
    text: str
    text_pieces: list[TextPiece]
    notes: list[Note]


class Recipe(BaseModel):
    """
    Everything the recipe page shows.

    notes holds the recipe notes; step notes sit on their step. card is the image a link
    preview shows, being smaller than hero.
    """

    model_config = ConfigDict(frozen=True)

    slug: str
    title: str
    kicker: str
    source: Source | None
    url: str | None
    archive_url: str | None
    measure_system: MeasureSystem
    serves_text: str | None
    serves_min: int | None
    serves_max: int | None
    serves_options: list[ServesOption]
    yield_unit: str | None
    prep_min: int | None
    cook_min: int | None
    rest_min: int | None
    total_min: int | None
    intro: str | None
    archived: bool
    cooked: bool
    tags: list[Tag]
    hero: ImageLink | None
    card: ImageLink | None
    sections: list[IngredientSection]
    steps: list[Step]
    notes: list[Note]

    def has_conversions(self) -> bool:
        """Whether the Metric view would change anything, so the page offers it."""
        return any(
            ingredient.metric is not None or any(piece.metric for piece in ingredient.item_pieces)
            for section in self.sections
            for ingredient in section.ingredients
        ) or any(piece.metric for step in self.steps for piece in step.text_pieces)


class TagCount(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    kind: TagKind | None
    recipe_count: int


class SourceCount(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    publication: str
    author: str
    recipe_count: int


class NoteListing(BaseModel):
    """A note on the notes page, with the recipe and step it belongs to."""

    model_config = ConfigDict(frozen=True)

    id: int
    body: str
    created_at: str
    recipe_slug: str
    recipe_title: str
    step_id: int | None
    step_position: int | None
    step_title: str | None


class StoredImage(BaseModel):
    model_config = ConfigDict(frozen=True)

    data: bytes
    content_type: str


IMAGE_COLUMNS = "images.id, images.sha256, images.width, images.height, images.alt, images.credit"


def image_link(row: sqlite3.Row) -> ImageLink:
    return ImageLink(
        url=f"/images/{row['id']}-{row['sha256'][:8]}.webp",
        width=row["width"],
        height=row["height"],
        alt=row["alt"],
        credit=row["credit"],
    )


def kickers(connection: sqlite3.Connection) -> dict[int, str]:
    """
    Return each recipe's kicker, cuisine · course, such as "Korean · Main", by recipe id.

    Of several cuisines the one on the fewest recipes is shown, as the most specific
    ("Korean" over "Asian"), ties going to the first alphabetically; a recipe without a
    course tag is a main.
    """
    rows = connection.execute(
        """
        SELECT recipe_tags.recipe_id, tags.name, tags.kind,
               (SELECT count(*) FROM recipe_tags AS uses WHERE uses.tag_id = tags.id) AS uses
        FROM recipe_tags JOIN tags ON tags.id = recipe_tags.tag_id
        WHERE tags.kind IN ('cuisine', 'course')
        ORDER BY uses, tags.name
        """
    ).fetchall()
    cuisines: dict[int, str] = {}
    courses: dict[int, str] = {}
    for row in rows:
        chosen = cuisines if row["kind"] == "cuisine" else courses
        chosen.setdefault(row["recipe_id"], row["name"])
    return {
        recipe_id: " · ".join(
            name.replace("-", " ").title()
            for name in [cuisines.get(recipe_id), courses.get(recipe_id, DEFAULT_COURSE)]
            if name
        )
        for (recipe_id,) in connection.execute("SELECT id FROM recipes")
    }


def recipe_cards(connection: sqlite3.Connection, recipe_ids: list[int]) -> list[RecipeCard]:
    """Read the cards of the given recipes, in the given order, such as a search's results."""
    recipe_kickers = kickers(connection)
    rows = connection.execute(
        f"""
        SELECT recipes.id AS recipe_id, recipes.slug, recipes.title, recipes.total_min,
               EXISTS (SELECT 1 FROM cooked_recipes WHERE recipe_id = recipes.id) AS cooked,
               {IMAGE_COLUMNS}
        FROM json_each(?) AS results
        JOIN recipes ON recipes.id = results.value
        LEFT JOIN images ON images.recipe_id = recipes.id AND images.role = 'card'
        ORDER BY results.key
        """,
        (json.dumps(recipe_ids),),
    ).fetchall()
    return [
        RecipeCard(
            slug=row["slug"],
            title=row["title"],
            kicker=recipe_kickers[row["recipe_id"]],
            total_min=row["total_min"],
            card=image_link(row) if row["id"] is not None else None,
            cooked=bool(row["cooked"]),
        )
        for row in rows
    ]


def recipe(connection: sqlite3.Connection, slug: str) -> Recipe | None:
    """Read one recipe by slug, archived or not, with its ingredients, steps and notes."""
    row = connection.execute(
        """
        SELECT recipes.*, sources.publication, sources.author,
               EXISTS (SELECT 1 FROM cooked_recipes WHERE recipe_id = recipes.id) AS cooked
        FROM recipes LEFT JOIN sources ON sources.id = recipes.source_id
        WHERE recipes.slug = ?
        """,
        (slug,),
    ).fetchone()
    if row is None:
        return None
    recipe_id = row["id"]

    images = {
        image["role"]: image_link(image)
        for image in connection.execute(
            f"SELECT images.role, {IMAGE_COLUMNS} FROM images WHERE recipe_id = ?", (recipe_id,)
        )
    }
    tags = [
        Tag(name=name, kind=kind)
        for name, kind in connection.execute(
            """
            SELECT tags.name, tags.kind FROM recipe_tags JOIN tags ON tags.id = recipe_tags.tag_id
            WHERE recipe_tags.recipe_id = ? ORDER BY tags.name
            """,
            (recipe_id,),
        )
    ]

    ingredients_by_section: dict[int, list[Ingredient]] = defaultdict(list)
    for line in connection.execute(
        """
        SELECT ingredients.section_id, ingredients.quantity, ingredients.item,
               ingredients.amount_min, ingredients.amount_max, ingredients.unit,
               ingredients.grams_override
        FROM ingredients JOIN ingredient_sections ON ingredient_sections.id = ingredients.section_id
        WHERE ingredient_sections.recipe_id = ? ORDER BY ingredients.position
        """,
        (recipe_id,),
    ):
        amount = (
            Amount(minimum=line["amount_min"], maximum=line["amount_max"], unit=line["unit"])
            if line["amount_min"] is not None
            else None
        )
        ingredients_by_section[line["section_id"]].append(
            Ingredient(
                quantity=line["quantity"],
                item=line["item"],
                quantity_tokens=quantity_tokens(line["quantity"]),
                item_pieces=convert_text(line["item"]),
                metric=metric_amount(
                    line["quantity"],
                    line["item"],
                    row["measure_system"],
                    amount,
                    line["grams_override"],
                ),
            )
        )
    sections = [
        IngredientSection(name=name, ingredients=ingredients_by_section[section_id])
        for section_id, name in connection.execute(
            "SELECT id, name FROM ingredient_sections WHERE recipe_id = ? ORDER BY position",
            (recipe_id,),
        )
    ]

    notes_by_step: dict[int | None, list[Note]] = defaultdict(list)
    for note in connection.execute(
        """
        SELECT id, step_id, body, created_at, updated_at FROM recipe_notes
        WHERE recipe_id = ? ORDER BY created_at, id
        """,
        (recipe_id,),
    ):
        notes_by_step[note["step_id"]].append(
            Note(
                id=note["id"],
                body=note["body"],
                created_at=note["created_at"],
                updated_at=note["updated_at"],
            )
        )
    steps = [
        Step(
            id=step["id"],
            position=step["position"],
            title=step["title"],
            text=step["text"],
            text_pieces=convert_text(step["text"]),
            notes=notes_by_step[step["id"]],
        )
        for step in connection.execute(
            "SELECT id, position, title, text FROM steps WHERE recipe_id = ? ORDER BY position",
            (recipe_id,),
        )
    ]

    return Recipe(
        slug=row["slug"],
        title=row["title"],
        kicker=kickers(connection)[recipe_id],
        source=(
            Source(id=row["source_id"], publication=row["publication"], author=row["author"])
            if row["source_id"] is not None
            else None
        ),
        url=row["url"],
        archive_url=row["archive_url"],
        measure_system=row["measure_system"],
        serves_text=row["serves_text"],
        serves_min=row["serves_min"],
        serves_max=row["serves_max"],
        serves_options=serves_options(row["serves_min"], row["serves_max"]),
        yield_unit=row["yield_unit"],
        prep_min=row["prep_min"],
        cook_min=row["cook_min"],
        rest_min=row["rest_min"],
        total_min=row["total_min"],
        intro=row["intro"],
        archived=bool(row["archived"]),
        cooked=bool(row["cooked"]),
        tags=tags,
        hero=images.get("hero"),
        card=images.get("card"),
        sections=sections,
        steps=steps,
        notes=notes_by_step[None],
    )


def tag_counts(
    connection: sqlite3.Connection, recipe_ids: list[int]
) -> dict[TagKind | None, list[TagCount]]:
    """
    Count how many of the given recipes have each tag, grouped by kind, by name.

    Every tag on a recipe that is not archived is listed, with a count of 0 if none of the
    given recipes has it, so the filter list keeps its shape as a search narrows. Kinds come
    in the schema's order, tags without a kind last.
    """
    counts = [
        TagCount.model_validate(dict(row))
        for row in connection.execute(
            """
            SELECT tags.name, tags.kind, count(results.value) AS recipe_count
            FROM tags
            JOIN recipe_tags ON recipe_tags.tag_id = tags.id
            JOIN recipes ON recipes.id = recipe_tags.recipe_id
            LEFT JOIN json_each(?) AS results ON results.value = recipes.id
            WHERE NOT recipes.archived OR results.value IS NOT NULL
            GROUP BY tags.id ORDER BY tags.name
            """,
            (json.dumps(recipe_ids),),
        )
    ]
    kind_order = [*TAG_KINDS, None]
    grouped: dict[TagKind | None, list[TagCount]] = {}
    for count in sorted(counts, key=lambda count: kind_order.index(count.kind)):
        grouped.setdefault(count.kind, []).append(count)
    return grouped


def tag(connection: sqlite3.Connection, name: str) -> Tag | None:
    row = connection.execute("SELECT name, kind FROM tags WHERE name = ?", (name,)).fetchone()
    return Tag.model_validate(dict(row)) if row is not None else None


def source_counts(connection: sqlite3.Connection) -> list[SourceCount]:
    """List the sources of recipes that are not archived, by publication then author."""
    return [
        SourceCount.model_validate(dict(row))
        for row in connection.execute(
            """
            SELECT sources.id, sources.publication, sources.author, count(*) AS recipe_count
            FROM sources JOIN recipes ON recipes.source_id = sources.id AND NOT recipes.archived
            GROUP BY sources.id
            ORDER BY sources.publication COLLATE NOCASE, sources.author COLLATE NOCASE
            """
        )
    ]


def source(connection: sqlite3.Connection, source_id: int) -> Source | None:
    row = connection.execute(
        "SELECT id, publication, author FROM sources WHERE id = ?", (source_id,)
    ).fetchone()
    return Source.model_validate(dict(row)) if row is not None else None


def notes(connection: sqlite3.Connection, recipe_id: int, step_id: int | None) -> list[Note]:
    """Read a recipe's notes, oldest first: one step's, or with no step the recipe notes."""
    return [
        Note.model_validate(dict(row))
        for row in connection.execute(
            """
            SELECT id, body, created_at, updated_at FROM recipe_notes
            WHERE recipe_id = ? AND step_id IS ? ORDER BY created_at, id
            """,
            (recipe_id, step_id),
        )
    ]


def recent_notes(connection: sqlite3.Connection) -> list[NoteListing]:
    """List every note, newest first, with its recipe and step."""
    return [
        NoteListing.model_validate(dict(row))
        for row in connection.execute(
            """
            SELECT recipe_notes.id, recipe_notes.body, recipe_notes.created_at,
                   recipes.slug AS recipe_slug, recipes.title AS recipe_title,
                   recipe_notes.step_id, steps.position AS step_position, steps.title AS step_title
            FROM recipe_notes
            JOIN recipes ON recipes.id = recipe_notes.recipe_id
            LEFT JOIN steps ON steps.id = recipe_notes.step_id
            ORDER BY recipe_notes.created_at DESC, recipe_notes.id DESC
            """
        )
    ]


def image(connection: sqlite3.Connection, image_id: int, hash_prefix: str) -> StoredImage | None:
    """
    Read an image's bytes, or None unless the hash prefix matches.

    Checking the hash means an old URL for a replaced image is a 404, never the new image
    under a cache lifetime meant for the old one.
    """
    row = connection.execute(
        "SELECT data, content_type FROM images WHERE id = ? AND substr(sha256, 1, 8) = ?",
        (image_id, hash_prefix),
    ).fetchone()
    return StoredImage.model_validate(dict(row)) if row is not None else None
