import sqlite3

from pydantic import BaseModel, ConfigDict


class CookedForm(BaseModel):
    """The cooked tickbox as its form sends it: the state to set."""

    model_config = ConfigDict(frozen=True)

    cooked: bool


def set_cooked(connection: sqlite3.Connection, slug: str, cooked: bool) -> bool:
    """Mark a recipe cooked or not yet cooked; False if there is no such recipe."""
    row = connection.execute("SELECT id FROM recipes WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        return False
    if cooked:
        connection.execute(
            "INSERT OR IGNORE INTO cooked_recipes (recipe_id) VALUES (?)", (row["id"],)
        )
    else:
        connection.execute("DELETE FROM cooked_recipes WHERE recipe_id = ?", (row["id"],))
    return True
