"""Tests for the manual Qdrant recovery instructions."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import restore


def test_qdrant_recovery_mounts_snapshot_and_stops_live_server(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot = "full-snapshot-test.snapshot"
    local = Path("_container_data/restore") / snapshot
    config = SimpleNamespace(
        backup=SimpleNamespace(
            rclone_config_path="_container_data/rclone.conf",
            rclone_remote="remote",
            rclone_path="backups",
        )
    )
    monkeypatch.setattr(restore, "load_config", lambda _: config)
    monkeypatch.setattr(restore, "_download", lambda *args: local)

    restore._restore_qdrant(snapshot, local.parent)
    output = capsys.readouterr().out

    assert "docker compose stop app agent vector_db" in output
    assert f"$(pwd)/_container_data/backup/restore/{snapshot}" in output
    assert f"/qdrant/snapshots/{snapshot}:ro" in output
    assert "docker cp" not in output
