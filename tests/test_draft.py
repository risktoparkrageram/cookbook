import pytest
from pytest_cases import parametrize_with_cases

from cookbook.draft import (
    DraftImages,
    IngredientLine,
    IngredientSection,
    RecipeDraft,
    Step,
    parse_serves,
)


def case_full_draft() -> RecipeDraft:
    return RecipeDraft(
        slug="miso_noodles",
        title="Miso Butter Noodles",
        url="https://example.com/miso-noodles",
        publication="Example Kitchen",
        author="A. Cook",
        serves="2",
        measure_system="au",
        prep_min=10,
        cook_min=10,
        tags=["japanese", "quick"],
        steps=[
            Step(title="Boil", text="Boil the noodles."),
            Step(title="Make the sauce", text="Melt the butter with the miso."),
        ],
        images=DraftImages(hero="hero.webp", card="card.webp", hero_alt="A bowl of noodles"),
        sections=[
            IngredientSection(
                name="Noodles",
                items=[
                    IngredientLine(quantity="200 g", item="udon noodles"),
                    IngredientLine(quantity="1 cup", item="plain flour", grams=125),
                ],
            ),
            IngredientSection(items=[IngredientLine(item="spring onions, to serve")]),
        ],
    )


def case_minimal_draft() -> RecipeDraft:
    return RecipeDraft(
        slug="toast", title="Toast", steps=[Step(title="Toast", text="Toast the bread.")]
    )


@parametrize_with_cases("draft", cases=".")
def test_toml_round_trip_keeps_every_field(draft: RecipeDraft) -> None:
    assert RecipeDraft.from_toml(draft.to_toml()) == draft


def test_from_toml_reads_pairs_and_tables_as_ingredient_lines() -> None:
    draft = RecipeDraft.from_toml(
        """
        slug = "pancakes"
        title = "Pancakes"
        steps = [{ title = "Batter", text = "Whisk." }]

        [[sections]]
        items = [["2", "eggs"], { quantity = "1 cup", item = "plain flour", grams = 125 }]
        """
    )

    assert draft.sections == [
        IngredientSection(
            items=[
                IngredientLine(quantity="2", item="eggs"),
                IngredientLine(quantity="1 cup", item="plain flour", grams=125),
            ]
        )
    ]


def test_to_toml_writes_ingredients_without_override_as_pairs() -> None:
    draft = RecipeDraft(
        slug="pancakes",
        title="Pancakes",
        steps=[Step(title="Batter", text="Whisk.")],
        sections=[IngredientSection(items=[IngredientLine(quantity="2", item="eggs")])],
    )

    assert draft.to_toml() == (
        'slug = "pancakes"\n'
        'title = "Pancakes"\n'
        'measure_system = "uk"\n'
        "tags = []\n"
        "steps = [\n"
        '    { title = "Batter", text = "Whisk." },\n'
        "]\n"
        "\n"
        "[[sections]]\n"
        "items = [\n"
        "    [\n"
        '        "2",\n'
        '        "eggs",\n'
        "    ],\n"
        "]\n"
    )


def test_total_defaults_to_the_sum_of_given_times() -> None:
    draft = RecipeDraft(
        slug="bread",
        title="Bread",
        steps=[Step(title="Bake", text="Bake.")],
        prep_min=20,
        rest_min=60,
    )

    assert draft.total_min == 80


def test_explicit_total_is_kept() -> None:
    draft = RecipeDraft(
        slug="bread",
        title="Bread",
        steps=[Step(title="Bake", text="Bake.")],
        prep_min=20,
        total_min=95,
    )

    assert draft.total_min == 95


def test_tags_are_lowercased_and_deduplicated_in_order() -> None:
    draft = RecipeDraft(
        slug="dal",
        title="Dal",
        steps=[Step(title="Cook", text="Cook.")],
        tags=["Indian", " quick ", "indian", "", "Side  Dish"],
    )

    assert draft.tags == ["indian", "quick", "side dish"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2–4", (2, 4, None)),
        ("4", (4, 4, None)),
        ("Serves 6", (6, 6, None)),
        ("6-8 people", (6, 8, None)),
        ("~24 cookies", (24, 24, "cookies")),
        ("Makes 12 muffins", (12, 12, "muffins")),
        ("5 (1 batch for a curry serving 5)", (5, 5, None)),
        ("as needed", (None, None, None)),
        (None, (None, None, None)),
    ],
)
def test_parse_serves(
    text: str | None, expected: tuple[int | None, int | None, str | None]
) -> None:
    assert parse_serves(text) == expected
