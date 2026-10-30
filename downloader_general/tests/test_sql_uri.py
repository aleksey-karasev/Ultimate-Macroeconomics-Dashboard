"""Tests for safe Postgres URI construction."""

from sqlalchemy.engine import make_url
from src.utils.downloads import _get_sql_config


def test_sql_uri_percent_encodes_credentials() -> None:
    uri = _get_sql_config("user@example", "p@ss/word", "db", 5432, "macro")
    parsed = make_url(uri)

    assert "user%40example:p%40ss%2Fword" in uri
    assert parsed.username == "user@example"
    assert parsed.password == "p@ss/word"
    assert parsed.host == "db"
    assert parsed.port == 5432
    assert parsed.database == "macro"


def test_sql_uri_supports_cluster_level_connection() -> None:
    parsed = make_url(_get_sql_config("main", "password", "db", 5432, ""))
    assert parsed.database is None
