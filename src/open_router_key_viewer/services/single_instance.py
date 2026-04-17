from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QLockFile, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstanceManager(QObject):
    """Coordinate optional single-instance activation via QLocalServer."""

    activation_requested = Signal()

    def __init__(self, app_id: str = "open-router-key-viewer", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._instance_name = self._build_instance_name(app_id)
        runtime_dir = self._runtime_dir()
        self._server_name = str(runtime_dir / f"{self._instance_name}.sock")
        self._lock_file = QLockFile(str(runtime_dir / f"{self._instance_name}.lock"))
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._handle_new_connection)

    @property
    def server_name(self) -> str:
        return self._server_name

    def start_or_activate_existing(self) -> bool:
        """Start listening for activations, or activate an existing instance."""
        if self._lock_file.tryLock(0):
            if self._start_listening():
                return True
            self._lock_file.unlock()
            return False

        if self._notify_existing_instance():
            return False

        if self._lock_file.removeStaleLockFile() and self._lock_file.tryLock(0):
            if self._start_listening():
                return True
            self._lock_file.unlock()
            return False

        return False

    def _start_listening(self) -> bool:
        QLocalServer.removeServer(self._server_name)
        if self._server.listen(self._server_name):
            return True
        return False

    def close(self) -> None:
        if self._server.isListening():
            self._server.close()
        if self._lock_file.isLocked():
            self._lock_file.unlock()
        QLocalServer.removeServer(self._server_name)

    @staticmethod
    def _build_instance_name(app_id: str) -> str:
        uid = getattr(os, "getuid", lambda: None)()
        suffix = str(uid) if uid is not None else "default"
        return f"{app_id}-{suffix}"

    @staticmethod
    def _runtime_dir() -> Path:
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if runtime_dir:
            path = Path(runtime_dir)
        else:
            path = Path(tempfile.gettempdir()) / "open-router-key-viewer"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _notify_existing_instance(self) -> bool:
        socket = QLocalSocket(self)
        socket.connectToServer(self._server_name)
        if not socket.waitForConnected(250):
            return False
        socket.write(b"activate\n")
        socket.flush()
        socket.waitForBytesWritten(250)
        socket.disconnectFromServer()
        return True

    def _handle_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            socket.readyRead.connect(lambda s=socket: self._handle_socket_ready(s))
            socket.disconnected.connect(socket.deleteLater)

    def _handle_socket_ready(self, socket: QLocalSocket) -> None:
        payload = bytes(socket.readAll()).decode("utf-8", errors="ignore").strip().lower()
        if payload == "activate":
            self.activation_requested.emit()
        socket.disconnectFromServer()
