from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from cookbook.cooked import CookedForm, set_cooked
from cookbook.web import Database, RequiredUser, SameOrigin, templates

router = APIRouter(dependencies=[SameOrigin])


@router.post("/recipes/{slug}/cooked")
def mark_cooked(
    request: Request,
    connection: Database,
    user: RequiredUser,
    slug: str,
    form: Annotated[CookedForm, Form()],
) -> Response:
    """Set the cooked tickbox; htmx gets the new tickbox, a plain form post the recipe page."""
    if not set_cooked(connection, slug, form.cooked):
        raise HTTPException(status_code=404, detail="No such recipe")
    if "HX-Request" not in request.headers:
        return RedirectResponse(f"/recipes/{slug}", status_code=303)
    return templates.TemplateResponse(
        request, "_cooked.html", {"slug": slug, "cooked": form.cooked}
    )
