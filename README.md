# cookbook

A small, self-hosted recipe web app for a home network, built for phones in the kitchen.
Recipes live in one SQLite database; this repository holds only the code: no recipes.

Status: early. The database schema, the draft recipe format and quantity parsing exist;
the web app does not yet.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run scripts/lint-and-test.sh   # ruff, format check, mypy --strict, pytest
```

## Layout

| Path | |
|---|---|
| `src/cookbook/migrations/` | Database schema as numbered SQL migrations (`schema.migrate`) |
| `src/cookbook/draft.py` | `RecipeDraft`: a recipe as a TOML file, for import and export |
| `src/cookbook/units.py` | Parses quantities such as `1½ cups` or `2 tbsp + 1 tsp` into grams or millilitres |
| `src/cookbook/search.py` | Keeps the full-text search index for a recipe current |
| `src/cookbook/settings.py` | Configuration from `COOKBOOK_*` environment variables |

## Configuration

| Variable | |
|---|---|
| `COOKBOOK_DB_PATH` | Path to the SQLite database (required) |
| `COOKBOOK_SECRET_KEY` | Session signing key, at least 32 characters (required) |
| `COOKBOOK_HOST`, `COOKBOOK_PORT` | Listen address, default `127.0.0.1:8000` |
| `COOKBOOK_MIGRATE` | Apply pending migrations at startup, default off |
