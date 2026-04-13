from __future__ import annotations

from typing import Any

import pytest

import open_router_key_viewer.ui.controllers.query_controller as query_controller_module
from open_router_key_viewer.ui.controllers.query_controller import QueryExecutionController


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks: list[Any] = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in list(self._callbacks):
            callback(*args)


class _FakeWorker:
    def __init__(self, mode: str, secret: str, parent: object) -> None:
        self.mode = mode
        self.secret = secret
        self.parent = parent
        self.succeeded = _FakeSignal()
        self.failed = _FakeSignal()
        self.finished = _FakeSignal()
        self.started = False
        self.running = False

    def isRunning(self) -> bool:  # noqa: N802
        return self.running

    def start(self) -> None:
        self.started = True
        self.running = True


def test_run_starts_worker_and_calls_success_then_finished(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[object] = []
    worker_ref: dict[str, _FakeWorker] = {}

    def _worker_factory(mode: str, secret: str, parent: object) -> _FakeWorker:
        worker = _FakeWorker(mode, secret, parent)
        worker_ref["worker"] = worker
        return worker

    monkeypatch.setattr(query_controller_module, "QueryWorker", _worker_factory)

    controller = QueryExecutionController(
        "credits",
        object(),
        on_started=lambda: events.append("started"),
        on_succeeded=lambda payload: events.append(("success", payload)),
        on_failed=lambda message: events.append(("failed", message)),
        on_finished=lambda: events.append("finished"),
    )

    assert controller.run("secret") is True
    worker = worker_ref["worker"]
    assert worker.started is True
    assert worker.mode == "credits"
    assert worker.secret == "secret"
    assert controller.is_running() is True

    worker.succeeded.emit({"ok": True})
    worker.running = False
    worker.finished.emit()

    assert events == ["started", ("success", {"ok": True}), "finished"]
    assert controller.is_running() is False


def test_run_returns_false_when_worker_already_running(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_controller_module, "QueryWorker", _FakeWorker)
    events: list[str] = []
    controller = QueryExecutionController(
        "key-info",
        object(),
        on_started=lambda: events.append("started"),
        on_succeeded=lambda payload: None,
        on_failed=lambda message: None,
        on_finished=lambda: None,
    )

    assert controller.run("first") is True
    assert controller.run("second") is False
    assert events == ["started"]


def test_failed_signal_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    worker_ref: dict[str, _FakeWorker] = {}

    def _worker_factory(mode: str, secret: str, parent: object) -> _FakeWorker:
        worker = _FakeWorker(mode, secret, parent)
        worker_ref["worker"] = worker
        return worker

    monkeypatch.setattr(query_controller_module, "QueryWorker", _worker_factory)
    failures: list[str] = []
    controller = QueryExecutionController(
        "key-info",
        object(),
        on_started=lambda: None,
        on_succeeded=lambda payload: None,
        on_failed=failures.append,
        on_finished=lambda: None,
    )

    assert controller.run("secret") is True
    worker_ref["worker"].failed.emit("boom")

    assert failures == ["boom"]


def test_stop_delegates_to_stop_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_controller_module, "QueryWorker", _FakeWorker)
    stopped: list[object] = []
    monkeypatch.setattr(query_controller_module, "stop_thread", lambda worker: stopped.append(worker))

    controller = QueryExecutionController(
        "key-info",
        object(),
        on_started=lambda: None,
        on_succeeded=lambda payload: None,
        on_failed=lambda message: None,
        on_finished=lambda: None,
    )

    assert controller.run("secret") is True
    worker = controller._worker
    controller.stop()

    assert stopped == [worker]
    assert controller._worker is None
