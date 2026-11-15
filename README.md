# cookbook

A small, self-hosted recipe web app for a home network, built for phones in the kitchen.
Recipes live in one SQLite database; this repository holds only the code: no recipes.

Status: early. Browsing and search work: full-text search with filters (tags, source,
ingredient, times, serves, notes), recipe, tag, source and notes pages, images and a JSON
API. Anyone can read notes; a signed-in user adds, edits and deletes them. Any recipe exports
as an A4 PDF (with or without notes) or as a zipped draft folder; signed-in users can
download every recipe as one zip. In the kitchen, ingredients and steps tick off, the
current step is marked, the quantities scale with the serves and switch to metric, and the
screen stays awake; all of it is remembered per phone. The site can be added to a phone's
home screen.

There is one account and no sign-up. It is created on the host with recipe-db's
`set-password` command, which writes an scrypt hash to the `users` table; running it again
replaces the account's email and password, and the database refuses a second account.
Setting a new password signs out every device.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run scripts/lint-and-test.sh   # ruff, format check, mypy --strict, pytest
```

Run the app against a database (created by the migrations and filled by an import):

```bash
COOKBOOK_DB_PATH=path/to/recipes.db COOKBOOK_SECRET_KEY=$(openssl rand -hex 32) \
  uv run uvicorn --factory cookbook.app:create_app --reload
```

## Layout

| Path | |
|---|---|
| `src/cookbook/app.py` | `create_app()`: the FastAPI app; refuses to start on a database at another schema version |
| `src/cookbook/queries.py` | Reads recipes, tags, sources and notes into the models the pages show |
| `src/cookbook/routes/` | Pages (`pages.py`), sign-in (`auth.py`), note writes (`notes.py`) and the JSON API with `/healthz` (`api.py`) |
| `src/cookbook/auth.py`, `notes.py` | Signing in and the session cookie's contents; adding, editing and deleting notes |
| `src/cookbook/templates/`, `static/` | Jinja2 templates, CSS, scripts and the bundled Inter font (SIL OFL, `static/fonts/OFL.txt`) |
| `src/cookbook/migrations/` | Database schema as numbered SQL migrations (`schema.migrate`) |
| `src/cookbook/draft.py` | `RecipeDraft`: a recipe as a TOML file, for import and export |
| `src/cookbook/units.py` | Parses quantities such as `1½ cups` or `2 tbsp + 1 tsp` into grams or millilitres; marks the numbers the browser may scale; works out serves options, metric amounts and °F / inch conversions |
| `src/cookbook/densities.toml` | Grams per millilitre for showing volumes such as cups of flour in grams |
| `src/cookbook/static/cook.js` | Cook mode: ticks, current step, serves scaling, metric view, keeping the screen awake |
| `src/cookbook/search.py` | Searches and filters recipes, and keeps a recipe's full-text search index current |
| `src/cookbook/export.py` | PDF and draft exports, built on request |
| `src/cookbook/fonts/` | Inter TrueType subsets for the PDF (SIL OFL, `OFL.txt`) |
| `src/cookbook/static/htmx.min.js` | [htmx](https://htmx.org) 2.0.4, vendored release build (BSD-0) |
| `src/cookbook/passwords.py` | Hashes and verifies the admin password (scrypt) |
| `src/cookbook/settings.py` | Configuration from `COOKBOOK_*` environment variables |

## Configuration

| Variable | |
|---|---|
| `COOKBOOK_DB_PATH` | Path to the SQLite database (required) |
| `COOKBOOK_SECRET_KEY` | Session signing key, at least 32 characters (required) |
| `COOKBOOK_HOST`, `COOKBOOK_PORT` | Listen address, default `127.0.0.1:8000` |
| `COOKBOOK_MIGRATE` | Apply pending migrations at startup, default off |
