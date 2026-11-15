from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from cookbook import queries, schema, search
from cookbook.search import SearchFilters
from cookbook.web import Database

router = APIRouter()


class Health(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    schema_version: int


@router.get("/api/recipes")
def recipes(
    connection: Database, filters: Annotated[SearchFilters, Query()]
) -> list[queries.RecipeCard]:
    """Search the recipes with the same query string as the home page."""
    return queries.recipe_cards(connection, search.find(connection, filters))


@router.get("/api/recipes/{slug}")
def recipe(connection: Database, slug: str) -> queries.Recipe:
    found = queries.recipe(connection, slug)
    if found is None:
        raise HTTPException(status_code=404, detail="No such recipe")
    return found


@router.get("/healthz")
def health(connection: Database) -> Health:
    return Health(status="ok", schema_version=schema.current_version(connection))
