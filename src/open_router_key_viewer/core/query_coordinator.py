from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtWidgets import QWidget

from open_router_key_viewer.core.threading import disconnect_signal, stop_thread
from open_router_key_viewer.core.query_worker import QueryWorker
from open_router_key_viewer.state import QueryState, normalize_query_error
from open_router_key_viewer.state.app_metadata import DISPLAY_DATETIME_FORMAT


class QueryCoordinator:
    """Own query worker lifecycle and QueryState transitions."""

    def __init__(
        self,
        mode: str,
        query_state: QueryState,
        parent: QWidget,
        *,
        on_started: Callable[[], None],
        on_state_changed: Callable[[], None],
        on_failed: Callable[[str], None],
        on_succeeded: Callable[[dict[str, object]], None],
        on_finished: Callable[[], None],
    ) -> None:
        self.mode = mode
        self.query_state = query_state
        self.parent = parent
        self.on_started = on_started
        self.on_state_changed = on_state_changed
        self.on_failed = on_failed
        self.on_succeeded = on_succeeded
        self.on_finished = on_finished
        self._worker: QueryWorker | None = None

    def is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def run(self, secret: str) -> bool:
        if self.is_running():
            return False

        self.query_state.start()
        self.on_started()
        self._worker = QueryWorker(self.mode, secret, self.parent)
        self._worker.succeeded.connect(self._handle_success)
        self._worker.failed.connect(self._handle_failure)
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

    def _handle_success(self, payload: dict) -> None:
        self.query_state.succeed(payload, datetime.now().strftime(DISPLAY_DATETIME_FORMAT))
        self.on_state_changed()
        self.on_succeeded(self.query_state.summary)

    def _handle_failure(self, error: object) -> None:
        message, http_meta, raw_payload = normalize_query_error(error, "请求失败")
        self.query_state.fail(message, http_meta=http_meta, raw_response=raw_payload)
        self.on_state_changed()
        self.on_failed(message)

    def _handle_finished(self) -> None:
        self._worker = None
        self.on_finished()
