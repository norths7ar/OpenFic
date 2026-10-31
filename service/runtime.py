"""Persisted service state, process ownership and read-only instance inspection."""

import json
import os
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import cast
from urllib.request import ProxyHandler, build_opener

import psutil

from .config import Instance, same_path
from .contract import Diagnostics, ManagerError, RuntimeRecord, Status
from .platform import LockBusy, Process, management_lock


def open_local(request, *, timeout: float):
    """Local control requests must not be routed through environment proxies."""
    return build_opener(ProxyHandler({})).open(request, timeout=timeout)


class Runtime:
    def __init__(self, instance: Instance, diagnostics: Diagnostics):
        self.instance = instance
        self.diagnostics = diagnostics
        self.resources = ExitStack()

    def process(self, pid: int) -> Process | None:
        try:
            result = Process(pid)
        except psutil.NoSuchProcess:
            return None
        self.resources.callback(result.close)
        return result

    def listeners(self) -> set[int]:
        """Return listener PIDs, failing when a matching listener's PID is unavailable."""
        self.diagnostics.stage = "listening-port inspection"
        listeners: set[int] = set()
        for connection in psutil.net_connections(kind="tcp"):
            address = connection.laddr
            if connection.status != psutil.CONN_LISTEN or not address:
                continue
            if address.port != self.instance.port:
                continue
            pid = connection.pid
            if pid is None:
                raise ManagerError(
                    "Unable to identify a listening process. Full process visibility is required."
                )
            listeners.add(pid)
        return listeners

    def read_state(self) -> RuntimeRecord | None:
        self.diagnostics.stage = "runtime-state inspection"
        try:
            content = self.instance.state_path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            return None
        try:
            state = json.loads(content)
            if not isinstance(state, dict) or int(str(state["pid"])) <= 0:
                raise ValueError
            int(str(state["port"]))
            datetime.fromisoformat(state["started_at"])
            if any(
                not isinstance(state[name], str) or not state[name].strip()
                for name in ("python", "data_directory")
            ):
                raise ValueError
            if state.get("shutdown_token"):
                self.diagnostics.secrets.append(str(state["shutdown_token"]))
            return cast(RuntimeRecord, state)
        except ValueError, TypeError, KeyError:
            raise ManagerError(
                f"Invalid OpenFic state file: {self.instance.state_path}. Existing state "
                f"was preserved."
            ) from None

    def owned_process(self, state: RuntimeRecord | None) -> Process | None:
        if state is None:
            return None
        self.diagnostics.stage = "process identity inspection"
        process = self.process(int(state["pid"]))
        if process is None:
            return None
        try:
            executable, command = process.info.exe(), process.info.cmdline()
            if not executable or not command:
                raise ManagerError(
                    "OpenFic process identity is not visible. Run the manager with full "
                    "process visibility; existing state was preserved."
                )
            expected_command = ["-m", "app.cli", "serve"]
            command_matches = any(
                command[i : i + 3] == expected_command for i in range(len(command))
            )
            port_matches = any(
                command[i : i + 2] == ["--port", str(self.instance.port)]
                for i in range(len(command))
            )
            recorded_start = datetime.fromisoformat(state["started_at"]).timestamp()
            # .NET writes 100 ns fractions; datetime truncates to microseconds and
            # psutil exposes a float. One microsecond covers only representation loss.
            start_matches = abs(recorded_start - process.created) <= 0.000001
            executable_matches = (
                same_path(executable, self.instance.python)
                or (
                    self.instance.base_python is not None
                    and same_path(executable, self.instance.base_python)
                )
                or Path(executable).resolve() == self.instance.python.resolve()
                or (
                    self.instance.base_python is not None
                    and Path(executable).resolve() == self.instance.base_python.resolve()
                )
            )
            if not (
                same_path(state["python"], self.instance.python)
                and same_path(state["data_directory"], self.instance.data)
                and int(state["port"]) == self.instance.port
                and start_matches
                and executable_matches
                and command_matches
                and port_matches
            ):
                raise ManagerError(
                    "Recorded PID does not identify this OpenFic service. Refusing to manage it.",
                    "warning",
                )
            if process.exited:
                return None
            return process
        except psutil.NoSuchProcess:
            return None

    def healthy(self) -> bool:
        try:
            with open_local(self.instance.health_url, timeout=2) as response:
                return json.load(response).get("status") == "healthy"
        except Exception:
            return False

    def publish_state(self, state: RuntimeRecord):
        # This is a runtime transaction record, not a development scratch file.
        # Keep it beside the committed state for atomic replacement on any volume.
        # The management lock serializes writers; readers only trust openfic.json.
        path = self.instance.runtime_directory / "openfic.pending.json"
        try:
            with path.open("w", encoding="utf-8") as stream:
                json.dump(state, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(path, self.instance.state_path)
        finally:
            path.unlink(missing_ok=True)

    def status(self, *, lock_held=False) -> Status:
        self.diagnostics.stage = "management-lock inspection"
        if not lock_held:
            try:
                with management_lock(self.instance.lock_path, probe=True):
                    pass
            except FileNotFoundError:
                pass
            except LockBusy:
                return Status(
                    "warning",
                    "Another lifecycle or backup operation holds the OpenFic management lock.",
                    busy=True,
                )
        state = self.read_state()
        try:
            process = self.owned_process(state)
        except ManagerError as error:
            if error.state != "warning":
                raise
            return self.diagnostics.failure(error, "status")
        listeners = self.listeners()
        if process and process.pid in listeners and self.healthy():
            return Status(
                "running", "Process identity, listening port and health check passed.", process.pid
            )
        if process:
            return Status(
                "warning",
                "The managed process is alive but its listening port or health check failed.",
                process.pid,
            )
        if listeners or self.healthy():
            return Status(
                "warning",
                "The service port is reachable without a verified owned process. "
                "Existing state was preserved.",
            )
        return Status(
            "stopped", "No managed process, listening port or healthy endpoint was found."
        )
