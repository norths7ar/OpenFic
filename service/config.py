"""Instance configuration and managed-path validation, without service operations."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .contract import ManagerError

PATH_SETTINGS = (
    "COVERS_DIR",
    "CHARACTER_IMAGES_DIR",
    "AGENT_ATTACHMENTS_DIR",
    "CHAPTER_EXPORTS_DIR",
    "STATIC_DIR",
    "AGENT_CHECKPOINT_DB",
)


def absolute(value: str | Path) -> Path:
    # Preserve lexical paths in the existing runtime contract (do not follow links).
    return Path(os.path.abspath(value))


def same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(str(absolute(left))) == os.path.normcase(str(absolute(right)))


@dataclass(frozen=True)
class Instance:
    root: Path
    data: Path
    port: int = 18081
    base_python: Path | None = field(init=False, default=None)

    def __post_init__(self):
        config = self.backend / ".venv/pyvenv.cfg"
        if config.exists():
            for line in config.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if separator and key.strip() == "home":
                    object.__setattr__(
                        self,
                        "base_python",
                        absolute(
                            Path(value.strip()) / ("python.exe" if os.name == "nt" else "python")
                        ),
                    )
                    break

    @property
    def backend(self) -> Path:
        return self.root / "backend"

    @property
    def python(self) -> Path:
        return self.backend / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    @property
    def runtime_directory(self) -> Path:
        return self.data / "runtime"

    @property
    def state_path(self) -> Path:
        return self.runtime_directory / "openfic.json"

    @property
    def lock_path(self) -> Path:
        return self.runtime_directory / "openfic.lock"

    @property
    def frontend(self) -> Path:
        return self.root / "frontend/dist"

    @property
    def health_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/api/v1/health"

    @classmethod
    def from_arguments(cls, data_path: str | None, port: int):
        root = Path(__file__).resolve().parents[1]
        return cls(root, absolute(data_path) if data_path else root / "data", port)


def managed_paths(values: object) -> dict[str, str]:
    result = {}
    for name in PATH_SETTINGS:
        value = values.get(name) if isinstance(values, dict) else None
        if not isinstance(value, str) or not value.strip() or not Path(value).is_absolute():
            raise ManagerError(f"Managed path setting is missing or not absolute: {name}")
        result[name] = str(absolute(value))
    return result


def restored_paths(environment_path: str, data: Path) -> dict[str, str]:
    path = absolute(environment_path)
    root = path.parent
    if path.name != "restore-environment.json":
        raise ManagerError(
            "Restore environment must be the generated restore-environment.json file."
        )
    try:
        values = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError:
        raise ManagerError("Restore environment is not valid JSON.") from None
    if (
        not isinstance(values, dict)
        or not values.get("OPENFIC_DATA_DIR")
        or not (
            same_path(values["OPENFIC_DATA_DIR"], root / "data") and same_path(data, root / "data")
        )
    ):
        raise ManagerError("Restored environment does not match the restored data directory.")
    for name, value in values.items():
        if name not in ("OPENFIC_DATA_DIR", *PATH_SETTINGS):
            raise ManagerError("Restore environment contains an unsupported setting.")
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ManagerError(f"Managed path setting is missing or not absolute: {name}")
        target = absolute(value)
        if not target.is_relative_to(root) or not target.resolve().is_relative_to(root.resolve()):
            raise ManagerError(f"Restored environment points outside the restore directory: {name}")
        if target.is_symlink() or target.is_junction():
            raise ManagerError(f"Restored environment path cannot be a link: {name}")
    return managed_paths(values)
