import asyncio
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
async def login(
    request: Request, connection: Database, form: Annotated[LoginForm, Form()]
) -> Response:
    """
    Sign in and go back to the page the sign-in link was on.

    An address with auth.LOGIN_ATTEMPTS unsuccessful attempts in the window gets 429 without
    a password check. Passwords are checked one at a time on a worker thread, because each
    scrypt check needs about 32 MB and the app's memory is capped. A failure waits
    COOKBOOK_FAILED_LOGIN_DELAY_S before answering, without holding a thread.
    """
    settings: Settings = request.app.state.settings
    attempts: auth.LoginAttempts = request.app.state.login_attempts
    password_checks: asyncio.Semaphore = request.app.state.password_checks
    # Behind Caddy, uvicorn takes the address from X-Forwarded-For.
    address = request.client.host if request.client else ""
    if not attempts.allow(address, time.monotonic()):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": form.next, "email": form.email, "too_many": True},
            status_code=429,
        )
    async with password_checks:
        session = await asyncio.to_thread(auth.sign_in, connection, form)
    if session is None:
        await asyncio.sleep(settings.failed_login_delay_s)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": form.next, "email": form.email, "failed": True},
            status_code=401,
        )
    attempts.forget(address)
    request.session.clear()
    request.session.update(session.model_dump())
    return RedirectResponse(form.next, status_code=303)


@router.post("/logout", dependencies=[SameOrigin])
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=303)
