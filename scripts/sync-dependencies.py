"""Synchronize the backend while remembering installed provider extras."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from contextlib import contextmanager
from importlib.metadata import distributions
from pathlib import Path


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@contextmanager
def synchronization_lock(backend: Path):
    """Keep selection capture and exact sync together across maintenance sessions."""
    with (backend / ".openfic-sync.lock").open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SystemExit(
                "Another dependency sync is running; retry after it finishes."
            ) from None
        # Closing the file releases the operating-system lock, including on failure.
        yield


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extra", action="append", default=[])
    parser.add_argument("--data-path", type=Path, default=root / "data")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with synchronization_lock(root / "backend"):
        return synchronize(root, args, parser)


def synchronize(root: Path, args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    backend = root / "backend"
    state = args.data_path.resolve() / "dependency-extras.json"
    manifest = tomllib.loads((backend / "pyproject.toml").read_text(encoding="utf-8"))
    extras = manifest["project"].get("optional-dependencies", {})
    saved = json.loads(state.read_text(encoding="utf-8")) if state.exists() else []
    if not isinstance(saved, list) or not all(isinstance(item, str) for item in saved):
        parser.error(f"Invalid extras list in {state}")
    selected = set(saved) | set(args.extra)
    unknown = selected - extras.keys()
    if unknown:
        parser.error(f"Unknown provider extras: {', '.join(sorted(unknown))}")

    environment = Path(os.environ.get("UV_PROJECT_ENVIRONMENT", backend / ".venv"))
    if not environment.is_absolute():
        environment = backend / environment
    sites = [environment / "Lib" / "site-packages"]
    sites.extend(environment.glob("lib/python*/site-packages"))
    installed = {
        normalize(dist.metadata["Name"])
        for dist in distributions(path=[str(site) for site in sites])
        if dist.metadata["Name"]
    }
    for extra, requirements in extras.items():
        # Preserve even a partially installed provider; sync repairs its dependencies.
        if any(normalize(re.match(r"[\w.-]+", req)[0]) in installed for req in requirements):
            selected.add(extra)

    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv.exe")
    command = [uv, "sync", "--frozen"]
    for extra in sorted(selected):
        command.extend(["--extra", extra])
    print(f"Provider extras: {', '.join(sorted(selected)) or '(none)'}", flush=True)
    if args.dry_run:
        command.append("--dry-run")
    else:
        # Save before sync: a failed update or a rebuilt venv must not erase intent.
        state.parent.mkdir(parents=True, exist_ok=True)
        temporary = state.with_suffix(".tmp")
        temporary.write_text(json.dumps(sorted(selected), indent=2) + "\n", encoding="utf-8")
        temporary.replace(state)
    return subprocess.run(command, cwd=backend, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
