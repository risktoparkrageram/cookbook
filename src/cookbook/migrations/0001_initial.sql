CREATE TABLE sources (
    id          INTEGER PRIMARY KEY,
    publication TEXT NOT NULL,
    author      TEXT NOT NULL DEFAULT '',
    UNIQUE (publication, author)
);

CREATE TABLE recipes (
    id             INTEGER PRIMARY KEY,
    slug           TEXT NOT NULL UNIQUE CHECK (slug GLOB '[a-z0-9]*' AND slug NOT GLOB '*[^a-z0-9_]*'),
    title          TEXT NOT NULL,
    source_id      INTEGER REFERENCES sources (id),
    url            TEXT,
    archive_url    TEXT,
    measure_system TEXT NOT NULL DEFAULT 'uk' CHECK (measure_system IN ('uk', 'us', 'au')),
    serves_text    TEXT,
    serves_min     INTEGER,
    serves_max     INTEGER,
    yield_unit     TEXT,
    prep_min       INTEGER,
    cook_min       INTEGER,
    rest_min       INTEGER,
    total_min      INTEGER,
    intro          TEXT,
    archived       INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE ingredient_sections (
    id        INTEGER PRIMARY KEY,
    recipe_id INTEGER NOT NULL REFERENCES recipes (id) ON DELETE CASCADE,
    position  INTEGER NOT NULL,
    name      TEXT,
    UNIQUE (recipe_id, position)
);

-- quantity is the text as written; amount_min/amount_max/unit are the parsed form
-- (unit is 'g', 'ml' or NULL for a count) and are NULL when the text cannot be parsed.
CREATE TABLE ingredients (
    id             INTEGER PRIMARY KEY,
    section_id     INTEGER NOT NULL REFERENCES ingredient_sections (id) ON DELETE CASCADE,
    position       INTEGER NOT NULL,
    quantity       TEXT NOT NULL DEFAULT '',
    item           TEXT NOT NULL,
    amount_min     REAL,
    amount_max     REAL,
    unit           TEXT CHECK (unit IN ('g', 'ml')),
    grams_override REAL,
    UNIQUE (section_id, position)
);

CREATE TABLE steps (
    id        INTEGER PRIMARY KEY,
    recipe_id INTEGER NOT NULL REFERENCES recipes (id) ON DELETE CASCADE,
    position  INTEGER NOT NULL,
    text      TEXT NOT NULL,
    UNIQUE (recipe_id, position)
);

CREATE TABLE tags (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT CHECK (kind IN ('cuisine', 'ingredient', 'diet', 'course', 'style', 'technique'))
);

CREATE TABLE recipe_tags (
    recipe_id INTEGER NOT NULL REFERENCES recipes (id) ON DELETE CASCADE,
    tag_id    INTEGER NOT NULL REFERENCES tags (id),
    PRIMARY KEY (recipe_id, tag_id)
);

CREATE TABLE images (
    id           INTEGER PRIMARY KEY,
    recipe_id    INTEGER NOT NULL REFERENCES recipes (id) ON DELETE CASCADE,
    role         TEXT NOT NULL CHECK (role IN ('hero', 'card')),
    data         BLOB NOT NULL,
    content_type TEXT NOT NULL,
    sha256       TEXT NOT NULL,
    width        INTEGER NOT NULL,
    height       INTEGER NOT NULL,
    alt          TEXT,
    credit       TEXT,
    origin       TEXT,
    UNIQUE (recipe_id, role)
);

CREATE TABLE recipe_notes (
    id         INTEGER PRIMARY KEY,
    recipe_id  INTEGER NOT NULL REFERENCES recipes (id) ON DELETE CASCADE,
    step_id    INTEGER REFERENCES steps (id) ON DELETE SET NULL,
    body       TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 1000),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX recipe_notes_recipe ON recipe_notes (recipe_id);

CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at TEXT
);

-- One row per recipe, rowid = recipes.id. search.refresh writes every column; the
-- triggers below rewrite only notes, with the same expression as search.NOTES_SQL.
-- Ordering sits in a subquery, not group_concat(... ORDER BY), so SQLite before 3.44
-- (Debian 12 ships 3.40) can still read this schema.
CREATE VIRTUAL TABLE recipe_search USING fts5 (
    slug UNINDEXED,
    title,
    source,
    ingredients,
    steps,
    tags,
    notes,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER recipe_notes_after_insert AFTER INSERT ON recipe_notes BEGIN
    UPDATE recipe_search
    SET notes = (SELECT coalesce(group_concat(body, char(10)), '')
                 FROM (SELECT body FROM recipe_notes WHERE recipe_id = new.recipe_id ORDER BY id))
    WHERE rowid = new.recipe_id;
END;

CREATE TRIGGER recipe_notes_after_update AFTER UPDATE OF body, recipe_id ON recipe_notes BEGIN
    UPDATE recipe_search
    SET notes = (SELECT coalesce(group_concat(body, char(10)), '')
                 FROM (SELECT body FROM recipe_notes WHERE recipe_id = old.recipe_id ORDER BY id))
    WHERE rowid = old.recipe_id;
    UPDATE recipe_search
    SET notes = (SELECT coalesce(group_concat(body, char(10)), '')
                 FROM (SELECT body FROM recipe_notes WHERE recipe_id = new.recipe_id ORDER BY id))
    WHERE rowid = new.recipe_id;
END;

CREATE TRIGGER recipe_notes_after_delete AFTER DELETE ON recipe_notes BEGIN
    UPDATE recipe_search
    SET notes = (SELECT coalesce(group_concat(body, char(10)), '')
                 FROM (SELECT body FROM recipe_notes WHERE recipe_id = old.recipe_id ORDER BY id))
    WHERE rowid = old.recipe_id;
END;

CREATE TRIGGER recipes_after_delete AFTER DELETE ON recipes BEGIN
    DELETE FROM recipe_search WHERE rowid = old.id;
END;
