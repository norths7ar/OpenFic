"""Public command arguments, output contract and action dispatch."""

import argparse
import json
import os
import sys

from .backup import Backup
from .config import Instance
from .contract import Diagnostics, ManagerError, Status
from .lifecycle import Lifecycle
from .platform import LockBusy, management_lock
from .runtime import Runtime


def payload(status: Status, instance: Instance) -> dict:
    result = dict(
        schema_version=1,
        state=status.state,
        detail=status.detail,
        pid=status.pid,
        port=instance.port,
        data_directory=str(instance.data),
    )
    if status.busy:
        result["busy"] = True
    return result


def execute(runtime: Runtime, diagnostics: Diagnostics, options: argparse.Namespace) -> int:
    report = (lambda message: None) if options.json else print
    lifecycle = Lifecycle(
        runtime,
        diagnostics,
        restore_environment_path=options.restore_environment_path,
        report=report,
    )
    backup = Backup(runtime, lifecycle, diagnostics, report=report)
    try:
        if not 1 <= runtime.instance.port <= 65535:
            raise ManagerError("Port must be between 1 and 65535.")
        action = options.action
        if options.json and action in ("backup", "restore"):
            raise ManagerError("--json is supported only for start, stop, restart and status.")
        if action == "status":
            print(json.dumps(payload(runtime.status(), runtime.instance)))
            return 0
        if action == "restore":
            backup.restore(options.snapshot_path, options.restore_path)
            return 0
        diagnostics.stage = "management-lock acquisition"
        runtime.instance.runtime_directory.mkdir(parents=True, exist_ok=True)
        try:
            runtime.resources.enter_context(management_lock(runtime.instance.lock_path))
        except LockBusy:
            raise ManagerError(
                "Another lifecycle or backup operation holds the OpenFic management "
                "lock. No lifecycle action was performed.",
                "warning",
                busy=True,
            ) from None
        if action == "start":
            lifecycle.start()
        elif action == "stop":
            lifecycle.stop()
        elif action == "restart":
            lifecycle.restart()
        elif action == "backup":
            backup.backup(options.snapshot_path, options.browser_backup_path)
        if action in ("start", "stop", "restart"):
            result = runtime.status(lock_held=True)
            expected = "stopped" if action == "stop" else "running"
            if result.state != expected:
                raise ManagerError(
                    f"OpenFic {action} could not be confirmed: {result.detail}",
                    result.state,
                )
            if options.json:
                print(
                    json.dumps(payload(result, runtime.instance) | {"ok": True, "action": action})
                )
        return 0
    except Exception as error:
        result = diagnostics.failure(error, options.action)
        if options.action == "status":
            print(json.dumps(payload(result, runtime.instance)))
        else:
            print(result.detail, file=sys.stderr)
            if options.json:
                print(
                    json.dumps(
                        payload(result, runtime.instance) | {"ok": False, "action": options.action}
                    )
                )
        return 1
    finally:
        runtime.resources.close()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="python -m service",
        description="Manage the local OpenFic service independently of its web process.",
    )
    result.add_argument(
        "action",
        nargs="?",
        type=str.lower,
        default="status",
        choices=("start", "stop", "restart", "status", "backup", "restore"),
    )
    result.add_argument(
        "--port", type=int, default=18081, help="Local service port (default: 18081)."
    )
    result.add_argument("--data-path", help="Instance data directory (default: repository/data).")
    result.add_argument(
        "--snapshot-path",
        help="Backup destination (default: output/backups/timestamp), or snapshot to restore.",
    )
    result.add_argument(
        "--browser-backup-path", help="Browser companion export to include in a backup."
    )
    result.add_argument(
        "--restore-path", help="New directory for a restored copy; never the live data directory."
    )
    result.add_argument(
        "--restore-environment-path",
        help="Generated restore-environment.json for starting a restored copy.",
    )
    result.add_argument(
        "--json",
        action="store_true",
        help="Machine-readable start/stop/restart result; status always emits JSON.",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    options = parser().parse_args(argv)
    try:
        instance = Instance.from_arguments(options.data_path, options.port)
        diagnostics = Diagnostics(
            secrets=[
                value
                for name in ("OPENFIC_SHUTDOWN_TOKEN", "ENCRYPTION_KEY")
                if (value := os.environ.get(name))
            ]
        )
        runtime = Runtime(instance, diagnostics)
    except Exception as error:
        # Construction must not turn a machine-facing command into a traceback.
        detail = (
            f"Unable to initialize OpenFic manager: {type(error).__name__}. "
            "Check paths and permissions."
        )
        result = dict(
            schema_version=1,
            state="unknown",
            detail=detail,
            pid=None,
            port=options.port,
            data_directory=options.data_path,
        )
        if options.action == "status":
            print(json.dumps(result))
        else:
            print(detail, file=sys.stderr)
            if options.json:
                print(json.dumps(result | {"ok": False, "action": options.action}))
        return 1
    return execute(runtime, diagnostics, options)
