from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class RateLimit:
    requests: int | None
    interval: str | None


@dataclass(slots=True)
class KeyInfo:
    label: str | None
    usage: float | None
    usage_daily: float | None
    usage_weekly: float | None
    usage_monthly: float | None
    limit: float | None
    limit_remaining: float | None
    limit_reset: str | None
    expires_at: str | None
    is_free_tier: bool | None
    is_management_key: bool | None
    is_provisioning_key: bool | None
    include_byok_in_limit: bool | None
    rate_limit: RateLimit | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CreditsInfo:
    total_credits: float | None
    total_usage: float | None
    remaining_credits: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QueryResult:
    summary: dict[str, Any]
    http_meta: dict[str, Any]
    raw_response: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
