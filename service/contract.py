"""Lifecycle result data and credential-safe diagnostics, independent of output streams."""

from dataclasses import dataclass, field
from typing import Literal, NotRequired, TypedDict

import psutil

type ServiceState = Literal["running", "stopped", "warning", "unknown"]


class RuntimeRecord(TypedDict):
    """Persisted identity; optional legacy fields are checked by their consumers."""

    pid: int | str
    port: int | str
    started_at: str
    python: str
    data_directory: str
    launcher_pid: NotRequired[int]
    stdout: NotRequired[str]
    stderr: NotRequired[str]
    shutdown_token: NotRequired[object]
    paths: NotRequired[object]


@dataclass(frozen=True)
class Status:
    state: ServiceState
    detail: str
    pid: int | None = None
    busy: bool = False


class ManagerError(Exception):
    def __init__(self, detail: str, state: ServiceState = "unknown", *, busy: bool = False):
        super().__init__(detail)
        self.state: ServiceState = state
        self.busy = busy


@dataclass
class Diagnostics:
    stage: str = "initialization"
    secrets: list[str] = field(default_factory=list)

    def redact(self, detail: str) -> str:
        for secret in self.secrets:
            detail = detail.replace(secret, "[redacted]")
        return detail

    def failure(self, error: Exception, action: str) -> Status:
        if isinstance(error, ManagerError):
            return Status(error.state, self.redact(str(error)), busy=error.busy)
        if isinstance(error, (PermissionError, psutil.AccessDenied)):
            return Status(
                "unknown",
                f"Access denied during {self.stage}. Check filesystem and process "
                f"inspection permissions.",
            )
        return Status(
            "unknown", self.redact(f"OpenFic {action} failed during {self.stage}: {error}")
        )
