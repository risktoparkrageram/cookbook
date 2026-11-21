import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cookbook.app import create_app
from cookbook.auth import LoginAttempts
from cookbook.passwords import hash_password
from cookbook.settings import Settings

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
    attributes = [part.strip().lower() for part in cookie.split(";")[1:]]
    assert "httponly" in attributes and "samesite=lax" in attributes
    assert "max-age=31536000" in attributes
    assert "Sign out" in client.get("/").text
    last_login = recipes.execute("SELECT last_login_at FROM users").fetchone()[0]
    assert last_login is not None


def test_login_cookie_is_secure_by_default(database_path: Path, admin: str) -> None:
    settings = Settings(db_path=database_path, secret_key="s" * 32, failed_login_delay_s=0)
    client = TestClient(create_app(settings))

    response = client.post(
        "/login",
        data={"email": "cook@example.com", "password": "correct horse battery"},
        headers=SAME_ORIGIN,
        follow_redirects=False,
    )

    assert response.status_code == 303
    attributes = [part.strip().lower() for part in response.headers["set-cookie"].split(";")[1:]]
    assert "secure" in attributes


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("cook@example.com", "wrong password here"),
        ("someone@example.com", "correct horse battery"),
    ],
)
def test_login_fails_on_a_wrong_password_or_email_after_the_delay(
    database_path: Path, admin: str, email: str, password: str
) -> None:
    settings = Settings(db_path=database_path, secret_key="s" * 32, failed_login_delay_s=0.3)
    client = TestClient(create_app(settings))

    started = time.perf_counter()
    response = client.post(
        "/login", data={"email": email, "password": password}, headers=SAME_ORIGIN
    )
    elapsed = time.perf_counter() - started

    assert elapsed >= 0.3
    assert response.status_code == 401
    assert "That email and password don’t match." in response.text
    assert "cookbook_session" not in response.headers.get("set-cookie", "")
    assert "Sign in</a>" in client.get("/").text


def test_login_refuses_an_address_after_five_unsuccessful_attempts(
    client: TestClient, admin: str
) -> None:
    """The sixth try is refused even with the right password; other addresses still sign in."""
    for _ in range(5):
        failed = client.post(
            "/login", data={"email": admin, "password": "a wrong guess"}, headers=SAME_ORIGIN
        )
        assert failed.status_code == 401

    refused = client.post(
        "/login", data={"email": admin, "password": "correct horse battery"}, headers=SAME_ORIGIN
    )
    elsewhere = TestClient(client.app, client=("192.0.2.20", 50000)).post(
        "/login",
        data={"email": admin, "password": "correct horse battery"},
        headers=SAME_ORIGIN,
        follow_redirects=False,
    )

    assert refused.status_code == 429
    assert "Too many attempts. Try again in 15 minutes." in refused.text
    assert "cookbook_session" not in refused.headers.get("set-cookie", "")
    assert elsewhere.status_code == 303


def test_signing_in_clears_the_address_attempts(client: TestClient, admin: str) -> None:
    """Four failures, a sign-in, then four more failures still leave a fifth attempt."""
    for password in ["a wrong guess"] * 4 + ["correct horse battery"] + ["a wrong guess"] * 4:
        client.post("/login", data={"email": admin, "password": password}, headers=SAME_ORIGIN)

    response = client.post(
        "/login",
        data={"email": admin, "password": "correct horse battery"},
        headers=SAME_ORIGIN,
        follow_redirects=False,
    )

    assert response.status_code == 303


def test_login_attempts_expire_after_the_window() -> None:
    attempts = LoginAttempts()
    allowed = [attempts.allow("192.0.2.20", now) for now in [0, 10, 20, 30, 40, 899, 900]]

    assert allowed == [True, True, True, True, True, False, True]


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
