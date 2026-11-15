from datetime import date

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from cookbook import export, queries
from cookbook.web import Database, RequiredUser

router = APIRouter()

# Exports carry notes, which change at any time: never serve one from a cache.
NO_STORE = {"Cache-Control": "no-store"}


@router.get("/recipes/{slug}/export.pdf")
def recipe_pdf(connection: Database, slug: str, notes: bool = True) -> Response:
    """The recipe as an A4 PDF, shown in the browser; notes=0 leaves the notes out."""
    recipe = queries.recipe(connection, slug)
    if recipe is None:
        raise HTTPException(status_code=404, detail="No such recipe")
    pdf = export.recipe_pdf(recipe, export.hero_data(connection, slug), include_notes=notes)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={**NO_STORE, "Content-Disposition": f'inline; filename="{slug}.pdf"'},
    )


@router.get("/recipes/{slug}/export.zip")
def recipe_zip(connection: Database, slug: str) -> Response:
    """The recipe as a draft folder with its images and notes, for recipe-db's import."""
    recipe = export.recipe_export(connection, slug)
    if recipe is None:
        raise HTTPException(status_code=404, detail="No such recipe")
    return Response(
        export.drafts_zip([recipe]),
        media_type="application/zip",
        headers={**NO_STORE, "Content-Disposition": f'attachment; filename="{slug}.zip"'},
    )


@router.get("/export/all.zip")
def all_recipes_zip(connection: Database, user: RequiredUser) -> Response:
    """Every recipe, archived ones included, as draft folders: for signed-in users."""
    file_name = f"cookbook-{date.today().isoformat()}.zip"
    return Response(
        export.drafts_zip(export.all_recipe_exports(connection)),
        media_type="application/zip",
        headers={**NO_STORE, "Content-Disposition": f'attachment; filename="{file_name}"'},
    )
