import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from cookbook import auth, db
from cookbook.auth import Session, User
from cookbook.settings import Settings
from cookbook.units import format_minutes

PACKAGE_DIR = Path(__file__).parent
HOME_TIME_ZONE = ZoneInfo("Europe/London")


def format_local_time(utc_text: str) -> str:
    """
    Show a timestamp SQLite stored in UTC as UK time: "2 Jan 2026, 18:40".

    The zone is fixed in code so the result doesn't depend on the host's time zone.
    """
    moment = datetime.fromisoformat(utc_text).replace(tzinfo=UTC).astimezone(HOME_TIME_ZONE)
    return f"{moment.day} {moment:%b %Y, %H:%M}"


def format_local_date(utc_text: str) -> str:
    """Show the UK date of a timestamp SQLite stored in UTC: "2 Jan 2026"."""
    moment = datetime.fromisoformat(utc_text).replace(tzinfo=UTC).astimezone(HOME_TIME_ZONE)
    return f"{moment.day} {moment:%b %Y}"


def signed_in_user_for_templates(request: Request) -> dict[str, User | None]:
    """Give every template the signed-in user, which signed_in_user put on the request."""
    user: User | None = getattr(request.state, "user", None)
    return {"user": user}


templates = Jinja2Templates(
    directory=PACKAGE_DIR / "templates", context_processors=[signed_in_user_for_templates]
)
templates.env.filters["minutes"] = format_minutes
templates.env.filters["local_time"] = format_local_time
templates.env.filters["local_date"] = format_local_date


def open_database(request: Request) -> Iterator[sqlite3.Connection]:
    """Give a request its own connection, closed when the response is done."""
    settings: Settings = request.app.state.settings
    connection = db.connect(settings.db_path)
    try:
        yield connection
    finally:
        connection.close()


Database = Annotated[sqlite3.Connection, Depends(open_database)]


def signed_in_user(request: Request, connection: Database) -> User | None:
    """
    Find the user the session cookie belongs to, if any, and keep it on the request.

    Every route depends on this, so templates can show the signed-in controls.
    """
    try:
        session = Session.model_validate(request.session) if request.session else None
    except ValidationError:
        session = None
    user = auth.session_user(connection, session) if session is not None else None
    if user is None:
        request.session.clear()
    request.state.user = user
    return user


def require_user(user: Annotated[User | None, Depends(signed_in_user)]) -> User:
    if user is None:
        raise HTTPException(status_code=403, detail="Sign in to change notes")
    return user


def require_same_origin(request: Request) -> None:
    """
    Refuse a write that another site's page sent, judged by its Origin or else Referer.

    The session cookie is SameSite=Lax, which already keeps it off most cross-site
    writes; this also covers browsers that ignore SameSite.
    """
    source = request.headers.get("origin") or request.headers.get("referer")
    if source is None or urlsplit(source).netloc != request.headers.get("host"):
        raise HTTPException(status_code=403, detail="Cross-origin write refused")


SignedInUser = Annotated[User | None, Depends(signed_in_user)]
RequiredUser = Annotated[User, Depends(require_user)]
SameOrigin = Depends(require_same_origin)
