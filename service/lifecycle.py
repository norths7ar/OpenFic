"""Start, authenticated stop and restart of an owned OpenFic process."""

import os
import secrets
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.error import HTTPError
from urllib.request import Request

import psutil

from .config import managed_paths, restored_paths
from .contract import Diagnostics, ManagerError, RuntimeRecord
from .platform import Process, terminate_launched_tree
from .runtime import Runtime, open_local
from .snapshot import configured_paths


@dataclass
class ShutdownProgress:
    process: Process | None = None
    request_state: Literal["not_sent", "uncertain", "accepted", "rejected"] = "not_sent"


class Lifecycle:
    def __init__(
        self,
        runtime: Runtime,
        diagnostics: Diagnostics,
        *,
        restore_environment_path: str | None = None,
        report: Callable[[str], None] = print,
    ):
        self.runtime = runtime
        self.instance = runtime.instance
        self.diagnostics = diagnostics
        self.restore_environment_path = restore_environment_path
        self.report = report

    def start(self, saved_paths: dict[str, str] | None = None):
        existing = self.runtime.owned_process(self.runtime.read_state())
        listeners = self.runtime.listeners()
        if existing:
            if existing.pid in listeners and self.runtime.healthy():
                self.report(
                    f"OpenFic is already running. PID: {existing.pid}. "
                    f"http://127.0.0.1:{self.instance.port}/"
                )
                return
            raise ManagerError(
                "The managed OpenFic process is alive but not healthy. Check logs or "
                "stop it first.",
                "warning",
            )
        if listeners:
            raise ManagerError(
                f"Port {self.instance.port} is occupied by unmanaged PID(s): "
                f"{', '.join(map(str, sorted(listeners)))}.",
                "warning",
            )
        if self.runtime.healthy():
            raise ManagerError(
                "OpenFic is reachable but its process ownership cannot be verified. "
                "Existing state was preserved.",
                "warning",
            )
        if not self.instance.python.is_file():
            raise ManagerError(f"Run uv sync --frozen in backend first: {self.instance.python}")
        if os.environ.get("ENCRYPTION_KEY", "").strip():
            raise ManagerError(
                f"Process ENCRYPTION_KEY is not supported by the managed service. Store "
                f"it in {self.instance.data / '.env'} instead."
            )
        if not (self.instance.frontend / "index.html").is_file():
            raise ManagerError("Run pnpm build in frontend before starting OpenFic.")
        self.diagnostics.stage = "managed-path resolution"
        if saved_paths is not None:
            paths = managed_paths(saved_paths)
        elif self.restore_environment_path:
            paths = restored_paths(self.restore_environment_path, self.instance.data)
        else:
            paths = configured_paths(self.instance, self.diagnostics.redact)
        launcher, stdout, stderr, token = self._launch(paths)
        launched_identity = psutil.Process(launcher.pid)
        complete = False
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                time.sleep(0.25)
                if launcher.poll() is not None:
                    raise ManagerError(f"OpenFic exited during startup. See {stderr}")
                listeners = self.runtime.listeners()
                if len(listeners) != 1 or not self.runtime.healthy():
                    continue
                listener = self.runtime.process(next(iter(listeners)))
                if listener is None:
                    continue
                if listener.pid != launcher.pid and listener.info.ppid() != launcher.pid:
                    raise ManagerError(
                        "Port was claimed by a different process during startup.",
                        "warning",
                    )
                state = RuntimeRecord(
                    pid=listener.pid,
                    launcher_pid=launcher.pid,
                    started_at=datetime.fromtimestamp(listener.created, UTC).isoformat(),
                    python=str(self.instance.python),
                    data_directory=str(self.instance.data),
                    port=self.instance.port,
                    stdout=str(stdout),
                    stderr=str(stderr),
                    shutdown_token=token,
                    paths=paths,
                )
                if self.runtime.owned_process(state) is None:
                    raise ManagerError(f"OpenFic exited during startup. See {stderr}")
                self.diagnostics.stage = "runtime-state publication"
                self.runtime.publish_state(state)
                complete = True
                self.report(
                    f"OpenFic started in background. PID: {listener.pid}. "
                    f"http://127.0.0.1:{self.instance.port}/"
                )
                return
            raise ManagerError(f"OpenFic did not become healthy within 45 seconds. See {stderr}")
        finally:
            if not complete:
                terminate_launched_tree(launched_identity)
                launcher.wait(timeout=5)

    def _launch(self, paths: dict[str, str]):
        """Launch detached with only explicit log handles, never caller capture pipes."""
        self.diagnostics.stage = "service startup"
        logs = self.instance.data / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        stdout, stderr = (
            logs / f"openfic-{stamp}.stdout.log",
            logs / f"openfic-{stamp}.stderr.log",
        )
        token = secrets.token_hex(32).upper()
        self.diagnostics.secrets.append(token)
        environment = (
            os.environ
            | paths
            | {
                "OPENFIC_DATA_DIR": str(self.instance.data),
                "OPENFIC_FRONTEND_DIST": str(self.instance.frontend),
                "OPENFIC_SHUTDOWN_TOKEN": token,
                "PYTHONUNBUFFERED": "1",
                "PYTHONIOENCODING": "utf-8",
            }
        )
        with (
            stdout.open("ab", buffering=0) as out,
            stderr.open("ab", buffering=0) as err,
        ):
            launcher = subprocess.Popen(
                [
                    str(self.instance.python),
                    "-m",
                    "app.cli",
                    "serve",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self.instance.port),
                ],
                cwd=self.instance.backend,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                close_fds=True,
                creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
                if os.name == "nt"
                else 0,
                start_new_session=os.name != "nt",
            )
        return launcher, stdout, stderr, token

    def stop(self, progress: ShutdownProgress | None = None):
        progress = progress if progress is not None else ShutdownProgress()
        progress.request_state = "not_sent"
        state = self.runtime.read_state()
        process = self.runtime.owned_process(state)
        progress.process = process
        if process is None or state is None:
            if self.runtime.healthy() or self.runtime.listeners():
                raise ManagerError(
                    "The service port is reachable without a verified owned process; "
                    "refusing to stop it. Existing state was preserved.",
                    "warning",
                )
            self.report("OpenFic is not running.")
            return
        if process.pid not in self.runtime.listeners():
            raise ManagerError(
                "Managed process is not listening; inspect logs before stopping it manually.",
                "warning",
            )
        self.diagnostics.stage = "authenticated graceful shutdown"
        token = state.get("shutdown_token")
        if not isinstance(token, str) or not token.strip():
            raise ManagerError(
                "The managed state has no shutdown credential. Existing state was preserved."
            )
        progress.request_state = "uncertain"
        request = Request(
            self.instance.health_url + "/shutdown",
            method="POST",
            headers={"X-OpenFic-Shutdown-Token": token},
        )
        try:
            with open_local(request, timeout=5):
                pass
            progress.request_state = "accepted"
        except Exception as error:
            if isinstance(error, HTTPError) and error.code in (
                400,
                401,
                403,
                404,
                405,
                422,
            ):
                progress.request_state = "rejected"
            raise ManagerError(
                "OpenFic graceful shutdown request failed. Check authentication, "
                "connectivity and service logs; existing state was preserved."
            ) from None
        if not process.wait(30):
            raise ManagerError(
                f"OpenFic has not finished shutting down. PID: {process.pid}. No forced "
                f"termination was performed.",
                "warning",
            )
        if self.runtime.listeners() or self.runtime.healthy():
            raise ManagerError(
                "The managed process exited, but the service port is still reachable. "
                "Existing state was preserved.",
                "warning",
            )
        self.diagnostics.stage = "runtime-state removal"
        self.instance.state_path.unlink()
        self.report(f"OpenFic stopped gracefully. PID: {process.pid}.")

    def restart(self):
        state = self.runtime.read_state()
        saved_paths = state.get("paths") if state is not None else None
        paths = managed_paths(saved_paths) if saved_paths is not None else None
        self.stop()
        self.start(paths)
