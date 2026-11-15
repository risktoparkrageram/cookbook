from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Every setting the app and its tools read, from COOKBOOK_* environment variables.

    No .env file is read: on the host the variables come from the service's
    EnvironmentFile, in development from the shell.
    """

    model_config = SettingsConfigDict(env_prefix="COOKBOOK_", frozen=True, extra="ignore")

    db_path: Path
    secret_key: SecretStr = Field(min_length=32)
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    migrate: bool = False
