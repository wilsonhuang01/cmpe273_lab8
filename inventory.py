"""In-process Primary/Secondary inventory with asynchronous replication."""

from collections import deque
from dataclasses import dataclass
from threading import Condition, Thread


@dataclass(frozen=True)
class InventoryValue:
    stock: int
    version: int


class InventorySystem:
    """One writable Primary, one read-only Secondary, and an ordered update queue.

    Both replicas start at stock=10. Writes acknowledge the Primary immediately;
    a separate worker copies queued values to the Secondary. All data is in memory.
    """

    def __init__(self):
        self._primary = InventoryValue(stock=10, version=0)
        self._secondary = InventoryValue(stock=10, version=0)
        self._pending = deque()
        self._condition = Condition()
        self._paused = False
        self._closed = False
        self._worker = Thread(target=self._replicate, name="replication")
        self._worker.start()

    def read(self, replica="primary"):
        """Read a detached, immutable value from the requested replica."""
        with self._condition:
            if replica == "primary":
                return self._primary
            if replica == "secondary":
                return self._secondary
            raise ValueError("replica must be 'primary' or 'secondary'")

    def update(self, stock):
        """Write only to the Primary and enqueue the resulting version."""
        if type(stock) is not int or stock < 0:
            raise ValueError("stock must be a nonnegative integer")
        with self._condition:
            if self._closed:
                raise RuntimeError("inventory system is closed")
            self._primary = InventoryValue(stock, self._primary.version + 1)
            self._pending.append(self._primary)
            self._condition.notify_all()
            return self._primary

    def pause_replication(self):
        """Stop delivery before returning; subsequent writes remain queued."""
        with self._condition:
            self._paused = True

    def resume_replication(self):
        with self._condition:
            self._paused = False
            self._condition.notify_all()

    def wait_for_replication(self, version, timeout=5):
        """Wait at most timeout seconds for the Secondary to reach a version."""
        with self._condition:
            self._condition.wait_for(
                lambda: self._secondary.version >= version or self._closed,
                timeout=timeout,
            )
            return self._secondary.version >= version

    def _replicate(self):
        while True:
            with self._condition:
                self._condition.wait_for(
                    lambda: self._closed or (self._pending and not self._paused)
                )
                if self._closed:
                    return
                # Apply under the same lock as pause, so no delivery can slip
                # through after pause_replication() has returned.
                self._secondary = self._pending.popleft()
                self._condition.notify_all()

    def close(self):
        """Stop the worker. Like all state, any queued updates are discarded."""
        with self._condition:
            self._closed = True
            self._condition.notify_all()
        self._worker.join()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
