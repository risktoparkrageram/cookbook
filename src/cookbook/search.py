import sqlite3

NOTES_SQL = """
SELECT coalesce(group_concat(body, char(10)), '')
FROM (SELECT body FROM recipe_notes WHERE recipe_id = ? ORDER BY id)
"""


def refresh(connection: sqlite3.Connection, recipe_id: int) -> None:
    """
    Rewrite one recipe's recipe_search row from the recipe tables and its notes.

    Call after any change to a recipe's own tables; note changes are kept current by the
    schema's triggers, which use the same expression as NOTES_SQL. A recipe that no longer
    exists loses its row.
    """
    recipe = connection.execute(
        """
        SELECT recipes.slug, recipes.title,
               trim(coalesce(sources.publication, '') || ' ' || coalesce(sources.author, ''))
        FROM recipes LEFT JOIN sources ON sources.id = recipes.source_id
        WHERE recipes.id = ?
        """,
        (recipe_id,),
    ).fetchone()
    connection.execute("DELETE FROM recipe_search WHERE rowid = ?", (recipe_id,))
    if recipe is None:
        return
    slug, title, source = recipe

    ingredient_lines: list[str] = []
    current_section = None
    for section_id, section_name, quantity, item in connection.execute(
        """
        SELECT ingredient_sections.id, ingredient_sections.name,
               ingredients.quantity, ingredients.item
        FROM ingredient_sections
        JOIN ingredients ON ingredients.section_id = ingredient_sections.id
        WHERE ingredient_sections.recipe_id = ?
        ORDER BY ingredient_sections.position, ingredients.position
        """,
        (recipe_id,),
    ):
        if section_id != current_section:
            current_section = section_id
            if section_name:
                ingredient_lines.append(section_name)
        ingredient_lines.append(f"{quantity} {item}".strip())

    steps = [
        f"{step_title}\n{step_text}"
        for step_title, step_text in connection.execute(
            "SELECT title, text FROM steps WHERE recipe_id = ? ORDER BY position", (recipe_id,)
        )
    ]
    tags = [
        name
        for (name,) in connection.execute(
            """
            SELECT tags.name FROM recipe_tags JOIN tags ON tags.id = recipe_tags.tag_id
            WHERE recipe_tags.recipe_id = ? ORDER BY tags.name
            """,
            (recipe_id,),
        )
    ]
    (notes,) = connection.execute(NOTES_SQL, (recipe_id,)).fetchone()

    connection.execute(
        """
        INSERT INTO recipe_search (rowid, slug, title, source, ingredients, steps, tags, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            recipe_id,
            slug,
            title,
            source,
            "\n".join(ingredient_lines),
            "\n".join(steps),
            " ".join(tags),
            notes,
        ),
    )
