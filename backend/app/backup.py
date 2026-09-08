"""Offline, checksummed application snapshots. No application/settings imports."""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values

PATH_SETTINGS = {
    "COVERS_DIR": "covers",
    "CHARACTER_IMAGES_DIR": "character-images",
    "AGENT_ATTACHMENTS_DIR": "agent-attachments",
    "CHAPTER_EXPORTS_DIR": "chapter-exports",
    "STATIC_DIR": ".",
    "AGENT_CHECKPOINT_DB": "checkpoints.db",
}


def configured_paths(
    data: Path, repository: Path, saved_paths: dict[str, str] | None = None
) -> dict[str, Path]:
    """Resolve the paths used by a managed service or by a direct offline backup."""
    data, repository = data.resolve(), repository.resolve()
    if saved_paths is not None:
        if set(saved_paths) != set(PATH_SETTINGS):
            raise ValueError("Managed service state has an incomplete path configuration")
        if any(not Path(value).expanduser().is_absolute() for value in saved_paths.values()):
            raise ValueError("Managed service state contains a relative path")
        paths = {key: Path(value).expanduser().resolve() for key, value in saved_paths.items()}
    else:
        config = {key.upper(): value for key, value in dotenv_values(data / ".env").items()}
        config.update({key.upper(): value for key, value in os.environ.items()})
        paths = {}
        for key, default in PATH_SETTINGS.items():
            # AGENT_CHECKPOINT_DB is read from os.environ, not the application's dotenv settings.
            value = os.environ.get(key) if key == "AGENT_CHECKPOINT_DB" else config.get(key)
            path = Path(value).expanduser() if value else data / default
            paths[key] = (
                (repository / "backend" / path).resolve()
                if not path.is_absolute()
                else path.resolve()
            )
    return paths


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def files(root: Path) -> list[Path]:
    result = []
    for path in root.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Linked paths are not supported in snapshots: {path}")
        if path.is_file():
            result.append(path)
    return sorted(result)


def copy_file(source: Path, destination: Path) -> None:
    if source.is_symlink() or source.is_junction():
        raise ValueError(f"Linked source is not supported: {source}")
    before = source.stat()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"Source changed during backup: {source}")


def copy_tree(source: Path, destination: Path, *, exclude: set[str] | None = None) -> None:
    destination.mkdir(parents=True)
    source_files = files(source)
    for directory in source.rglob("*"):
        if directory.is_dir():
            (destination / directory.relative_to(source)).mkdir(parents=True, exist_ok=True)
    for path in source_files:
        if exclude and path.relative_to(source).as_posix() in exclude:
            continue
        copy_file(path, destination / path.relative_to(source))


def database_revision(data: Path) -> str:
    with sqlite3.connect((data / "openfic.db").as_uri() + "?mode=ro", uri=True) as conn:
        if conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError("Application database integrity check failed")
        return conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def create_snapshot(
    data: Path,
    destination: Path,
    repository: Path,
    browser: Path | None = None,
    saved_paths: dict[str, str] | None = None,
) -> Path:
    """Caller must hold the service management lock and stop all data writers."""
    data, destination, repository = data.resolve(), destination.resolve(), repository.resolve()
    if os.environ.get("ENCRYPTION_KEY"):
        raise ValueError(
            "Process ENCRYPTION_KEY is not supported for managed snapshots; "
            "store it in the data directory .env instead"
        )
    if destination.exists() or destination.is_relative_to(data):
        raise ValueError("Backup destination must be new and outside the data directory")
    if (data / "runtime" / "openfic.json").exists():
        raise ValueError("Stop the managed service before taking a snapshot")
    browser_metadata = None
    if browser:
        browser_metadata = json.loads(browser.read_text(encoding="utf-8-sig"))
        if (
            browser_metadata.get("format") != "openfic-browser-backup"
            or browser_metadata.get("version") != 1
            or browser_metadata.get("database", {}).get("name") != "OpenFicDB"
        ):
            raise ValueError("Not an OpenFic browser companion package")
    revision = database_revision(data)
    paths = configured_paths(data, repository, saved_paths)
    for key, path in paths.items():
        if destination.is_relative_to(path):
            raise ValueError(f"Backup destination lies inside {key}")
    destination.mkdir(parents=True)
    # A failed backup deliberately has no manifest and cannot be restored.
    copy_tree(data, destination / "data", exclude={"runtime/openfic.lock"})
    overrides = {}
    for key, path in paths.items():
        if path.is_relative_to(data):
            overrides[key] = "data/" + path.relative_to(data).as_posix()
        else:
            relative = f"external/{key}/{path.name}"
            target = destination / relative
            if path.is_dir():
                copy_tree(path, target)
            elif path.is_file():
                copy_file(path, target)
                if key == "AGENT_CHECKPOINT_DB":
                    for suffix in ("-wal", "-shm"):
                        sidecar = Path(str(path) + suffix)
                        if sidecar.exists():
                            copy_file(sidecar, Path(str(target) + suffix))
            elif key != "AGENT_CHECKPOINT_DB":
                target.mkdir(parents=True)
            else:
                raise ValueError("Configured external checkpoint database is missing")
            overrides[key] = relative
    # A key in data/.env is the only supported override; process-level overrides are rejected.
    effective_key = dotenv_values(data / ".env").get("ENCRYPTION_KEY")
    if effective_key:
        (destination / "data" / ".key").write_text(effective_key, encoding="utf-8")
    tracked = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=repository
        )
        .decode("utf-8")
        .split("\0")
    )
    for name in sorted(set(tracked)):
        if not name:
            continue
        source = repository / name
        if source.is_file():
            copy_file(source, destination / "source" / name)
    built = repository / "frontend" / "dist"
    if built.exists():
        copy_tree(built, destination / "source" / "frontend" / "dist")
    if browser:
        copy_file(browser, destination / "browser.json")
    manifest = {
        "format": "openfic-full-snapshot",
        "version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "schema_revision": revision,
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repository, text=True
        ).strip(),
        "source_is_working_tree": True,
        "browser_included": browser is not None,
        "browser_exported_at": browser_metadata.get("exportedAt") if browser_metadata else None,
        "paths": overrides,
        "files": {p.relative_to(destination).as_posix(): digest(p) for p in files(destination)},
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return destination


