"""Tests for fail-closed initial ingestion before the completion marker."""

from types import SimpleNamespace

from main import INGEST_ORDER, run_initial_ingest
import pytest


def _downloaders(calls: list[str], fail_init: str | None = None) -> dict:
    result = {}
    for name in INGEST_ORDER:

        def init(name: str = name) -> bool:
            calls.append(f"init:{name}")
            return name != fail_init

        downloader = SimpleNamespace(run=lambda name=name: calls.append(f"run:{name}"))
        result[name] = (downloader, init)
    return result


def test_initial_ingest_runs_every_source_in_order() -> None:
    calls: list[str] = []
    run_initial_ingest(_downloaders(calls))

    assert calls == [call for name in INGEST_ORDER for call in (f"init:{name}", f"run:{name}")]


def test_initial_ingest_fails_instead_of_skipping_unavailable_source() -> None:
    calls: list[str] = []
    with pytest.raises(RuntimeError, match="news"):
        run_initial_ingest(_downloaders(calls, fail_init="news"))

    assert "run:news" not in calls
    assert not any(call.endswith("yahoo") for call in calls)
