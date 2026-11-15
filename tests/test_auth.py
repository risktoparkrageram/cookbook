import sqlite3

import pytest
from fastapi.testclient import TestClient

from cookbook.passwords import hash_password

SAME_ORIGIN = {"Origin": "http://testserver"}


def test_login_signs_in_and_returns_to_the_page(
    client: TestClient, recipes: sqlite3.Connection, admin: str
) -> None:
    response = client.post(
        "/login",
        data={"email": " Cook@Example.com ", "password": "correct horse battery", "next": "/tags"},
        headers=SAME_ORIGIN,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/tags"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("cookbook_session=")
    assert "httponly" in cookie.lower() and "samesite=lax" in cookie.lower()
    assert "max-age=31536000" in cookie.lower()
    assert "Sign out" in client.get("/").text
    last_login = recipes.execute("SELECT last_login_at FROM users").fetchone()[0]
    assert last_login is not None


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("cook@example.com", "wrong password here"),
        ("someone@example.com", "correct horse battery"),
    ],
)
def test_login_fails_on_a_wrong_password_or_email(
    client: TestClient, admin: str, email: str, password: str
) -> None:
    response = client.post(
        "/login", data={"email": email, "password": password}, headers=SAME_ORIGIN
    )

    assert response.status_code == 401
    assert "That email and password don’t match." in response.text
    assert "cookbook_session" not in response.headers.get("set-cookie", "")
    assert "Sign in</a>" in client.get("/").text


@pytest.mark.parametrize(
    ("next_page", "location"),
    [
        ("/recipes/tofu_rice_bowl?x=1", "/recipes/tofu_rice_bowl?x=1"),
        ("//evil.example/", "/"),
        ("/\\evil.example/", "/"),
        ("https://evil.example/", "/"),
    ],
)
def test_login_only_returns_to_pages_on_this_site(
    client: TestClient, admin: str, next_page: str, location: str
) -> None:
    response = client.post(
        "/login",
        data={"email": admin, "password": "correct horse battery", "next": next_page},
        headers=SAME_ORIGIN,
        follow_redirects=False,
    )

    assert response.headers["location"] == location


def test_login_from_another_site_is_refused(client: TestClient, admin: str) -> None:
    response = client.post(
        "/login",
        data={"email": admin, "password": "correct horse battery"},
        headers={"Origin": "http://evil.example"},
    )

    assert response.status_code == 403
    assert "set-cookie" not in response.headers


def test_logout_signs_out(admin_client: TestClient) -> None:
    response = admin_client.post("/logout", follow_redirects=False)

    assert response.headers["location"] == "/"
    assert "Sign in</a>" in admin_client.get("/").text


def test_a_new_password_signs_out_every_session(
    admin_client: TestClient, recipes: sqlite3.Connection
) -> None:
    recipes.execute("UPDATE users SET password_hash = ?", (hash_password("a different password"),))

    assert "Sign in</a>" in admin_client.get("/").text


def test_sign_in_link_returns_to_the_current_page(client: TestClient) -> None:
    page = client.get("/?q=tofu&tag=asian").text

    assert 'href="/login?next=/%3Fq%3Dtofu%26tag%3Dasian"' in page
