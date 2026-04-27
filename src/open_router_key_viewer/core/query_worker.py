from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from open_router_key_viewer.services.openrouter import OpenRouterAPIError, OpenRouterClient


class QueryWorker(QThread):
    """Run an OpenRouter query off the UI thread."""

    succeeded = Signal(dict)
    failed = Signal(object)

    def __init__(self, mode: str, secret: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode = mode
        self.secret = secret
        self.client = OpenRouterClient()

    def run(self) -> None:
        try:
            if self.mode == "key-info":
                result = self.client.get_current_key_info(self.secret)
            elif self.mode == "credits":
                result = self.client.get_credits(self.secret)
            else:
                raise OpenRouterAPIError(f"Unsupported query mode: {self.mode}")
        except OpenRouterAPIError as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(
                    {
                        "message": str(exc),
                        "http_meta": exc.http_meta or {},
                        "raw_response": exc.raw_response,
                    }
                )
            return

        if not self.isInterruptionRequested():
            self.succeeded.emit(result.to_dict())
