from __future__ import annotations

from typing import Any

import pytest

import open_router_key_viewer.core.query_coordinator as query_coordinator_module
from open_router_key_viewer.core.query_coordinator import QueryCoordinator
from open_router_key_viewer.state import QueryState


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks: list[Any] = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in list(self._callbacks):
            callback(*args)

    def disconnect(self) -> None:
        self._callbacks.clear()


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


def test_query_coordinator_updates_state_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    worker_ref: dict[str, _FakeWorker] = {}
    events: list[object] = []

    def _worker_factory(mode: str, secret: str, parent: object) -> _FakeWorker:
        worker = _FakeWorker(mode, secret, parent)
        worker_ref["worker"] = worker
        return worker

    monkeypatch.setattr(query_coordinator_module, "QueryWorker", _worker_factory)
    query_state = QueryState("credits")
    coordinator = QueryCoordinator(
        "credits",
        query_state,
        object(),
        on_started=lambda: events.append("started"),
        on_state_changed=lambda: events.append(("state", query_state.status)),
        on_failed=lambda message: events.append(("failed", message)),
        on_succeeded=lambda summary: events.append(("success", summary)),
        on_finished=lambda: events.append("finished"),
    )

    assert coordinator.run("secret") is True
    worker = worker_ref["worker"]
    assert worker.started is True
    assert worker.mode == "credits"
    assert worker.secret == "secret"
    assert query_state.status == "loading"

    worker.succeeded.emit({"summary": {"remaining_credits": 7}})
    worker.running = False
    worker.finished.emit()

    assert query_state.status == "success"
    assert query_state.summary["remaining_credits"] == 7
    assert events[0] == "started"
    assert events[-2][0] == "success"
    assert events[-1] == "finished"
    assert coordinator.is_running() is False


def test_query_coordinator_blocks_duplicate_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_coordinator_module, "QueryWorker", _FakeWorker)
    started: list[str] = []
    coordinator = QueryCoordinator(
        "key-info",
        QueryState("key-info"),
        object(),
        on_started=lambda: started.append("started"),
        on_state_changed=lambda: None,
        on_failed=lambda message: None,
        on_succeeded=lambda summary: None,
        on_finished=lambda: None,
    )

    assert coordinator.run("first") is True
    assert coordinator.run("second") is False
    assert started == ["started"]


def test_query_coordinator_stop_disconnects_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_coordinator_module, "QueryWorker", _FakeWorker)
    stopped: list[object] = []
    monkeypatch.setattr(query_coordinator_module, "stop_thread", lambda worker: stopped.append(worker))
    coordinator = QueryCoordinator(
        "key-info",
        QueryState("key-info"),
        object(),
        on_started=lambda: None,
        on_state_changed=lambda: None,
        on_failed=lambda message: None,
        on_succeeded=lambda summary: None,
        on_finished=lambda: None,
    )

    assert coordinator.run("secret") is True
    worker = coordinator._worker
    assert worker is not None

    coordinator.stop()

    assert stopped == [worker]
    assert coordinator._worker is None
    assert worker.succeeded._callbacks == []
    assert worker.failed._callbacks == []
    assert worker.finished._callbacks == []
