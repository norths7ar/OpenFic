"""Offline restore must preserve data and refuse damaged or overwriting restores."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from app.backup import (
    PATH_SETTINGS,
    configured_paths,
    create_snapshot,
    restore_snapshot,
    verify_snapshot,
)


def source(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    data = repo / "data"
    data.mkdir(parents=True)
    (repo / "backend").mkdir()
    (repo / "README.md").write_text("working tree", encoding="utf-8")
    (data / ".key").write_text("test-key", encoding="utf-8")
    (data / "empty-folder").mkdir()
    with sqlite3.connect(data / "openfic.db") as conn:
        conn.execute("CREATE TABLE alembic_version (version_num TEXT)")
        conn.execute("INSERT INTO alembic_version VALUES ('1035')")
    return repo, data


def git_output(command, **kwargs):
    return "test-commit\n" if kwargs.get("text") else b"README.md\0"


def test_round_trip_preserves_data_and_source(tmp_path):
    repo, data = source(tmp_path)
    snapshot, restored = tmp_path / "snapshot", tmp_path / "restored"
    with patch("app.backup.subprocess.check_output", side_effect=git_output):
        create_snapshot(data, snapshot, repo)
    assert verify_snapshot(snapshot)["browser_included"] is False
    restore_snapshot(snapshot, restored)
    assert (restored / "data" / ".key").read_text() == "test-key"
    assert (restored / "source" / "README.md").read_text() == "working tree"
    assert (restored / "data" / "empty-folder").is_dir()
    env = json.loads((restored / "restore-environment.json").read_text())
    assert all(Path(value).is_relative_to(restored) for value in env.values())
    with pytest.raises(ValueError, match="new directory"):
        restore_snapshot(snapshot, restored)


def test_tampering_is_rejected_before_creating_destination(tmp_path):
    repo, data = source(tmp_path)
    snapshot, restored = tmp_path / "snapshot", tmp_path / "restored"
    with patch("app.backup.subprocess.check_output", side_effect=git_output):
        create_snapshot(data, snapshot, repo)
    (snapshot / "data" / ".key").write_text("modified")
    with pytest.raises(ValueError, match="checksum"):
        restore_snapshot(snapshot, restored)
    assert not restored.exists()


def test_external_paths_relocate_and_effective_key_survives(tmp_path, monkeypatch):
    repo, data = source(tmp_path)
    covers = tmp_path / "external-covers"
    covers.mkdir()
    (covers / "image.png").write_bytes(b"image")
    monkeypatch.setenv("COVERS_DIR", str(covers))
    (data / ".env").write_text("ENCRYPTION_KEY=effective-key\n", encoding="utf-8")
    snapshot, restored = tmp_path / "snapshot", tmp_path / "restored"
    with patch("app.backup.subprocess.check_output", side_effect=git_output):
        create_snapshot(data, snapshot, repo)
    restore_snapshot(snapshot, restored)
    env = json.loads((restored / "restore-environment.json").read_text())
    assert Path(env["COVERS_DIR"]).is_relative_to(restored)
    assert (Path(env["COVERS_DIR"]) / "image.png").read_bytes() == b"image"
    assert (restored / "data" / ".key").read_text() == "effective-key"


def test_process_encryption_key_is_rejected_for_a_recoverable_snapshot(tmp_path, monkeypatch):
    repo, data = source(tmp_path)
    monkeypatch.setenv("ENCRYPTION_KEY", "process-only-key")
    with pytest.raises(ValueError, match="Process ENCRYPTION_KEY"):
        create_snapshot(data, tmp_path / "snapshot", repo)


def test_saved_service_paths_override_the_backup_invocation_environment(tmp_path, monkeypatch):
    repo, data = source(tmp_path)
    active_covers = tmp_path / "active-covers"
    active_covers.mkdir()
    (active_covers / "image.png").write_bytes(b"active")
    other_covers = tmp_path / "other-covers"
    other_covers.mkdir()
    monkeypatch.setenv("COVERS_DIR", str(other_covers))
    saved_paths = {key: str(data / default) for key, default in PATH_SETTINGS.items()}
    saved_paths["COVERS_DIR"] = str(active_covers)
    snapshot, restored = tmp_path / "snapshot", tmp_path / "restored"
    with patch("app.backup.subprocess.check_output", side_effect=git_output):
        create_snapshot(data, snapshot, repo, saved_paths=saved_paths)
    restore_snapshot(snapshot, restored)
    assert (
        restored / "external" / "COVERS_DIR" / "active-covers" / "image.png"
    ).read_bytes() == b"active"
    assert configured_paths(data, repo, saved_paths)["COVERS_DIR"] == active_covers


def test_snapshot_includes_its_start_script_for_matching_source(tmp_path):
    repo, data = source(tmp_path)
    script = repo / "scripts" / "openfic-service.ps1"
    script.parent.mkdir()
    script.write_text("# snapshot launcher", encoding="utf-8")
    snapshot = tmp_path / "snapshot"

    def tracked(command, **kwargs):
        return (
            "test-commit\n" if kwargs.get("text") else b"README.md\0scripts/openfic-service.ps1\0"
        )

    with patch("app.backup.subprocess.check_output", side_effect=tracked):
        create_snapshot(data, snapshot, repo)
    assert (snapshot / "source" / "scripts" / "openfic-service.ps1").is_file()


def test_managed_path_state_must_be_complete_and_absolute(tmp_path):
    repo, data = source(tmp_path)
    with pytest.raises(ValueError, match="incomplete"):
        configured_paths(data, repo, {"COVERS_DIR": str(data / "covers")})
    relative_paths = {key: str(data / default) for key, default in PATH_SETTINGS.items()}
    relative_paths["COVERS_DIR"] = "covers"
    with pytest.raises(ValueError, match="relative"):
        configured_paths(data, repo, relative_paths)


def test_running_service_and_recursive_destination_rejected(tmp_path):
    repo, data = source(tmp_path)
    (data / "runtime").mkdir()
    (data / "runtime" / "openfic.json").write_text("{}")
    with pytest.raises(ValueError, match="Stop"):
        create_snapshot(data, tmp_path / "snapshot", repo)
    with pytest.raises(ValueError, match="outside"):
        create_snapshot(data, data / "snapshot", repo)
