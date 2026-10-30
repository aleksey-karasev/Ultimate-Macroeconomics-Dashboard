"""Regression tests for indicator-card edge cases."""

from contextlib import nullcontext

from core import plotting
import polars as pl
import pytest


def test_graphbox_empty_history_shows_warning_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plotting, "get_world_bank_indicator_name", lambda *args, **kwargs: "")
    box = plotting.GraphBox({"id": "TEST.INDICATOR", "name": "Test indicator"})
    monkeypatch.setattr(box, "_fetch_data", lambda: pl.DataFrame())
    monkeypatch.setattr(box, "_render_header_and_settings", lambda defaults: defaults)
    monkeypatch.setattr(plotting.st, "container", lambda **kwargs: nullcontext())
    warnings: list[str] = []
    monkeypatch.setattr(plotting.st, "warning", warnings.append)

    getattr(plotting.GraphBox.render_streamlit_ui, "__wrapped__")(box)

    assert warnings == ["No data available for Test indicator."]
