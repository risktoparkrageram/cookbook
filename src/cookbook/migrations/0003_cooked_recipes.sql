-- Recipes the cook has made at least once: a row means cooked, no row means not yet.
-- The app writes this table; recipe-db's import keeps recipe ids, so marks survive it.
CREATE TABLE cooked_recipes (
    recipe_id INTEGER PRIMARY KEY REFERENCES recipes (id) ON DELETE CASCADE
);
