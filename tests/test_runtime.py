from __future__ import annotations

import open_router_key_viewer.ui.runtime as runtime_module
from open_router_key_viewer.ui.runtime import disconnect_signal, stop_thread


class _FakeSignal:
    def __init__(self) -> None:
        self.callbacks: list[object] = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)

    def disconnect(self) -> None:
        self.callbacks.clear()


class _FakeThread:
    def __init__(self, *, running: bool, wait_results: list[bool]) -> None:
        self._running = running
        self._wait_results = wait_results
        self.finished = _FakeSignal()
        self.requested_interruption = 0
        self.quit_calls = 0
        self.wait_calls: list[int] = []
        self.parent_values: list[object] = []

    def isRunning(self) -> bool:  # noqa: N802
        return self._running

    def requestInterruption(self) -> None:  # noqa: N802
        self.requested_interruption += 1

    def quit(self) -> None:
        self.quit_calls += 1

    def wait(self, timeout_ms: int) -> bool:
        self.wait_calls.append(timeout_ms)
        if self._wait_results:
            return self._wait_results.pop(0)
        return False

    def setParent(self, value) -> None:  # noqa: N802
        self.parent_values.append(value)

    def deleteLater(self) -> None:
        return None


def test_stop_thread_requests_interruption_and_quits_cleanly() -> None:
    thread = _FakeThread(running=True, wait_results=[True])

    stop_thread(thread, timeout_ms=1234)

    assert thread.requested_interruption == 1
    assert thread.quit_calls == 1
    assert thread.wait_calls == [1234]
    assert thread.parent_values == []
    assert thread.finished.callbacks == []


def test_stop_thread_detaches_thread_when_wait_times_out() -> None:
    thread = _FakeThread(running=True, wait_results=[False])
    runtime_module._DETACHED_THREADS.clear()

    stop_thread(thread, timeout_ms=500)

    assert thread.requested_interruption == 1
    assert thread.quit_calls == 1
    assert thread.wait_calls == [500]
    assert thread.parent_values == [None]
    assert len(thread.finished.callbacks) == 1
    assert runtime_module._DETACHED_THREADS == [thread]

    thread.finished.callbacks[0]()

    assert runtime_module._DETACHED_THREADS == []


def test_disconnect_signal_clears_connected_callbacks() -> None:
    signal = _FakeSignal()
    signal.connect(lambda: None)
    signal.connect(lambda: None)

    disconnect_signal(signal)

    assert signal.callbacks == []
