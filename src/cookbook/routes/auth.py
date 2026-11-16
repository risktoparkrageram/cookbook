import time
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from cookbook import auth
from cookbook.auth import LocalPath, LoginForm
from cookbook.settings import Settings
from cookbook.web import Database, SameOrigin, templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: LocalPath = "/") -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"next": next, "email": ""})


@router.post("/login", dependencies=[SameOrigin])
def login(request: Request, connection: Database, form: Annotated[LoginForm, Form()]) -> Response:
    """
    Sign in and go back to the page the sign-in link was on.

    A failure waits COOKBOOK_FAILED_LOGIN_DELAY_S before answering.
    """
    session = auth.sign_in(connection, form)
    if session is None:
        settings: Settings = request.app.state.settings
        time.sleep(settings.failed_login_delay_s)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": form.next, "email": form.email, "failed": True},
            status_code=401,
        )
    request.session.clear()
    request.session.update(session.model_dump())
    return RedirectResponse(form.next, status_code=303)


@router.post("/logout", dependencies=[SameOrigin])
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=303)
