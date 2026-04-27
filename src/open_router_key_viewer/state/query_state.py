from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

QueryStatus = Literal["idle", "loading", "success", "error"]


@dataclass(slots=True)
class QueryState:
    mode: str
    status: QueryStatus = "idle"
    summary: dict[str, Any] = field(default_factory=dict)
    http_meta: dict[str, Any] = field(default_factory=dict)
    raw_response: object = field(default_factory=dict)
    last_success_time: str = "-"

    def start(self) -> None:
        self.status = "loading"
        self.summary = {}
        self.http_meta = {}
        self.raw_response = {}

    def succeed(self, payload: dict[str, Any], success_time: str) -> None:
        summary = payload.get("summary", {})
        http_meta = payload.get("http_meta", {})
        self.status = "success"
        self.summary = summary if isinstance(summary, dict) else {}
        self.http_meta = http_meta if isinstance(http_meta, dict) else {}
        self.raw_response = payload.get("raw_response", {})
        self.last_success_time = success_time

    def fail(self, message: str, *, http_meta: object = None, raw_response: object = None) -> None:
        self.status = "error"
        self.summary = {}
        self.http_meta = http_meta if isinstance(http_meta, dict) else {}
        self.raw_response = raw_response if raw_response is not None else {"error": message}

    def raw_http_payload(self) -> dict[str, object]:
        return {
            "request": self.http_meta.get("request", {}),
            "response": {
                **self.http_meta.get("response", {}),
                "body": self.raw_response,
            },
        }
