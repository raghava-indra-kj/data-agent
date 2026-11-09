"""Cross-process lock for the small owner-managed configuration file."""

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from data_agent_mcp.domain.queries import OperationError

_process_lock = threading.RLock()


@contextmanager
def file_lock(path: Path):
    with _process_lock, path.open("a+b") as handle:
        if not path.stat().st_size:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + 10
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise OperationError(
                        "CONFIGURATION_BUSY",
                        "Another process is updating configuration. Try again shortly.",
                    ) from None
                time.sleep(0.05)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