def verify_snapshot(snapshot: Path) -> dict:
    snapshot = snapshot.resolve()
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "openfic-full-snapshot" or manifest.get("version") != 1:
        raise ValueError("Unsupported snapshot format")
    actual = {p.relative_to(snapshot).as_posix() for p in files(snapshot)} - {"manifest.json"}
    if actual != set(manifest["files"]):
        raise ValueError("Snapshot file inventory mismatch")
    for name, checksum in manifest["files"].items():
        path = (snapshot / name).resolve()
        if not path.is_relative_to(snapshot) or digest(path) != checksum:
            raise ValueError(f"Snapshot checksum mismatch: {name}")
    for relative in manifest["paths"].values():
        if not (snapshot / relative).resolve().is_relative_to(snapshot):
            raise ValueError("Snapshot contains an invalid data path")
    return manifest


def restore_snapshot(snapshot: Path, destination: Path) -> Path:
    snapshot, destination = snapshot.resolve(), destination.resolve()
    if destination.exists() or destination.is_relative_to(snapshot):
        raise ValueError("Restore destination must be a new directory outside the snapshot")
    manifest = verify_snapshot(snapshot)
    copy_tree(snapshot, destination)
    runtime = destination / "data" / "runtime"
    # Runtime identity is never restored; do not carry a stale shutdown token/PID into a new service.
    for name in ("openfic.json", "openfic.lock"):
        (runtime / name).unlink(missing_ok=True)
    overrides = {key: str(destination / value) for key, value in manifest["paths"].items()}
    overrides["OPENFIC_DATA_DIR"] = str(destination / "data")
    # Keep a relocatable source copy, and an explicit runtime environment for isolated startup.
    (destination / "restore-environment.json").write_text(
        json.dumps(overrides, indent=2), encoding="utf-8"
    )
    env_path = destination / "data" / ".env"
    current = dict(dotenv_values(env_path))
    current.update(overrides)
    # The copied .key is the effective key, including an original process-level override.
    current.pop("ENCRYPTION_KEY", None)
    env_path.write_text(
        "\n".join(
            f"{key}={json.dumps(value)}" for key, value in current.items() if value is not None
        )
        + "\n",
        encoding="utf-8",
    )
    if database_revision(destination / "data") != manifest["schema_revision"]:
        raise ValueError("Restored database revision differs from snapshot")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "paths", "verify", "restore"])
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--browser", type=Path)
    parser.add_argument("--paths-file", type=Path)
    args = parser.parse_args()
    if args.action == "create":
        if args.data is None or args.repository is None or args.snapshot is None:
            parser.error("create requires --data, --repository, and --snapshot")
        saved_paths = None
        if args.paths_file:
            saved_paths = json.loads(args.paths_file.read_text(encoding="utf-8"))
        create_snapshot(args.data, args.snapshot, args.repository, args.browser, saved_paths)
    elif args.action == "paths":
        if args.data is None or args.repository is None:
            parser.error("paths requires --data and --repository")
        print(
            json.dumps(
                {
                    key: str(value)
                    for key, value in configured_paths(args.data, args.repository).items()
                }
            )
        )
        return
    elif args.action == "verify":
        if args.snapshot is None:
            parser.error("verify requires --snapshot")
        verify_snapshot(args.snapshot)
    else:
        if args.snapshot is None or args.destination is None:
            parser.error("restore requires --snapshot and --destination")
        restore_snapshot(args.snapshot, args.destination)
    print(f"Snapshot {args.action} completed.")


if __name__ == "__main__":
    main()
