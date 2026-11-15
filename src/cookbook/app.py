import os

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from starlette.types import Scope

from cookbook import auth, db
from cookbook.routes import api, export, notes, pages
from cookbook.routes import auth as auth_routes
from cookbook.settings import Settings
from cookbook.web import PACKAGE_DIR, signed_in_user

FONT_CACHE_CONTROL = "public, max-age=31536000, immutable"


class StaticAssets(StaticFiles):
    """
    Static files, with the web font cached for a year.

    The font is the only large static file and never changes under its name; CSS and scripts
    are small and revalidate on every load, so a deploy shows up at once.
    """

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = (
            FONT_CACHE_CONTROL if str(full_path).endswith(".woff2") else "no-cache"
        )
        return response


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    Build the web app, refusing to start on a database at another schema version.

    uvicorn calls this with no settings (uvicorn --factory cookbook.app:create_app), so they
    come from the COOKBOOK_* environment variables.
    """
    settings = settings or Settings()
    connection = db.connect(settings.db_path)
    try:
        db.require_current_schema(connection, migrate=settings.migrate)
    finally:
        connection.close()

    app = FastAPI(
        title="Cookbook",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        dependencies=[Depends(signed_in_user)],
    )
    app.state.settings = settings
    # The cookie is HttpOnly (always, in Starlette) and not Secure: the site is plain HTTP.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key.get_secret_value(),
        session_cookie="cookbook_session",
        max_age=auth.SESSION_MAX_AGE_S,
        same_site="lax",
        https_only=False,
    )
    app.mount("/static", StaticAssets(directory=PACKAGE_DIR / "static"), name="static")
    app.include_router(pages.router)
    app.include_router(notes.router)
    app.include_router(export.router)
    app.include_router(auth_routes.router)
    app.include_router(api.router)
    return app
