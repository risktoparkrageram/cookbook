import re
import sqlite3

import pytest
from fastapi.testclient import TestClient

COOKED_QUERY = "SELECT recipe_id FROM cooked_recipes ORDER BY recipe_id"


@pytest.mark.parametrize("cooked", ["true", "false"])
def test_guests_cannot_mark_recipes_cooked(
    client: TestClient, recipes: sqlite3.Connection, cooked: str
) -> None:
    response = client.post(
        "/recipes/tofu_rice_bowl/cooked",
        data={"cooked": cooked},
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 403
    assert [row[0] for row in recipes.execute(COOKED_QUERY)] == [3]


def test_marking_cooked_from_another_site_is_refused(
    admin_client: TestClient, recipes: sqlite3.Connection
) -> None:
    response = admin_client.post(
        "/recipes/tofu_rice_bowl/cooked",
        data={"cooked": "true"},
        headers={"Origin": "http://evil.example"},
    )

    assert response.json() == {"detail": "Cross-origin write refused"}
    assert [row[0] for row in recipes.execute(COOKED_QUERY)] == [3]


def test_marking_cooked_and_back_with_htmx_returns_the_tickbox(
    admin_client: TestClient, recipes: sqlite3.Connection
) -> None:
    """Marking twice stays one row; unmarking removes only that recipe's."""
    for _ in range(2):
        marked = admin_client.post(
            "/recipes/tofu_rice_bowl/cooked", data={"cooked": "true"}, headers={"HX-Request": "1"}
        )
    after_marking = [row[0] for row in recipes.execute(COOKED_QUERY)]
    unmarked = admin_client.post(
        "/recipes/tofu_rice_bowl/cooked", data={"cooked": "false"}, headers={"HX-Request": "1"}
    )

    assert after_marking == [1, 3]
    assert '<button class="cooked-tick" aria-pressed="true">Cooked</button>' in marked.text
    assert '<input type="hidden" name="cooked" value="false">' in marked.text
    assert '<button class="cooked-tick" aria-pressed="false">Cooked</button>' in unmarked.text
    assert [row[0] for row in recipes.execute(COOKED_QUERY)] == [3]


def test_marking_cooked_without_htmx_goes_back_to_the_recipe(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/recipes/tofu_rice_bowl/cooked", data={"cooked": "true"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/recipes/tofu_rice_bowl"


def test_marking_an_unknown_recipe_is_not_found(admin_client: TestClient) -> None:
    response = admin_client.post("/recipes/no_such_recipe/cooked", data={"cooked": "true"})

    assert response.status_code == 404


def test_guests_see_cooked_marks_but_no_tickbox(client: TestClient) -> None:
    listing = client.get("/").text
    biscuits = client.get("/recipes/almond_biscuits").text
    bowl = client.get("/recipes/tofu_rice_bowl").text

    assert re.findall(r'<span class="status( cooked)?">(\w+)</span>', listing) == [
        (" cooked", "Cooked"),
        ("", "New"),
        ("", "New"),
    ]
    assert '<span class="cooked-tick" aria-pressed="true">Cooked</span>' in biscuits
    assert "cooked-tick" not in bowl


def test_deleting_a_recipe_removes_its_cooked_mark(recipes: sqlite3.Connection) -> None:
    recipes.execute("DELETE FROM recipes WHERE id = 3")

    assert recipes.execute(COOKED_QUERY).fetchall() == []
