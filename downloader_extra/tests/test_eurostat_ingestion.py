"""Eurostat ingestion keeps filtered panels distinct and reuses existing slugs."""

import asyncio
from collections.abc import Iterator
import importlib
import json
from pathlib import Path
from types import ModuleType

import client_eurostat
import httpx
import pytest
from schema import Base, EurostatIndicator, EurostatIndicatorValue, IngestRequest, Region
from settings import get_settings
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

DATASET = "nama_10r_2gdp"


@pytest.fixture
def ingestion_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    # A file-backed database lets the fetcher's worker thread open its own engine.
    sql_uri = f"sqlite:///{tmp_path / 'eurostat.db'}"
    engine = create_engine(sql_uri)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Region(id="BE10", name="Brussels", level=2))

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("postgres: {database: macro}\n", encoding="utf-8")
    monkeypatch.setenv("POSTGRES_USER", "test")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    get_settings.cache_clear()
    api = importlib.import_module("main")
    monkeypatch.setattr(api.app.state, "sql_uri", sql_uri, raising=False)
    monkeypatch.setattr(api.app.state, "session_factory", sessionmaker(bind=engine), raising=False)
    try:
        yield api
    finally:
        get_settings.cache_clear()
        engine.dispose()


@pytest.fixture
def eurostat_requests(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        unit = request.url.params.get("unit", "DEFAULT")
        return httpx.Response(
            200,
            json={
                "id": ["unit", "geo", "time"],
                "size": [1, 1, 1],
                "dimension": {
                    "unit": {"category": {"index": {unit: 0}}},
                    "geo": {"category": {"index": {"BE10": 0}}},
                    "time": {"category": {"index": {"2024": 0}}},
                },
                "value": {"0": 100.0 if unit == "EUR_HAB" else 120.0},
            },
        )

    monkeypatch.setattr(
        client_eurostat,
        "build_async_client",
        lambda: httpx.AsyncClient(
            base_url="https://eurostat.test/", transport=httpx.MockTransport(handler)
        ),
    )
    return seen


def test_different_filters_store_distinct_panels(
    ingestion_api: ModuleType, eurostat_requests: list[httpx.Request]
) -> None:
    first = asyncio.run(
        ingestion_api._ingest_eurostat(
            IngestRequest(source="eurostat", dataset=DATASET, filters={"unit": "EUR_HAB"})
        )
    )
    second = asyncio.run(
        ingestion_api._ingest_eurostat(
            IngestRequest(source="eurostat", dataset=DATASET, filters={"unit": "PPS_HAB"})
        )
    )
    assert first.status == second.status == "success"
    assert first.identifier != second.identifier
    assert first.rows_inserted == second.rows_inserted == 1

    with ingestion_api.app.state.session_factory() as session:
        indicators = session.scalars(select(EurostatIndicator)).all()
        assert {row.indicator_id for row in indicators} == {first.identifier, second.identifier}
        values = session.scalars(select(EurostatIndicatorValue)).all()
        assert {row.indicator_id: row.value for row in values} == {
            first.identifier: 100.0,
            second.identifier: 120.0,
        }

    repeated = asyncio.run(
        ingestion_api._ingest_eurostat(
            IngestRequest(source="eurostat", dataset=DATASET, filters={"unit": "EUR_HAB"})
        )
    )
    assert repeated.status == "already_downloaded"
    assert repeated.identifier == first.identifier
    assert len(eurostat_requests) == 2


@pytest.mark.parametrize("existing_id", [DATASET, "gdp_per_capita"])
@pytest.mark.parametrize("dataset", [DATASET, DATASET.upper()])
def test_matching_legacy_or_curated_indicator_returns_its_actual_id(
    ingestion_api: ModuleType,
    eurostat_requests: list[httpx.Request],
    existing_id: str,
    dataset: str,
) -> None:
    with ingestion_api.app.state.session_factory() as session, session.begin():
        session.add(
            EurostatIndicator(
                indicator_id=existing_id,
                dataset=DATASET,
                filters=json.dumps({"unit": "EUR_HAB", "freq": "A"}),
            )
        )

    result = asyncio.run(
        ingestion_api._ingest_eurostat(
            IngestRequest(
                source="eurostat", dataset=dataset, filters={"freq": "A", "unit": "EUR_HAB"}
            )
        )
    )
    assert result.status == "already_downloaded"
    assert result.identifier == existing_id
    assert not eurostat_requests


@pytest.mark.parametrize("filters", [{"unit": "PPS_HAB"}, None])
def test_different_filters_preserve_a_legacy_panel(
    ingestion_api: ModuleType,
    eurostat_requests: list[httpx.Request],
    filters: dict[str, str] | None,
) -> None:
    with ingestion_api.app.state.session_factory() as session, session.begin():
        session.add(
            EurostatIndicator(
                indicator_id=DATASET, dataset=DATASET, filters=json.dumps({"unit": "EUR_HAB"})
            )
        )
        session.add(
            EurostatIndicatorValue(region="BE10", year=2024, indicator_id=DATASET, value=100.0)
        )

    result = asyncio.run(
        ingestion_api._ingest_eurostat(
            IngestRequest(source="eurostat", dataset=DATASET, filters=filters)
        )
    )
    assert result.status == "success"
    assert result.identifier != DATASET
    with ingestion_api.app.state.session_factory() as session:
        values = session.scalars(select(EurostatIndicatorValue)).all()
        assert {row.indicator_id: row.value for row in values} == {
            DATASET: 100.0,
            result.identifier: 120.0,
        }
