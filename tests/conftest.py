import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from cookbook import db, schema


@pytest.fixture
def database(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = db.connect(tmp_path / "cookbook.db")
    schema.migrate(connection)
    yield connection
    connection.close()
