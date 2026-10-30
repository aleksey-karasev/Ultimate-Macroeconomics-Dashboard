"""Validation tests for downloader_extra's typed ``config.yaml`` view."""

from config import DownloaderExtraConfig, build_postgres_uri
from pydantic import ValidationError
import pytest
from sqlalchemy.engine import make_url


def test_valid_config_parses() -> None:
    cfg = DownloaderExtraConfig.model_validate(
        {
            "postgres": {"host": "db", "port": 5432},
            "downloader_extra": {"port": 8003},
            "app": {"port": 8501},  # foreign section ignored
        }
    )
    assert cfg.postgres.host == "db"
    assert cfg.postgres.port == 5432
    assert cfg.downloader_extra.port == 8003


def test_defaults_when_sections_absent() -> None:
    cfg = DownloaderExtraConfig.model_validate({})
    assert cfg.postgres.host == "db"
    assert cfg.postgres.database is None
    assert cfg.downloader_extra.port == 8003


def test_invalid_port_raises() -> None:
    with pytest.raises(ValidationError):
        DownloaderExtraConfig.model_validate({"postgres": {"port": "nope"}})


def test_postgres_uri_percent_encodes_credentials() -> None:
    uri = build_postgres_uri("main@example", "p@ss/word", "db", 5432, "macro")
    parsed = make_url(uri)

    assert "main%40example:p%40ss%2Fword" in uri
    assert parsed.username == "main@example"
    assert parsed.password == "p@ss/word"
    assert parsed.host == "db"
    assert parsed.port == 5432
    assert parsed.database == "macro"
