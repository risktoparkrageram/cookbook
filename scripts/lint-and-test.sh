#!/bin/sh
set -eu

ruff check .
ruff format --check .
mypy src tests
pytest
playwright install chromium
pytest -m smoke
