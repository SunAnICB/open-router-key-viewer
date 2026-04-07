from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from open_router_key_viewer.models import CreditsInfo, KeyInfo, QueryResult, RateLimit

BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(slots=True)
class OpenRouterAPIError(Exception):
    message: str
    status_code: int | None = None

    def __str__(self) -> str:
        if self.status_code is None:
            return self.message
        return f"{self.message} (status={self.status_code})"


class OpenRouterClient:
    def __init__(self, *, base_url: str = BASE_URL, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_current_key_info(self, api_key: str) -> QueryResult:
        response = self._get_json("/key", api_key)
        payload = response["body"]
        data = payload.get("data", payload)
        rate_limit_data = data.get("rate_limit") or {}

        rate_limit = None
        if rate_limit_data:
            rate_limit = RateLimit(
                requests=_to_int(rate_limit_data.get("requests")),
                interval=_to_str(rate_limit_data.get("interval")),
            )

        result = KeyInfo(
            label=_to_str(data.get("label")),
            usage=_to_float(data.get("usage")),
            usage_daily=_to_float(data.get("usage_daily")),
            usage_weekly=_to_float(data.get("usage_weekly")),
            usage_monthly=_to_float(data.get("usage_monthly")),
            limit=_to_float(data.get("limit")),
            limit_remaining=_to_float(data.get("limit_remaining")),
            limit_reset=_to_str(data.get("limit_reset")),
            expires_at=_to_str(data.get("expires_at")),
            is_free_tier=_to_bool(data.get("is_free_tier")),
            is_management_key=_to_bool(data.get("is_management_key")),
            is_provisioning_key=_to_bool(data.get("is_provisioning_key")),
            include_byok_in_limit=_to_bool(data.get("include_byok_in_limit")),
            rate_limit=rate_limit,
        )
        return QueryResult(
            summary=result.to_dict(),
            http_meta=response["http_meta"],
            raw_response=payload,
        )

    def get_credits(self, management_key: str) -> QueryResult:
        response = self._get_json("/credits", management_key)
        payload = response["body"]
        data = payload.get("data", payload)
        total_credits = _to_float(data.get("total_credits"))
        total_usage = _to_float(data.get("total_usage"))

        remaining_credits = None
        if total_credits is not None and total_usage is not None:
            remaining_credits = total_credits - total_usage

        result = CreditsInfo(
            total_credits=total_credits,
            total_usage=total_usage,
            remaining_credits=remaining_credits,
        )
        return QueryResult(
            summary=result.to_dict(),
            http_meta=response["http_meta"],
            raw_response=payload,
        )

    def _get_json(self, path: str, api_key: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        request = Request(
            url=url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": "open-router-key-viewer/0.1.1",
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                status_code = response.getcode()
                headers = dict(response.headers.items())
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            message = _extract_error_message(error_body) or "OpenRouter API request failed"
            raise OpenRouterAPIError(message=message, status_code=exc.code) from exc
        except URLError as exc:
            raise OpenRouterAPIError(message=f"Network error: {exc.reason}") from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise OpenRouterAPIError(message="OpenRouter returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise OpenRouterAPIError(message="Unexpected response shape from OpenRouter")
        return {
            "http_meta": {
                "request": {
                    "method": "GET",
                    "url": url,
                    "headers": {
                        "Authorization": _mask_secret_header(api_key),
                        "Accept": "application/json",
                        "User-Agent": "open-router-key-viewer/0.1.1",
                    },
                },
                "response": {
                    "status_code": status_code,
                    "headers": headers,
                },
            },
            "body": payload,
        }


def _extract_error_message(raw_body: str) -> str | None:
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body.strip() or None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _mask_secret_header(secret: str) -> str:
    if len(secret) <= 10:
        return "Bearer ******"
    return f"Bearer {secret[:6]}...{secret[-4:]}"
