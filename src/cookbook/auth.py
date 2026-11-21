import hashlib
import sqlite3
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from cookbook.passwords import verify_password

SESSION_MAX_AGE_S = 365 * 24 * 60 * 60
LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_S = 15 * 60
# The hash of a random password that was thrown away. An email that matches no user is
# checked against it, so it takes as long to refuse as a wrong password and the timing
# doesn't tell which email is the account's.
UNKNOWN_USER_HASH = (
    "scrypt$32768$8$1$3HaKxL4pBAUlM//8cbKWAA==$iykBkF/ZEprk0TdFjw3BfURNfND3/8YSckO/m2lly34="
)


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


class LoginAttempts:
    """
    Sign-in attempts per client address that haven't yet succeeded, within LOGIN_WINDOW_S.

    An attempt counts before its password is checked, so a burst of parallel requests is
    held to LOGIN_ATTEMPTS as well. The counts live in memory: the app is one process, and
    a restart only forgets them.
    """

    def __init__(self) -> None:
        self.times: dict[str, list[float]] = {}

    def allow(self, address: str, now: float) -> bool:
        """Count an attempt from address, unless it already has LOGIN_ATTEMPTS in the window."""
        self.times = {
            known: recent
            for known, times in self.times.items()
            if (recent := [moment for moment in times if now - moment < LOGIN_WINDOW_S])
        }
        recent = self.times.setdefault(address, [])
        if len(recent) >= LOGIN_ATTEMPTS:
            return False
        recent.append(now)
        return True

    def forget(self, address: str) -> None:
        """Clear an address's attempts once it has signed in."""
        self.times.pop(address, None)


def session_key(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode()).hexdigest()[:32]


def sign_in(connection: sqlite3.Connection, form: LoginForm) -> Session | None:
    """Check an email and password and record the login; None when they don't match a user."""
    row = connection.execute(
        "SELECT id, password_hash FROM users WHERE email = ?", (form.email,)
    ).fetchone()
    if row is None:
        verify_password(form.password, UNKNOWN_USER_HASH)
        return None
    if not verify_password(form.password, row["password_hash"]):
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
