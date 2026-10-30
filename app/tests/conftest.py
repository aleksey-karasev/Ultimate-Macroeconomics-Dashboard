"""Shared fixtures for the app smoke suite.

A minimal config stub is created before test modules are imported because some
app modules load ``config.yaml`` at import time. ``theming.py`` looks for
``themes.yaml`` in a small set of locations; tests point it at the bundled
``_container_data/themes.yaml`` via cwd.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_STUB = """\
whisper: {}
"""


def _ensure_config_file() -> None:
    config_path = Path.cwd() / "config.yaml"
    if not config_path.is_file():
        config_path.write_text(_STUB, encoding="utf-8")


_ensure_config_file()


@pytest.fixture(autouse=True)
def _cwd_in_container_data(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    themes_path = repo_root / "_container_data" / "themes.yaml"
    if not themes_path.is_file():
        pytest.skip(f"themes.yaml not found at {themes_path}")
    monkeypatch.chdir(themes_path.parent)
    # Streamlit needs HOME to be writable for its caching backend.
    monkeypatch.setenv("HOME", os.environ.get("HOME", str(repo_root)))
