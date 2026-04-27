from __future__ import annotations

from PySide6.QtCore import QThread

_DETACHED_THREADS: list[QThread] = []


def stop_thread(thread: QThread | None, timeout_ms: int = 3000) -> None:
    """Request a worker thread to stop without blocking shutdown forever."""
    if thread is None or not thread.isRunning():
        return
    thread.requestInterruption()
    thread.quit()
    if thread.wait(timeout_ms):
        return
    thread.setParent(None)
    _DETACHED_THREADS.append(thread)

    def _release_thread() -> None:
        try:
            _DETACHED_THREADS.remove(thread)
        except ValueError:
            pass
        thread.deleteLater()

    thread.finished.connect(_release_thread)


def disconnect_signal(signal) -> None:
    """Best-effort disconnect for Qt signals that may already be detached."""
    try:
        signal.disconnect()
    except (RuntimeError, TypeError):
        return
