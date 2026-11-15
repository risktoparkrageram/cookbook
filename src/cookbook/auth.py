import hashlib
import sqlite3
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from cookbook.passwords import verify_password

SESSION_MAX_AGE_S = 365 * 24 * 60 * 60
FAILED_LOGIN_DELAY_S = 1.0


def local_path_or_home(path: str) -> str:
    """
    Keep a page to return to after signing in only if it is on this site.

    "//elsewhere.example" and "/\\elsewhere.example" are other sites to a browser.
    """
    if path.startswith("/") and not path.startswith(("//", "/\\")):
        return path
    return "/"


type LocalPath = Annotated[str, AfterValidator(local_path_or_home)]


class User(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    email: str


class LoginForm(BaseModel):
    model_config = ConfigDict(frozen=True)

    email: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=320)]
    password: Annotated[str, StringConstraints(max_length=1000)]
    next: LocalPath = "/"


class Session(BaseModel):
    """
    What the signed session cookie holds for a signed-in user.

    key is derived from the user's password hash, so setting a new password signs out
    every device; the cookie is signed, not encrypted, so it never holds the hash itself.
    """

    model_config = ConfigDict(frozen=True)

    user_id: int
    key: str


def session_key(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode()).hexdigest()[:32]


def sign_in(connection: sqlite3.Connection, form: LoginForm) -> Session | None:
    """Check an email and password and record the login; None when they don't match a user."""
    row = connection.execute(
        "SELECT id, password_hash FROM users WHERE email = ?", (form.email,)
    ).fetchone()
    if row is None or not verify_password(form.password, row["password_hash"]):
        return None
    connection.execute(
        "UPDATE users SET last_login_at = datetime('now') WHERE id = ?", (row["id"],)
    )
    return Session(user_id=row["id"], key=session_key(row["password_hash"]))


def session_user(connection: sqlite3.Connection, session: Session) -> User | None:
    """Find the user a session belongs to, unless the user is gone or has a new password."""
    row = connection.execute(
        "SELECT id, email, password_hash FROM users WHERE id = ?", (session.user_id,)
    ).fetchone()
    if row is None or session_key(row["password_hash"]) != session.key:
        return None
    return User(id=row["id"], email=row["email"])
