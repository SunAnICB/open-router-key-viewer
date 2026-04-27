from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FloatingMetricsState:
    key_value: str = "-"
    key_time: str = "-"
    credits_value: str = "-"
    credits_time: str = "-"

    def update(self, mode: str, summary: dict[str, object], success_time: str) -> None:
        if mode == "key-info":
            self.key_value = format_currency_value(summary.get("limit_remaining"))
            self.key_time = success_time
            return
        if mode == "credits":
            self.credits_value = format_currency_value(summary.get("remaining_credits"))
            self.credits_time = success_time


def format_currency_value(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"${value:.4f}"
    return "-"
