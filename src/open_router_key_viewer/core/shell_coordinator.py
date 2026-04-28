from __future__ import annotations

from dataclasses import dataclass

from open_router_key_viewer.services.alert_service import AlertService
from open_router_key_viewer.services.config_store import ConfigStore
from open_router_key_viewer.services.runtime_settings import RuntimeSettingsService
from open_router_key_viewer.state import FloatingMetricsState, QueryState
from open_router_key_viewer.state.floating_metrics import DEFAULT_FLOATING_METRICS, DEFAULT_PANEL_METRICS, RenderedMetric


@dataclass(frozen=True, slots=True)
class ShellAlertPresentation:
    target: str
    level: str
    subject: str
    value: float
    notify_in_app: bool
    notify_system: bool


class ShellCoordinator:
    """Own shell runtime settings, floating metrics, alerts, and webhooks."""

    def __init__(
        self,
        config_store: ConfigStore,
        *,
        key_query_state: QueryState,
        credits_query_state: QueryState,
    ) -> None:
        self.key_query_state = key_query_state
        self.credits_query_state = credits_query_state
        self.runtime_settings = RuntimeSettingsService(config_store)
        self.alert_service = AlertService()
        self.floating_metrics = FloatingMetricsState()

    def panel_indicator_enabled(self) -> bool:
        return self.runtime_settings.panel_indicator_enabled()

    def panel_rotation_interval_msec(self) -> int:
        return self.runtime_settings.current_config().panel_rotation_interval_seconds * 1000

    def update_floating_metrics(self, mode: str, summary: dict[str, object]) -> FloatingMetricsState:
        success_time = (
            self.key_query_state.last_success_time
            if mode == "key-info"
            else self.credits_query_state.last_success_time
        )
        self.floating_metrics.update(mode, summary, success_time)
        return self.floating_metrics

    def render_floating_metrics(self) -> list[RenderedMetric]:
        config = self.runtime_settings.current_config()
        return self.floating_metrics.render(
            config.floating_metrics,
            config.metric_labels,
            "floating",
            DEFAULT_FLOATING_METRICS,
        )

    def render_panel_metrics(self) -> list[RenderedMetric]:
        config = self.runtime_settings.current_config()
        return self.floating_metrics.render(config.panel_metrics, config.metric_labels, "panel", DEFAULT_PANEL_METRICS)

    def evaluate_alert(self, mode: str, summary: dict[str, object]) -> ShellAlertPresentation | None:
        config = self.runtime_settings.current_config()
        event = self.alert_service.evaluate(mode, summary, config)
        if event is None:
            return None
        self.alert_service.send_webhook(event)
        return ShellAlertPresentation(
            target=event.target,
            level=event.level,
            subject=event.subject,
            value=event.value,
            notify_in_app=config.notify_in_app,
            notify_system=config.notify_system,
        )
