"""Adapter to the backend snapshot CLI; does not import or initialize the web app."""

import json
import os
import subprocess
from collections.abc import Callable

from .config import Instance, managed_paths
from .contract import ManagerError


def invoke(
    instance: Instance, arguments: list[str], context: str, redact: Callable[[str], str]
) -> str:
    result = subprocess.run(
        [str(instance.python), "-m", "app.backup", *arguments],
        cwd=instance.backend,
        env=os.environ | {"PYTHONIOENCODING": "utf-8"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode:
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        reason = f": {redact(lines[-1])}" if lines else ""
        raise ManagerError(f"{context} (exit {result.returncode}){reason}")
    return result.stdout


def configured_paths(instance: Instance, redact: Callable[[str], str]) -> dict[str, str]:
    output = invoke(
        instance,
        ["paths", "--data", str(instance.data), "--repository", str(instance.root)],
        "Unable to resolve the managed data paths",
        redact,
    )
    try:
        values = json.loads(output)
    except ValueError:
        raise ManagerError("Managed path resolution did not return valid JSON.") from None
    return managed_paths(values)
