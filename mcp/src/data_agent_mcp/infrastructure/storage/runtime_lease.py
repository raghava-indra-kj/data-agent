import os
import threading
from pathlib import Path

from data_agent_mcp.domain.queries import OperationError


class FileRuntimeLease:
    """A separate OS file lock, held for the process lifespan, released on crash."""

    def __init__(self, path: Path):
        self.path = path
        self._handle = None
        self._mutex = threading.Lock()

    def acquire(self):
        with self._mutex:
            if self._handle is not None:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = self.path.open("a+b")
            try:
                if not self.path.stat().st_size:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                handle.close()
                raise OperationError(
                    "SERVER_ALREADY_RUNNING",
                    "Another MCP process owns this metadata store. Stop it or configure a separate state file.",
                ) from None
            self._handle = handle

    def release(self):
        with self._mutex:
            if self._handle is not None:
                self._handle.close()
                self._handle = None
