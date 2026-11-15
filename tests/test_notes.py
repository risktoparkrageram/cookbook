import re
import sqlite3

import pytest
from fastapi.testclient import TestClient

NOTES_QUERY = "SELECT recipe_id, step_id, body FROM recipe_notes ORDER BY id"
FIXTURE_NOTES = [
    (1, None, "Double the sauce"),
    (1, 2, "Use a cast iron pan"),
    (3, None, "Freezes well"),
]
WRITE_ROUTES = [
    ("POST", "/recipes/tofu_rice_bowl/notes", {"body": "More garlic"}),
    ("POST", "/notes/1", {"body": "Triple the sauce"}),
    ("DELETE", "/notes/1", None),
]


@pytest.mark.parametrize(("method", "path", "form"), WRITE_ROUTES)
def test_guests_cannot_write_notes(
    client: TestClient,
    recipes: sqlite3.Connection,
    method: str,
    path: str,
    form: dict[str, str] | None,
) -> None:
    response = client.request(method, path, data=form, headers={"Origin": "http://testserver"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Sign in to change notes"}
    assert [tuple(row) for row in recipes.execute(NOTES_QUERY)] == FIXTURE_NOTES


@pytest.mark.parametrize("origin", [{"Origin": "http://evil.example"}, {"Origin": "null"}, {}])
@pytest.mark.parametrize(("method", "path", "form"), WRITE_ROUTES)
def test_writes_from_another_site_are_refused(
    admin_client: TestClient,
    recipes: sqlite3.Connection,
    origin: dict[str, str],
    method: str,
    path: str,
    form: dict[str, str] | None,
) -> None:
    """With no Origin and no Referer the write is refused too: its source is unknown."""
    del admin_client.headers["Origin"]

    response = admin_client.request(method, path, data=form, headers=origin)

    assert response.status_code == 403
    assert response.json() == {"detail": "Cross-origin write refused"}
    assert [tuple(row) for row in recipes.execute(NOTES_QUERY)] == FIXTURE_NOTES


def test_referer_from_this_site_is_enough(
    admin_client: TestClient, recipes: sqlite3.Connection
) -> None:
    del admin_client.headers["Origin"]

    response = admin_client.post(
        "/notes/1",
        data={"body": "Triple the sauce"},
        headers={"Referer": "http://testserver/recipes/tofu_rice_bowl"},
        follow_redirects=False,
    )

    assert response.status_code == 303


def test_adding_a_recipe_note_with_htmx_returns_the_notes_block(
    admin_client: TestClient, recipes: sqlite3.Connection
) -> None:
    response = admin_client.post(
        "/recipes/tofu_rice_bowl/notes",
        data={"body": "  Toast the sesame <seeds>  "},
        headers={"HX-Request": "true"},
    )

    assert response.text.startswith('<div class="notes" id="notes">')
    assert re.findall(r"<div class=\"note\">\s*<p>([^<]*)</p>", response.text) == [
        "Double the sauce",
        "Toast the sesame &lt;seeds&gt;",
    ]
    assert [tuple(row) for row in recipes.execute(NOTES_QUERY)] == [
        *FIXTURE_NOTES,
        (1, None, "Toast the sesame <seeds>"),
    ]
    found = recipes.execute(
        "SELECT slug FROM recipe_search WHERE recipe_search MATCH 'sesame'"
    ).fetchall()
    assert [slug for (slug,) in found] == ["tofu_rice_bowl"]


def test_adding_a_step_note_without_htmx_goes_back_to_the_step(
    admin_client: TestClient, recipes: sqlite3.Connection
) -> None:
    response = admin_client.post(
        "/recipes/tofu_rice_bowl/notes",
        data={"body": "Dry the tofu first", "step_id": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/recipes/tofu_rice_bowl#notes-step-1"
    assert [tuple(row) for row in recipes.execute(NOTES_QUERY)] == [
        *FIXTURE_NOTES,
        (1, 1, "Dry the tofu first"),
    ]


@pytest.mark.parametrize(
    ("path", "form"),
    [
        ("/recipes/tofu_rice_bowl/notes", {"body": "Wrong recipe's step", "step_id": "3"}),
        ("/recipes/no_such_recipe/notes", {"body": "Nowhere"}),
        ("/notes/99", {"body": "No such note"}),
    ],
)
def test_notes_on_unknown_recipes_steps_or_notes_are_not_found(
    admin_client: TestClient, recipes: sqlite3.Connection, path: str, form: dict[str, str]
) -> None:
    """Step 3 exists but belongs to the noodles, not the tofu bowl."""
    response = admin_client.post(path, data=form)

    assert response.status_code == 404
    assert [tuple(row) for row in recipes.execute(NOTES_QUERY)] == FIXTURE_NOTES


@pytest.mark.parametrize("body", ["   ", "x" * 1001])
def test_blank_or_overlong_notes_are_rejected(
    admin_client: TestClient, recipes: sqlite3.Connection, body: str
) -> None:
    response = admin_client.post("/recipes/tofu_rice_bowl/notes", data={"body": body})

    assert response.status_code == 422
    assert [tuple(row) for row in recipes.execute(NOTES_QUERY)] == FIXTURE_NOTES


def test_editing_a_note_marks_it_edited(
    admin_client: TestClient, recipes: sqlite3.Connection
) -> None:
    response = admin_client.post(
        "/notes/2", data={"body": "Use a carbon steel pan"}, headers={"HX-Request": "true"}
    )

    assert response.text.startswith('<div class="notes" id="notes-step-2">')
    assert "<p>Use a carbon steel pan</p>" in response.text
    assert ">3 Jan 2026</time> · edited" in response.text
    assert [tuple(row) for row in recipes.execute(NOTES_QUERY)] == [
        (1, None, "Double the sauce"),
        (1, 2, "Use a carbon steel pan"),
        (3, None, "Freezes well"),
    ]


def test_deleting_a_note(admin_client: TestClient, recipes: sqlite3.Connection) -> None:
    response = admin_client.delete("/notes/1", headers={"HX-Request": "true"})

    assert response.text.startswith('<div class="notes" id="notes">')
    assert "Double the sauce" not in response.text
    assert [tuple(row) for row in recipes.execute(NOTES_QUERY)] == [
        (1, 2, "Use a cast iron pan"),
        (3, None, "Freezes well"),
    ]


def test_signed_in_recipe_page_offers_adding_and_editing(admin_client: TestClient) -> None:
    page = admin_client.get("/recipes/tofu_rice_bowl").text

    assert page.count("+ Note") == 3
    assert page.count('hx-delete="/notes/') == 2
    assert '<input type="hidden" name="step_id" value="2">' in page


def test_notes_page_shows_uk_time_and_links_to_the_step(
    client: TestClient, recipes: sqlite3.Connection
) -> None:
    """A summer note is an hour ahead of UTC (BST); the fixture's January notes are not."""
    recipes.execute("UPDATE recipe_notes SET created_at = '2026-07-01 09:30:00' WHERE id = 2")

    page = client.get("/notes").text

    assert re.findall(r'<a href="(/recipes/[^"]+)">', page) == [
        "/recipes/tofu_rice_bowl#notes-step-2",
        "/recipes/tofu_rice_bowl#notes",
        "/recipes/almond_biscuits#notes",
    ]
    assert "1 Jul 2026, 10:30" in page
    assert "2 Jan 2026, 10:00" in page
