import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cookbook import db, schema, search
from cookbook.app import create_app
from cookbook.passwords import hash_password
from cookbook.settings import Settings


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "cookbook.db"


@pytest.fixture
def database(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = db.connect(database_path)
    schema.migrate(connection)
    yield connection
    connection.close()


@pytest.fixture
def recipes(database: sqlite3.Connection) -> sqlite3.Connection:
    """
    Four invented recipes, one archived, sharing tags and a publication.

    "asian" is on three recipes and "korean" on one, so the kicker must pick the rarer
    cuisine; rows go in out of title and position order so a missing ORDER BY shows.
    "tofu" is the bowl's title, tag and ingredient but only in a step of the noodles, so
    ranking and the ingredient filter each tell the two apart. The bowl's hero is a real
    4 × 3 WebP, so a PDF can decode it. Only the biscuits are marked cooked. The bowl and
    the noodles share a publication but not an author; the stew's author and publication
    appear on no other recipe, so lists that should skip archived recipes leave them out.
    """
    database.executescript(
        """
        INSERT INTO sources (id, publication, author) VALUES
            (1, 'Allotment Weekly', 'Ada Example'),
            (2, 'Balcony Bakes', ''),
            (3, 'Allotment Weekly', 'Bo Writer'),
            (4, 'Cellar Notes', 'Cy Archive');
        INSERT INTO recipes (id, slug, title, source_id, url, serves_text, serves_min,
                             serves_max, prep_min, cook_min, total_min, archived) VALUES
            (1, 'tofu_rice_bowl', 'Tofu Rice Bowl', 1, 'https://example.com/tofu', '2–4', 2, 4,
             15, 125, 140, 0),
            (2, 'chilli_oil_noodles', 'Chilli Oil Noodles', 3, NULL, '2', 2, 2, 10, NULL, 10, 0),
            (3, 'almond_biscuits', 'Almond Biscuits', 2, NULL, '~24 biscuits', 24, 24, 20, 12,
             32, 0),
            (4, 'old_turnip_stew', 'Old Turnip Stew', 4, NULL, NULL, NULL, NULL, NULL,
             NULL, NULL, 1);
        UPDATE recipes SET yield_unit = 'biscuits' WHERE id = 3;
        INSERT INTO tags (id, name, kind) VALUES
            (1, 'asian', 'cuisine'), (2, 'korean', 'cuisine'), (3, 'tofu', 'ingredient'),
            (4, 'dessert', 'course'), (5, 'quick', 'style'), (6, 'mystery', NULL);
        INSERT INTO recipe_tags (recipe_id, tag_id) VALUES
            (1, 1), (1, 2), (1, 3), (2, 1), (2, 5), (3, 4), (3, 6), (4, 1), (4, 5);
        INSERT INTO ingredient_sections (id, recipe_id, position, name) VALUES
            (2, 1, 2, 'Sauce'), (1, 1, 1, NULL), (3, 2, 1, NULL), (4, 3, 1, NULL);
        INSERT INTO ingredients (section_id, position, quantity, item) VALUES
            (1, 2, '2 x 400g', 'tins of beans'),
            (1, 1, '200 g', 'firm tofu'),
            (2, 1, '1½ tbsp', 'soy sauce'),
            (2, 2, '', 'salt'),
            (3, 1, '100 g', 'noodles'),
            (4, 1, '150 g', 'ground almonds');
        INSERT INTO steps (id, recipe_id, position, title, text) VALUES
            (2, 1, 2, 'Fry the tofu', 'Fry until golden.'),
            (1, 1, 1, 'Press the tofu', 'Press for 10 minutes.'),
            (3, 2, 1, 'Boil', 'Boil the noodles and top with tofu.'),
            (4, 3, 1, 'Bake', 'Bake for 12 minutes.'),
            (5, 4, 1, 'Simmer', 'Simmer the turnips.');
        INSERT INTO images (id, recipe_id, role, data, content_type, sha256, width, height,
                            alt, credit) VALUES
            (5, 1, 'hero',
             x'524946461c000000574542505650384c100000002f038000000750b8284fff0311d1ff00',
             'image/webp', 'abcdef0123456789', 1600, 1200,
             'A bowl of tofu', 'Photograph: A. Snapper'),
            (6, 1, 'card', x'52494647', 'image/webp', '0123456789abcdef', 600, 450,
             'A bowl of tofu', NULL);
        INSERT INTO recipe_notes (id, recipe_id, step_id, body, created_at, updated_at) VALUES
            (1, 1, NULL, 'Double the sauce', '2026-01-02 10:00:00', '2026-01-02 10:00:00'),
            (2, 1, 2, 'Use a cast iron pan', '2026-01-03 10:00:00', '2026-01-03 10:00:00'),
            (3, 3, NULL, 'Freezes well', '2026-01-01 10:00:00', '2026-01-04 10:00:00');
        INSERT INTO cooked_recipes (recipe_id) VALUES (3);
        """
    )
    for recipe_id in range(1, 5):
        search.refresh(database, recipe_id)
    return database


@pytest.fixture
def client(recipes: sqlite3.Connection, database_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        db_path=database_path, secret_key="s" * 32, failed_login_delay_s=0, secure_cookie=False
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def admin(recipes: sqlite3.Connection) -> str:
    """The admin account, password "correct horse battery"; returns its email."""
    recipes.execute(
        "INSERT INTO users (id, email, password_hash) VALUES (1, 'cook@example.com', ?)",
        (hash_password("correct horse battery"),),
    )
    return "cook@example.com"


@pytest.fixture
def admin_client(client: TestClient, admin: str) -> TestClient:
    """The client signed in as the admin, sending this site's Origin with every request."""
    client.headers["Origin"] = "http://testserver"
    client.post("/login", data={"email": admin, "password": "correct horse battery"})
    return client
