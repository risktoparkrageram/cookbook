import sqlite3

from cookbook import queries
from cookbook.queries import AuthorCount, ImageLink, NoteListing, PublicationCount, TagCount
from cookbook.units import QuantityToken


def test_recipe_cards_keep_the_given_order_with_kicker_and_card(
    recipes: sqlite3.Connection,
) -> None:
    """The rarer cuisine wins the kicker and a course tag replaces Main."""
    cards = queries.recipe_cards(recipes, [1, 3, 4, 2])

    assert [(card.slug, card.kicker, card.total_min, card.cooked) for card in cards] == [
        ("tofu_rice_bowl", "Korean · Main", 140, False),
        ("almond_biscuits", "Dessert", 32, True),
        ("old_turnip_stew", "Asian · Main", None, False),
        ("chilli_oil_noodles", "Asian · Main", 10, False),
    ]
    assert cards[0].card == ImageLink(
        url="/images/6-01234567.webp", width=600, height=450, alt="A bowl of tofu", credit=None
    )
    assert cards[1].card is None


def test_recipe_reads_sections_steps_and_notes_in_order(recipes: sqlite3.Connection) -> None:
    recipe = queries.recipe(recipes, "tofu_rice_bowl")

    assert recipe is not None
    assert recipe.kicker == "Korean · Main"
    assert recipe.source is not None and recipe.source.publication == "Allotment Weekly"
    assert [tag.name for tag in recipe.tags] == ["asian", "korean", "tofu"]
    assert recipe.hero is not None and recipe.hero.url == "/images/5-abcdef01.webp"
    assert [
        (section.name, [(line.quantity, line.item) for line in section.ingredients])
        for section in recipe.sections
    ] == [
        (None, [("200 g", "firm tofu"), ("2 x 400g", "tins of beans")]),
        ("Sauce", [("1½ tbsp", "soy sauce"), ("", "salt")]),
    ]
    assert recipe.sections[1].ingredients[0].quantity_tokens == [
        QuantityToken(text="1½", kind="number", value=1.5),
        QuantityToken(text=" tbsp", kind="text"),
    ]
    assert [(step.title, [note.body for note in step.notes]) for step in recipe.steps] == [
        ("Press the tofu", []),
        ("Fry the tofu", ["Use a cast iron pan"]),
    ]
    assert [note.body for note in recipe.notes] == ["Double the sauce"]


def test_recipe_finds_archived_recipes_but_not_unknown_slugs(
    recipes: sqlite3.Connection,
) -> None:
    archived = queries.recipe(recipes, "old_turnip_stew")

    assert archived is not None and archived.archived
    assert queries.recipe(recipes, "no_such_recipe") is None


def test_tag_counts_count_the_given_recipes_grouped_by_kind(
    recipes: sqlite3.Connection,
) -> None:
    """
    Tags of recipes outside the results stay listed with 0; tags only archived recipes have
    are left out.

    The stew (4) is archived: its turnip tag is on no other recipe.
    """
    recipes.executescript(
        """
        INSERT INTO tags (id, name, kind) VALUES (7, 'turnip', 'ingredient');
        INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (4, 7);
        """
    )

    groups = queries.tag_counts(recipes, [1, 2])

    assert groups == {
        "cuisine": [
            TagCount(name="asian", kind="cuisine", recipe_count=2),
            TagCount(name="korean", kind="cuisine", recipe_count=1),
        ],
        "ingredient": [TagCount(name="tofu", kind="ingredient", recipe_count=1)],
        "course": [TagCount(name="dessert", kind="course", recipe_count=0)],
        "style": [TagCount(name="quick", kind="style", recipe_count=1)],
        None: [TagCount(name="mystery", kind=None, recipe_count=0)],
    }


def test_publication_counts_group_authors_and_skip_archived(recipes: sqlite3.Connection) -> None:
    assert queries.publication_counts(recipes) == [
        PublicationCount(publication="Allotment Weekly", recipe_count=2),
        PublicationCount(publication="Balcony Bakes", recipe_count=1),
    ]


def test_author_counts_skip_unnamed_and_archived(recipes: sqlite3.Connection) -> None:
    assert queries.author_counts(recipes) == [
        AuthorCount(author="Ada Example", publications='["Allotment Weekly"]', recipe_count=1),
        AuthorCount(author="Bo Writer", publications='["Allotment Weekly"]', recipe_count=1),
    ]


def test_recent_notes_are_newest_first_with_their_step(recipes: sqlite3.Connection) -> None:
    notes = queries.recent_notes(recipes)

    assert notes == [
        NoteListing(
            id=2,
            body="Use a cast iron pan",
            created_at="2026-01-03 10:00:00",
            recipe_slug="tofu_rice_bowl",
            recipe_title="Tofu Rice Bowl",
            step_id=2,
            step_position=2,
            step_title="Fry the tofu",
        ),
        NoteListing(
            id=1,
            body="Double the sauce",
            created_at="2026-01-02 10:00:00",
            recipe_slug="tofu_rice_bowl",
            recipe_title="Tofu Rice Bowl",
            step_id=None,
            step_position=None,
            step_title=None,
        ),
        NoteListing(
            id=3,
            body="Freezes well",
            created_at="2026-01-01 10:00:00",
            recipe_slug="almond_biscuits",
            recipe_title="Almond Biscuits",
            step_id=None,
            step_position=None,
            step_title=None,
        ),
    ]
