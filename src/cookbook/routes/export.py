import asyncio
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from cookbook import export, queries
from cookbook.web import Database, RequiredUser

router = APIRouter()

# Exports carry notes, which change at any time: never serve one from a cache.
NO_STORE = {"Cache-Control": "no-store"}


@router.get("/recipes/{slug}/export.pdf")
async def recipe_pdf(
    request: Request, connection: Database, slug: str, notes: bool = True
) -> Response:
    """
    The recipe as an A4 PDF, shown in the browser; notes=0 leaves the notes out.

    Exports are built one at a time on a worker thread (app.state.exports), so a burst of
    requests can't push the app past its memory cap or stall other pages.
    """
    recipe = queries.recipe(connection, slug)
    if recipe is None:
        raise HTTPException(status_code=404, detail="No such recipe")
    exports: asyncio.Semaphore = request.app.state.exports
    async with exports:
        hero = await asyncio.to_thread(export.hero_data, connection, slug)
        pdf = await asyncio.to_thread(export.recipe_pdf, recipe, hero, notes)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={**NO_STORE, "Content-Disposition": f'inline; filename="{slug}.pdf"'},
    )


@router.get("/recipes/{slug}/export.zip")
async def recipe_zip(request: Request, connection: Database, slug: str) -> Response:
    """The recipe as a draft folder with its images and notes, for recipe-db's import."""
    exports: asyncio.Semaphore = request.app.state.exports
    async with exports:
        recipe = await asyncio.to_thread(export.recipe_export, connection, slug)
        if recipe is None:
            raise HTTPException(status_code=404, detail="No such recipe")
        archive = await asyncio.to_thread(export.drafts_zip, [recipe])
    return Response(
        archive,
        media_type="application/zip",
        headers={**NO_STORE, "Content-Disposition": f'attachment; filename="{slug}.zip"'},
    )


@router.get("/export/all.zip")
async def all_recipes_zip(request: Request, connection: Database, user: RequiredUser) -> Response:
    """Every recipe, archived ones included, as draft folders: for signed-in users."""
    file_name = f"cookbook-{date.today().isoformat()}.zip"
    exports: asyncio.Semaphore = request.app.state.exports
    async with exports:
        recipes = await asyncio.to_thread(export.all_recipe_exports, connection)
        archive = await asyncio.to_thread(export.drafts_zip, recipes)
    return Response(
        archive,
        media_type="application/zip",
        headers={**NO_STORE, "Content-Disposition": f'attachment; filename="{file_name}"'},
    )
