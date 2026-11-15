from pathlib import Path

import pytest

from cookbook.settings import Settings


def test_settings_read_cookbook_prefixed_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COOKBOOK_DB_PATH", "/srv/cookbook/data/recipes.db")
    monkeypatch.setenv("COOKBOOK_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("COOKBOOK_PORT", "80")
    monkeypatch.setenv("COOKBOOK_MIGRATE", "1")
    monkeypatch.setenv("DB_PATH", "/unprefixed/is/ignored.db")

    settings = Settings()

    assert settings.db_path == Path("/srv/cookbook/data/recipes.db")
    assert settings.secret_key.get_secret_value() == "x" * 32
    assert (settings.host, settings.port, settings.migrate) == ("127.0.0.1", 80, True)
