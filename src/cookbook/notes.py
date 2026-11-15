import sqlite3
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

type NoteText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]


class NewNote(BaseModel):
    """A note as the add form sends it; without step_id it is a recipe note."""

    model_config = ConfigDict(frozen=True)

    body: NoteText
    step_id: int | None = None


class NoteEdit(BaseModel):
    model_config = ConfigDict(frozen=True)

    body: NoteText


class NotePlace(BaseModel):
    """Where a note sits: its recipe, and its step for a step note."""

    model_config = ConfigDict(frozen=True)

    recipe_id: int
    slug: str
    step_id: int | None

    def anchor(self) -> str:
        return f"notes-step-{self.step_id}" if self.step_id is not None else "notes"


def place(connection: sqlite3.Connection, recipe_id: int, step_id: int | None) -> NotePlace:
    (slug,) = connection.execute("SELECT slug FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    return NotePlace(recipe_id=recipe_id, slug=slug, step_id=step_id)


def add(connection: sqlite3.Connection, slug: str, note: NewNote) -> NotePlace | None:
    """Add a note to a recipe or one of its steps; None if there is no such recipe or step."""
    row = connection.execute(
        """
        SELECT recipes.id FROM recipes
        WHERE recipes.slug = :slug
          AND (:step_id IS NULL
               OR EXISTS (SELECT 1 FROM steps WHERE id = :step_id AND recipe_id = recipes.id))
        """,
        {"slug": slug, "step_id": note.step_id},
    ).fetchone()
    if row is None:
        return None
    connection.execute(
        "INSERT INTO recipe_notes (recipe_id, step_id, body) VALUES (?, ?, ?)",
        (row["id"], note.step_id, note.body),
    )
    return NotePlace(recipe_id=row["id"], slug=slug, step_id=note.step_id)


def update(connection: sqlite3.Connection, note_id: int, edit: NoteEdit) -> NotePlace | None:
    row = connection.execute(
        """
        UPDATE recipe_notes SET body = ?, updated_at = datetime('now') WHERE id = ?
        RETURNING recipe_id, step_id
        """,
        (edit.body, note_id),
    ).fetchone()
    return place(connection, row["recipe_id"], row["step_id"]) if row is not None else None


def delete(connection: sqlite3.Connection, note_id: int) -> NotePlace | None:
    row = connection.execute(
        "DELETE FROM recipe_notes WHERE id = ? RETURNING recipe_id, step_id", (note_id,)
    ).fetchone()
    return place(connection, row["recipe_id"], row["step_id"]) if row is not None else None
