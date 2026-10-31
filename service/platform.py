"""OS-specific locking and process handles, separate from lifecycle policy."""

import ctypes
import os
from contextlib import contextmanager, suppress
from pathlib import Path

import psutil

if os.name == "nt":
    from ctypes import wintypes

    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _kernel.CreateFileW.restype = wintypes.HANDLE
    _kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel.CloseHandle.restype = wintypes.BOOL
    _kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel.OpenProcess.restype = wintypes.HANDLE
    _kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel.WaitForSingleObject.restype = wintypes.DWORD
else:
    import fcntl


class LockBusy(Exception):
    """Another manager owns the lifecycle lock."""


@contextmanager
def management_lock(path: Path, *, probe: bool = False):
    """Probes never create files; Windows sharing matches the previous manager."""
    if os.name == "nt":
        handle = _kernel.CreateFileW(
            str(path),
            0x80000000 if probe else 0xC0000000,
            3 if probe else 0,
            None,
            3 if probe else 4,
            0x80,
            None,
        )
        if handle == ctypes.c_void_p(-1).value:
            error = ctypes.get_last_error()
            if error in (32, 33):
                raise LockBusy from None
            raise ctypes.WinError(error)
        try:
            yield
        finally:
            _kernel.CloseHandle(handle)
    else:
        with path.open("rb" if probe else "a+b") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise LockBusy from None
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class Process:
    """A process identity, with a retained Windows handle for shutdown waits."""

    def __init__(self, pid: int):
        self.info = psutil.Process(pid)
        self.pid = pid
        self.created = self.info.create_time()
        self.handle = None
        if os.name == "nt":
            self.handle = _kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
            if not self.handle:
                error = ctypes.get_last_error()
                if error == 87:
                    raise psutil.NoSuchProcess(pid)
                raise ctypes.WinError(error)
            # The PID could have been reused between inspection and OpenProcess.
            if not self.info.is_running():
                self.close()
                raise psutil.NoSuchProcess(pid)

    def close(self):
        if self.handle:
            _kernel.CloseHandle(self.handle)
            self.handle = None

    def wait(self, timeout: float) -> bool:
        if self.handle:
            result = _kernel.WaitForSingleObject(self.handle, int(timeout * 1000))
            if result == 0xFFFFFFFF:
                raise ctypes.WinError(ctypes.get_last_error())
            return result == 0
        try:
            self.info.wait(timeout=timeout)
            return True
        except psutil.TimeoutExpired:
            return False

    @property
    def exited(self) -> bool:
        return not self.info.is_running() or self.wait(0)


def terminate_launched_tree(process: psutil.Process) -> None:
    """Only failed startup may terminate the process tree this invocation launched."""
    if not process.is_running():
        return
    children = process.children(recursive=True)
    for child in reversed(children):
        with suppress(psutil.NoSuchProcess):
            child.kill()  # psutil guards against PID reuse.
    with suppress(psutil.NoSuchProcess):
        process.kill()
    psutil.wait_procs([*children, process], timeout=5)
