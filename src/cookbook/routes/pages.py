from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse

from cookbook import queries, search
from cookbook.search import SearchFilters
from cookbook.web import Database, templates

router = APIRouter()

IMAGE_CACHE_CONTROL = "public, max-age=31536000, immutable"
TIME_LIMITS = [15, 30, 45, 60, 90, 120, 180]


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request, connection: Database, filters: Annotated[SearchFilters, Query()]
) -> HTMLResponse:
    """
    Search and filter the recipes.

    htmx asks for just the results and the tag counts as the search changes; a full page
    otherwise, including when htmx restores a page from history it no longer holds. The
    cooked counts leave out the cooked filter, so each choice shows what it would find.
    """
    recipe_ids = search.find(connection, filters)
    ids_any_cooked = (
        recipe_ids
        if filters.cooked is None
        else search.find(connection, filters.model_copy(update={"cooked": None}))
    )
    partial = (
        "HX-Request" in request.headers and "HX-History-Restore-Request" not in request.headers
    )
    response = templates.TemplateResponse(
        request,
        "search_results.html" if partial else "search.html",
        {
            "section": "recipes",
            "filters": filters,
            "cards": queries.recipe_cards(connection, recipe_ids),
            "tag_groups": queries.tag_counts(connection, recipe_ids),
            "cooked_counts": queries.cooked_counts(connection, ids_any_cooked),
            "publications": queries.publication_counts(connection),
            "authors": queries.author_counts(connection),
            "time_limits": TIME_LIMITS,
        },
    )
    response.headers["Vary"] = "HX-Request"
    return response


@router.get("/recipes/{slug}", response_class=HTMLResponse)
def recipe_page(request: Request, connection: Database, slug: str) -> HTMLResponse:
    recipe = queries.recipe(connection, slug)
    if recipe is None:
        raise HTTPException(status_code=404, detail="No such recipe")
    return templates.TemplateResponse(
        request, "recipe.html", {"section": "recipes", "recipe": recipe}
    )


@router.get("/images/{image_id:int}-{hash_prefix}.webp")
def image(connection: Database, image_id: int, hash_prefix: str) -> Response:
    stored = queries.image(connection, image_id, hash_prefix)
    if stored is None:
        raise HTTPException(status_code=404, detail="No such image")
    return Response(
        stored.data,
        media_type=stored.content_type,
        headers={"Cache-Control": IMAGE_CACHE_CONTROL},
    )


@router.get("/tags", response_class=HTMLResponse)
def tags_page(request: Request, connection: Database) -> HTMLResponse:
    recipe_ids = search.find(connection, SearchFilters())
    return templates.TemplateResponse(
        request,
        "tags.html",
        {
            "section": "tags",
            "cooked_counts": queries.cooked_counts(connection, recipe_ids),
            "groups": queries.tag_counts(connection, recipe_ids),
        },
    )


@router.get("/tags/{name}", response_class=HTMLResponse)
def tag_page(request: Request, connection: Database, name: str) -> HTMLResponse:
    tag = queries.tag(connection, name)
    if tag is None:
        raise HTTPException(status_code=404, detail="No such tag")
    return templates.TemplateResponse(
        request,
        "listing.html",
        {
            "section": "tags",
            "label": tag.kind or "Tag",
            "heading": f"#{tag.name}",
            "cards": queries.recipe_cards(
                connection, search.find(connection, SearchFilters(tag=[tag.name]))
            ),
        },
    )


@router.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request, connection: Database) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "sources.html",
        {"section": "sources", "publications": queries.publication_counts(connection)},
    )


@router.get("/sources/{publication}", response_class=HTMLResponse)
def publication_page(request: Request, connection: Database, publication: str) -> HTMLResponse:
    recipe_ids = search.find(connection, SearchFilters(publication=publication))
    if not recipe_ids:
        raise HTTPException(status_code=404, detail="No such source")
    return templates.TemplateResponse(
        request,
        "listing.html",
        {
            "section": "sources",
            "label": "Source",
            "heading": publication,
            "cards": queries.recipe_cards(connection, recipe_ids),
        },
    )


@router.get("/authors", response_class=HTMLResponse)
def authors_page(request: Request, connection: Database) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "authors.html",
        {"section": "authors", "authors": queries.author_counts(connection)},
    )


@router.get("/authors/{author}", response_class=HTMLResponse)
def author_page(request: Request, connection: Database, author: str) -> HTMLResponse:
    recipe_ids = search.find(connection, SearchFilters(author=author))
    if not recipe_ids:
        raise HTTPException(status_code=404, detail="No such author")
    return templates.TemplateResponse(
        request,
        "listing.html",
        {
            "section": "authors",
            "label": "Author",
            "heading": author,
            "cards": queries.recipe_cards(connection, recipe_ids),
        },
    )


@router.get("/notes", response_class=HTMLResponse)
def notes_page(request: Request, connection: Database) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "notes.html", {"section": "notes", "notes": queries.recent_notes(connection)}
    )
