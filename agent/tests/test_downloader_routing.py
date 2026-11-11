"""Unit tests for the on-demand download routing helpers (offline, no LLM/DB).

Covers the two pure functions that decide *where* a download goes:
``DownloaderAgent._build_payload`` (DownloadPlan → /ingest body) and
``_detect_market_needs_download`` (empty SQL result → yahoo/binance/None).
"""

from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from agent.graph import DownloaderAgent, MacroAgentGraph, _detect_market_needs_download
from agent.schemas import DownloadPlan
import pytest

from agent import graph


def test_build_payload_worldbank() -> None:
    plan = DownloadPlan(
        thought_process="...", source="worldbank", indicator_id="NY.GDP.MKTP.CD", db_id=2
    )
    identifier, payload = DownloaderAgent._build_payload(plan)
    assert identifier == "NY.GDP.MKTP.CD"
    assert payload == {"source": "worldbank", "indicator_id": "NY.GDP.MKTP.CD", "db_id": 2}


def test_build_payload_yahoo() -> None:
    plan = DownloadPlan(thought_process="...", source="yahoo", ticker="AAPL")
    identifier, payload = DownloaderAgent._build_payload(plan)
    assert identifier == "AAPL"
    assert payload == {"source": "yahoo", "ticker": "AAPL"}


def test_build_payload_binance() -> None:
    plan = DownloadPlan(thought_process="...", source="binance", symbol="BTCUSDT")
    identifier, payload = DownloaderAgent._build_payload(plan)
    assert identifier == "BTCUSDT"
    assert payload == {"source": "binance", "symbol": "BTCUSDT"}


def test_build_payload_fred() -> None:
    plan = DownloadPlan(thought_process="...", source="fred", series_id="CAUR")
    identifier, payload = DownloaderAgent._build_payload(plan)
    assert identifier == "CAUR"
    assert payload == {"source": "fred", "series_id": "CAUR"}


@pytest.mark.parametrize("stored_identifier", ["gdp_per_capita", "nama_10r_2gdp_abcd", None])
def test_downloader_reports_the_stored_identifier(
    monkeypatch: pytest.MonkeyPatch, stored_identifier: str | None
) -> None:
    plan = DownloadPlan(
        thought_process="...",
        source="eurostat",
        dataset="nama_10r_2gdp",
        filters={"unit": "EUR_HAB"},
    )
    llm = MagicMock()
    llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=plan)
    response = {"success": True, "status": "success", "rows_inserted": 10}
    if stored_identifier is not None:
        response["identifier"] = stored_identifier
    monkeypatch.setattr(graph, "ingest_data", AsyncMock(return_value=response))

    state = cast(
        graph.AgentState, MacroAgentGraph._build_initial_state("Download regional GDP", [])
    )
    state["isolated_worker_task"] = "Download regional GDP"
    result = asyncio.run(DownloaderAgent(llm).ainvoke(state))

    expected_id = stored_identifier or plan.dataset
    assert result["last_worker_status"] == "SUCCESS"
    assert f"identifier={expected_id}," in result["worker_results"][0]


def test_build_payload_missing_field_raises() -> None:
    with pytest.raises(ValueError):
        DownloaderAgent._build_payload(DownloadPlan(thought_process="...", source="yahoo"))
    with pytest.raises(ValueError):
        DownloaderAgent._build_payload(
            DownloadPlan(thought_process="...", source="worldbank", indicator_id="X")
        )
    with pytest.raises(ValueError):
        DownloaderAgent._build_payload(DownloadPlan(thought_process="...", source="fred"))


def _step(query: str, row_count: int) -> dict:
    return {"query": query, "result": {"row_count": row_count}}


def test_detect_yahoo_untracked() -> None:
    steps = [_step("SELECT ticker FROM yahoo_metadata WHERE short_name ILIKE '%palantir%'", 0)]
    assert _detect_market_needs_download(steps) == "yahoo"


def test_detect_binance_untracked() -> None:
    steps = [_step("SELECT symbol FROM binance_metadata WHERE base_asset ILIKE 'LTC'", 0)]
    assert _detect_market_needs_download(steps) == "binance"


def test_detect_suppressed_when_metadata_found() -> None:
    # Asset IS tracked (metadata returned rows) but the price filter was empty —
    # that is a genuine EMPTY, not a download trigger.
    steps = [
        _step("SELECT ticker FROM yahoo_metadata WHERE short_name ILIKE '%apple%'", 1),
        _step("SELECT date FROM yahoo_historical_prices WHERE ticker = 'AAPL'", 0),
    ]
    assert _detect_market_needs_download(steps) is None


def test_detect_none_for_worldbank() -> None:
    steps = [_step("SELECT id FROM world_bank_database_indicators WHERE database_id = 2", 0)]
    assert _detect_market_needs_download(steps) is None
