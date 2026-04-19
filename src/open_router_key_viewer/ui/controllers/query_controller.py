from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QWidget

from open_router_key_viewer.ui.runtime import QueryWorker, disconnect_signal, stop_thread


class QueryExecutionController:
    """Manage query worker lifecycle for a single query page."""

    def __init__(
        self,
        mode: str,
        parent: QWidget,
        *,
        on_started: Callable[[], None],
        on_succeeded: Callable[[dict], None],
        on_failed: Callable[[object], None],
        on_finished: Callable[[], None],
    ) -> None:
        self.mode = mode
        self.parent = parent
        self.on_started = on_started
        self.on_succeeded = on_succeeded
        self.on_failed = on_failed
        self.on_finished = on_finished
        self._worker: QueryWorker | None = None

    def is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def run(self, secret: str) -> bool:
        if self.is_running():
            return False

        self.on_started()
        self._worker = QueryWorker(self.mode, secret, self.parent)
        self._worker.succeeded.connect(self.on_succeeded)
        self._worker.failed.connect(self.on_failed)
        self._worker.finished.connect(self._handle_finished)
        self._worker.start()
        return True

    def stop(self) -> None:
        if self._worker is not None:
            disconnect_signal(self._worker.succeeded)
            disconnect_signal(self._worker.failed)
            disconnect_signal(self._worker.finished)
        stop_thread(self._worker)
        self._worker = None

    def _handle_finished(self) -> None:
        self._worker = None
        self.on_finished()
