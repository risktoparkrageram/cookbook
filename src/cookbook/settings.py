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
    # Seconds a failed sign-in waits before answering, to slow down password guessing.
    failed_login_delay_s: float = Field(default=1.0, ge=0)
    # Mark the session cookie Secure, so browsers send it only over HTTPS. On wherever the
    # site is served over HTTPS (the host, behind Caddy); off for the plain-HTTP dev server,
    # where browsers would drop a Secure cookie and sign-in would never stick.
    secure_cookie: bool = False
