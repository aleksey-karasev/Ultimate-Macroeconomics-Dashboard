"""Typed view over the ``config.yaml`` slice the downloader_extra service reads."""

from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.engine import URL
import yaml


class PostgresConfig(BaseModel):
    """The ``postgres`` section. ``database`` falls back to ``POSTGRES_DB``."""

    host: str = "db"
    port: int = 5432
    database: str | None = None


class PortConfig(BaseModel):
    """A bare ``{port: int}`` service block."""

    port: int = 8003


class DownloaderExtraConfig(BaseModel):
    """The portion of ``config.yaml`` the downloader_extra service reads."""

    postgres: PostgresConfig = PostgresConfig()
    downloader_extra: PortConfig = PortConfig()


def build_postgres_uri(
    username: str, password: str, host: str, port: int, database: str | None
) -> str:
    """Build a SQLAlchemy Postgres URI with safely percent-encoded credentials."""
    return URL.create(
        "postgresql+psycopg2",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    ).render_as_string(hide_password=False)


def load_config(path: Path) -> DownloaderExtraConfig:
    """Parse and validate ``config.yaml`` into a :class:`DownloaderExtraConfig`."""
    return DownloaderExtraConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
