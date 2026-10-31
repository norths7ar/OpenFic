"""Snapshot operations and restoration of the original service after backup."""

import json
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .config import absolute, managed_paths
from .contract import Diagnostics, ManagerError, RuntimeRecord
from .lifecycle import Lifecycle, ShutdownProgress
from .platform import Process
from .runtime import Runtime
from .snapshot import configured_paths, invoke


class Backup:
    def __init__(
        self,
        runtime: Runtime,
        lifecycle: Lifecycle,
        diagnostics: Diagnostics,
        *,
        report: Callable[[str], None] = print,
    ):
        self.runtime = runtime
        self.instance = runtime.instance
        self.diagnostics = diagnostics
        self.report = report
        self.lifecycle = lifecycle

    def snapshot(self, arguments: list[str]):
        self.diagnostics.stage = f"snapshot {arguments[0]}"
        try:
            invoke(self.instance, arguments, "Snapshot operation failed", self.diagnostics.redact)
        except ManagerError as error:
            raise ManagerError(f"{error}; formal data was not replaced.") from None
        self.report(f"Snapshot {arguments[0]} completed.")

    def restore(self, snapshot_path: str | None, restore_path: str | None):
        if not snapshot_path or not restore_path:
            raise ManagerError(
                "restore requires --snapshot-path and --restore-path (a new directory)."
            )
        destination = absolute(restore_path)
        self.snapshot(
            [
                "restore",
                "--snapshot",
                str(absolute(snapshot_path)),
                "--destination",
                str(destination),
            ]
        )
        self.report(
            f"Restored to {destination}. First restore dependencies (including the "
            f"default deployment group):"
        )
        self.report(f'uv sync --frozen --project "{destination / "source/backend"}"')
        self.report(f'cd "{destination / "source"}"')
        self.report(
            f"uv run --no-sync --project backend python -m service start "
            f'--data-path "{destination / "data"}" '
            f'--restore-environment-path "{destination / "restore-environment.json"}" '
            "--port 18082"
        )

    def backup(self, snapshot_path: str | None = None, browser_backup_path: str | None = None):
        destination = (
            absolute(snapshot_path)
            if snapshot_path
            else (
                self.instance.root / "output/backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            )
        )
        arguments = [
            "create",
            "--data",
            str(self.instance.data),
            "--repository",
            str(self.instance.root),
            "--snapshot",
            str(destination),
        ]
        if browser_backup_path:
            arguments += ["--browser", str(absolute(browser_backup_path))]
        state = self.runtime.read_state()
        original = self.runtime.owned_process(state)
        self.diagnostics.stage = "managed-path resolution"
        saved_paths = state.get("paths") if state is not None else None
        paths = (
            managed_paths(saved_paths)
            if saved_paths is not None
            else configured_paths(self.instance, self.diagnostics.redact)
        )
        temporary = None
        stop_attempted = stop_completed = False
        progress = ShutdownProgress(process=original)
        failures = []
        try:
            self.diagnostics.stage = "backup path staging"
            scratch = self.instance.root / ".tmp"
            scratch.mkdir(exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=scratch,
                prefix=datetime.now().strftime("%Y%m%d-openfic-backup-paths-"),
                suffix=".json",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(paths, stream)
            arguments += ["--paths-file", str(temporary)]
            stop_attempted = True
            self.lifecycle.stop(progress)
            stop_completed = True
            self.snapshot(arguments)
        except Exception as error:
            failures.append(self.diagnostics.failure(error, "backup").detail)
        finally:
            if original is not None and stop_attempted:
                try:
                    self._recover(state, original, paths, progress, stop_completed)
                except Exception as error:
                    failures.append(
                        "Recovery after backup failed: "
                        + self.diagnostics.failure(error, "backup").detail
                    )
            if temporary is not None:
                self.diagnostics.stage = "backup temporary-file cleanup"
                try:
                    temporary.unlink(missing_ok=True)
                except Exception as error:
                    failures.append(self.diagnostics.failure(error, "backup").detail)
        if failures:
            raise ManagerError(" ".join(failures))
        self.report(f"Snapshot: {destination}")
        if not browser_backup_path:
            self.report(
                "Server snapshot only: export the browser companion separately to "
                "include unsubmitted work."
            )

    def _recover(
        self,
        state: RuntimeRecord | None,
        original: Process,
        paths: dict[str, str],
        progress: ShutdownProgress,
        stop_completed: bool,
    ) -> None:
        """Restore the captured running instance without duplicating a live process."""
        if stop_completed:
            self.lifecycle.start(paths)
            return

        self.diagnostics.stage = "backup shutdown recovery"
        process = progress.process or original
        if process.exited:
            self.lifecycle.start(paths)
            return

        if progress.request_state in ("accepted", "uncertain"):
            if not process.wait(30):
                raise ManagerError(
                    "Recovery could not confirm the original process exited within 30 additional "
                    "seconds after an accepted or uncertain shutdown request. "
                    "No restart or forced termination was performed.",
                    "warning",
                )
            self.lifecycle.start(paths)
            return

        remaining = self.runtime.owned_process(state)
        if (
            remaining is None
            or remaining.pid not in self.runtime.listeners()
            or not self.runtime.healthy()
        ):
            raise ManagerError(
                "Recovery could not confirm the original process is healthy after shutdown "
                "was not accepted. No restart or forced termination was performed.",
                "warning",
            )
        self.report(
            "Shutdown was not accepted; the original OpenFic process remains healthy. "
            "No recovery restart was performed."
        )
