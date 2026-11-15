import io
import re
import sqlite3
import zipfile

from fastapi.testclient import TestClient
from pypdf import PdfReader

from cookbook.draft import DraftImages, IngredientLine, IngredientSection, RecipeDraft, Step

HERO_WEBP = bytes.fromhex(
    "524946461c000000574542505650384c100000002f038000000750b8284fff0311d1ff00"
)


def test_recipe_zip_round_trips_through_the_draft_format(
    client: TestClient, recipes: sqlite3.Connection
) -> None:
    """The draft read back from the zip holds every field the database has for the recipe."""
    recipes.execute("UPDATE ingredients SET grams_override = 21 WHERE item = 'soy sauce'")

    response = client.get("/recipes/tofu_rice_bowl/export.zip")

    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == 'attachment; filename="tofu_rice_bowl.zip"'
    assert response.headers["cache-control"] == "no-store"
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert sorted(archive.namelist()) == [
        "tofu_rice_bowl/card.webp",
        "tofu_rice_bowl/hero.webp",
        "tofu_rice_bowl/notes.toml",
        "tofu_rice_bowl/recipe.toml",
    ]
    draft = RecipeDraft.from_toml(archive.read("tofu_rice_bowl/recipe.toml").decode())
    assert draft == RecipeDraft(
        slug="tofu_rice_bowl",
        title="Tofu Rice Bowl",
        url="https://example.com/tofu",
        publication="Allotment Weekly",
        author="Ada Example",
        serves="2–4",
        measure_system="uk",
        prep_min=15,
        cook_min=125,
        total_min=140,
        tags=["asian", "korean", "tofu"],
        steps=[
            Step(title="Press the tofu", text="Press for 10 minutes."),
            Step(title="Fry the tofu", text="Fry until golden."),
        ],
        images=DraftImages(
            hero="hero.webp",
            card="card.webp",
            hero_alt="A bowl of tofu",
            credit="Photograph: A. Snapper",
        ),
        sections=[
            IngredientSection(
                items=[
                    IngredientLine(quantity="200 g", item="firm tofu"),
                    IngredientLine(quantity="2 x 400g", item="tins of beans"),
                ]
            ),
            IngredientSection(
                name="Sauce",
                items=[
                    IngredientLine(quantity="1½ tbsp", item="soy sauce", grams=21),
                    IngredientLine(quantity="", item="salt"),
                ],
            ),
        ],
    )
    assert archive.read("tofu_rice_bowl/hero.webp") == HERO_WEBP
    assert archive.read("tofu_rice_bowl/card.webp") == b"RIFG"
    assert archive.read("tofu_rice_bowl/notes.toml").decode() == (
        "[[notes]]\n"
        'body = "Double the sauce"\n'
        'created_at = "2026-01-02 10:00:00"\n'
        'updated_at = "2026-01-02 10:00:00"\n'
        "\n"
        "[[notes]]\n"
        'body = "Use a cast iron pan"\n'
        "step = 2\n"
        'step_title = "Fry the tofu"\n'
        'created_at = "2026-01-03 10:00:00"\n'
        'updated_at = "2026-01-03 10:00:00"\n'
    )


def test_recipe_zip_without_images_or_notes_holds_only_the_draft(client: TestClient) -> None:
    response = client.get("/recipes/chilli_oil_noodles/export.zip")

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert archive.namelist() == ["chilli_oil_noodles/recipe.toml"]
    draft = RecipeDraft.from_toml(archive.read("chilli_oil_noodles/recipe.toml").decode())
    assert (draft.images, draft.serves) == (None, "2")


def test_all_recipes_zip_is_for_signed_in_users(client: TestClient) -> None:
    response = client.get("/export/all.zip")

    assert response.status_code == 403


def test_all_recipes_zip_holds_every_recipe_and_lists_the_archived(
    admin_client: TestClient,
) -> None:
    response = admin_client.get("/export/all.zip")

    assert re.fullmatch(
        r'attachment; filename="cookbook-\d{4}-\d{2}-\d{2}\.zip"',
        response.headers["content-disposition"],
    )
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert archive.namelist() == [
        "archived.txt",
        "almond_biscuits/recipe.toml",
        "almond_biscuits/notes.toml",
        "chilli_oil_noodles/recipe.toml",
        "old_turnip_stew/recipe.toml",
        "tofu_rice_bowl/recipe.toml",
        "tofu_rice_bowl/hero.webp",
        "tofu_rice_bowl/card.webp",
        "tofu_rice_bowl/notes.toml",
    ]
    assert archive.read("archived.txt") == b"old_turnip_stew\n"


def test_pdf_holds_the_recipe_and_its_notes(
    client: TestClient, recipes: sqlite3.Connection
) -> None:
    """The step gets a Fahrenheit temperature, which the PDF must show in Celsius only."""
    recipes.execute("UPDATE steps SET text = 'Fry at 350°F until golden.' WHERE id = 2")

    response = client.get("/recipes/tofu_rice_bowl/export.pdf")

    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'inline; filename="tofu_rice_bowl.pdf"'
    reader = PdfReader(io.BytesIO(response.content))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert reader.metadata is not None and reader.metadata.title == "Tofu Rice Bowl"
    assert "°F" not in text
    for expected in [
        "Tofu Rice Bowl",
        "KOREAN · MAIN",
        "Allotment Weekly · Ada Example",
        "1½ tbsp",
        "soy sauce",
        "Press the tofu",
        "Fry at 180°C, gas 4 until golden.",
        "Double the sauce",
        "Use a cast iron pan",
    ]:
        assert expected in text


def test_pdf_can_leave_the_notes_out(client: TestClient) -> None:
    response = client.get("/recipes/tofu_rice_bowl/export.pdf?notes=0")

    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)
    assert "Fry until golden." in text
    assert "Double the sauce" not in text
    assert "Use a cast iron pan" not in text
