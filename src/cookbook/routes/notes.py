from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from cookbook import notes, queries
from cookbook.notes import NewNote, NoteEdit, NotePlace
from cookbook.web import Database, RequiredUser, SameOrigin, templates

router = APIRouter(dependencies=[SameOrigin])


def notes_block(request: Request, connection: Database, place: NotePlace | None) -> Response:
    """
    Answer a note change with the changed block of notes for htmx to swap in.

    Without htmx, a plain form post, the browser goes back to that place on the recipe page.
    """
    if place is None:
        raise HTTPException(status_code=404, detail="No such recipe, step or note")
    if "HX-Request" not in request.headers:
        return RedirectResponse(f"/recipes/{place.slug}#{place.anchor()}", status_code=303)
    return templates.TemplateResponse(
        request,
        "_notes.html",
        {
            "notes": queries.notes(connection, place.recipe_id, place.step_id),
            "slug": place.slug,
            "step_id": place.step_id,
        },
    )


@router.post("/recipes/{slug}/notes")
def add_note(
    request: Request,
    connection: Database,
    user: RequiredUser,
    slug: str,
    note: Annotated[NewNote, Form()],
) -> Response:
    return notes_block(request, connection, notes.add(connection, slug, note))


@router.post("/notes/{note_id:int}")
def edit_note(
    request: Request,
    connection: Database,
    user: RequiredUser,
    note_id: int,
    edit: Annotated[NoteEdit, Form()],
) -> Response:
    return notes_block(request, connection, notes.update(connection, note_id, edit))


@router.delete("/notes/{note_id:int}")
def delete_note(
    request: Request, connection: Database, user: RequiredUser, note_id: int
) -> Response:
    return notes_block(request, connection, notes.delete(connection, note_id))
