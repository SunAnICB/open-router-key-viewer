from __future__ import annotations

import io
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import InfoBar, InfoBarPosition

from open_router_key_viewer.i18n import tr
from open_router_key_viewer.services.alert_service import AlertEvent, AlertService
from open_router_key_viewer.services.config_store import ConfigStore
from open_router_key_viewer.services.runtime_settings import RuntimeSettingsService
from open_router_key_viewer.state import FloatingMetricsState, QueryState
from open_router_key_viewer.state.app_metadata import APP_DISPLAY_NAME
from open_router_key_viewer.ui.widgets import FloatingWindow

try:
    from open_router_key_viewer.sni_tray import SNITray
except ImportError:
    SNITray = None  # type: ignore[assignment,misc]

_tr = tr


class WindowShellController:
    """Manage floating window, tray integration, alerts, and webhook delivery."""

    def __init__(
        self,
        host: QWidget,
        *,
        config_store: ConfigStore,
        key_query_state: QueryState,
        credits_query_state: QueryState,
        refresh_floating_metrics: Callable[[], None],
        quit_application: Callable[[], None],
    ) -> None:
        self.host = host
        self.key_query_state = key_query_state
        self.credits_query_state = credits_query_state
        self._refresh_floating_metrics_callback = refresh_floating_metrics
        self._quit_application_callback = quit_application
        self._floating_window_supported = self._is_x11_platform()
        self._indicator_available = self._check_indicator_available()
        self._alert_service = AlertService()
        self._runtime_settings = RuntimeSettingsService(config_store)
        self._tray_icon: QSystemTrayIcon | None = None
        self._sni_tray: SNITray | None = None  # type: ignore[assignment]
        self._panel_label_timer: QTimer | None = None
        self._panel_label_phase = 0
        self._background_hint_shown = False
        self._floating_metrics = FloatingMetricsState()
        self.floating_window: FloatingWindow | None = None
        if self._floating_window_supported:
            self.floating_window = self._create_floating_window(topmost=True)

    @property
    def floating_window_supported(self) -> bool:
        return self._floating_window_supported

    @property
    def indicator_available(self) -> bool:
        return self._indicator_available

    def setup_indicator(self) -> None:
        if self._indicator_available and self._runtime_settings.panel_indicator_enabled():
            sni = SNITray(
                activate=self.show_full_window,
                refresh=self._refresh_floating_metrics_callback,
                show_window=self.show_full_window,
                quit=self._quit_application_callback,
            )
            if sni.register():
                self._sni_tray = sni
                self._start_panel_label_rotation()
                self._set_window_icon()
                return
        self._setup_tray_icon()

    def apply_indicator_settings(self) -> None:
        want_enabled = self._indicator_available and self._runtime_settings.panel_indicator_enabled()

        if self._sni_tray is None or not self._sni_tray.is_active:
            if want_enabled:
                sni = SNITray(
                    activate=self.show_full_window,
                    refresh=self._refresh_floating_metrics_callback,
                    show_window=self.show_full_window,
                    quit=self._quit_application_callback,
                )
                if sni.register():
                    self._sni_tray = sni
                    self._start_panel_label_rotation()
                    if self._tray_icon is not None:
                        self._tray_icon.hide()
                        self._tray_icon = None
            return

        if want_enabled:
            self._sni_tray.show()
            if self._panel_label_timer is None:
                self._start_panel_label_rotation()
        else:
            self._sni_tray.hide()
            if self._panel_label_timer is not None:
                self._panel_label_timer.stop()
                self._panel_label_timer.deleteLater()
                self._panel_label_timer = None

    def retranslate_ui(self) -> None:
        if self.floating_window is not None:
            self.floating_window.retranslate_ui()
        self._sync_floating_window()
        self._sync_panel_label()

    def show_floating_window(self) -> None:
        if self.floating_window is None:
            InfoBar.warning(
                title=_tr("当前不可用"),
                content=(
                    _tr("数据已显示在顶栏指示器中")
                    if self._sni_tray is not None and self._sni_tray.is_active
                    else _tr("悬浮小窗仅在 X11/xcb 启动时支持")
                ),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2500,
                parent=self.host,
            )
            return

        self._sync_floating_window()
        center = self.host.frameGeometry().center()
        self.host.hide()
        target_x = center.x() - self.floating_window.width() // 2
        target_y = center.y() - self.floating_window.height() // 2
        self.floating_window.move(target_x, target_y)
        self.floating_window.show()
        self.floating_window.raise_()
        self.floating_window.activateWindow()

    def show_full_window(self) -> None:
        if self.floating_window is not None:
            self.floating_window.hide()
        self.host.show()
        self.host.showNormal()
        self.host.raise_()
        self.host.activateWindow()

    def hide_to_background(self) -> bool:
        has_indicator = self._sni_tray is not None and self._sni_tray.is_active
        has_tray = self._tray_icon is not None and self._tray_icon.isVisible()
        if not has_indicator and not has_tray:
            return False

        if self.floating_window is not None:
            self.floating_window.hide()
        self.host.hide()
        if has_tray and not self._background_hint_shown:
            self._tray_icon.showMessage(
                APP_DISPLAY_NAME,
                _tr("应用已驻留后台，可从托盘图标恢复或退出。"),
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
        self._background_hint_shown = True
        return True

    def handle_query_success(self, mode: str, summary: dict[str, object]) -> None:
        self._update_floating_metrics(mode, summary)
        self._evaluate_thresholds(mode, summary)

    def close(self) -> None:
        if self._panel_label_timer is not None:
            self._panel_label_timer.stop()
        if self.floating_window is not None:
            self.floating_window.blockSignals(True)
            self.floating_window.close_for_shutdown()
        if self._sni_tray is not None:
            self._sni_tray.unregister()
        if self._tray_icon is not None:
            self._tray_icon.hide()

    def _is_x11_platform(self) -> bool:
        return "xcb" in (QGuiApplication.platformName() or "").lower()

    @staticmethod
    def _check_indicator_available() -> bool:
        if SNITray is None:
            return False
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface

            bus = QDBusConnection.sessionBus()
            if not bus.isConnected():
                return False
            watcher = QDBusInterface(
                "org.kde.StatusNotifierWatcher",
                "/StatusNotifierWatcher",
                "org.kde.StatusNotifierWatcher",
                bus,
            )
            return watcher.isValid()
        except Exception:
            return False

    def _set_window_icon(self) -> None:
        icon = self._load_app_icon()
        if icon.isNull():
            icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.host.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)

    def _start_panel_label_rotation(self) -> None:
        self._panel_label_timer = QTimer(self.host)
        self._panel_label_timer.timeout.connect(self._rotate_panel_label)
        self._panel_label_timer.start(4000)
        self._sync_panel_label()

    def _rotate_panel_label(self) -> None:
        self._panel_label_phase = 1 - self._panel_label_phase
        self._sync_panel_label()

    def _sync_panel_label(self) -> None:
        if self._sni_tray is None or not self._sni_tray.is_active:
            return
        text = (
            f"{_tr('配额')} {self._floating_metrics.key_value}"
            if self._panel_label_phase == 0
            else f"{_tr('余额')} {self._floating_metrics.credits_value}"
        )
        self._sni_tray.set_label(text, f"{_tr('余额')} $99.9999")

    def _create_floating_window(self, topmost: bool) -> FloatingWindow:
        window = FloatingWindow()
        window.set_topmost(topmost)
        window.refresh_requested.connect(self._refresh_floating_metrics_callback)
        window.full_window_requested.connect(self.show_full_window)
        window.topmost_changed.connect(self._schedule_floating_window_rebuild)
        window.closed.connect(self.show_full_window)
        return window

    def _schedule_floating_window_rebuild(self, topmost: bool) -> None:
        QTimer.singleShot(0, lambda value=topmost: self._rebuild_floating_window(value))

    def _rebuild_floating_window(self, topmost: bool) -> None:
        if self.floating_window is None:
            return

        old_window = self.floating_window
        was_visible = old_window.isVisible()
        geometry = old_window.geometry()

        new_window = self._create_floating_window(topmost=topmost)
        self.floating_window = new_window
        self._sync_floating_window()
        new_window.setGeometry(geometry)

        old_window.blockSignals(True)
        old_window.close_for_shutdown()
        old_window.deleteLater()

        if was_visible:
            new_window.show()
            new_window.raise_()
            new_window.activateWindow()

    def _update_floating_metrics(self, mode: str, summary: dict[str, object]) -> None:
        success_time = (
            self.key_query_state.last_success_time
            if mode == "key-info"
            else self.credits_query_state.last_success_time
        )
        self._floating_metrics.update(mode, summary, success_time)
        self._sync_floating_window()

    def _sync_floating_window(self) -> None:
        if self.floating_window is not None:
            self.floating_window.update_metrics(
                self._floating_metrics.key_value,
                self._floating_metrics.key_time,
                self._floating_metrics.credits_value,
                self._floating_metrics.credits_time,
            )
        self._sync_panel_label()

    def _evaluate_thresholds(self, mode: str, summary: dict[str, object]) -> None:
        config = self._runtime_settings.current_config()
        event = self._alert_service.evaluate(mode, summary, config)
        if event is None:
            return
        if config.notify_in_app:
            self._notify_in_app(event)
        if config.notify_system:
            self._notify_system(event)
        self._alert_service.send_webhook(event)

    def _notify_in_app(self, event: AlertEvent) -> None:
        title = APP_DISPLAY_NAME
        content = _tr("{target} {level} 告警\n{subject} 当前值 {value:.4f}").format(
            target=_tr(event.target),
            level="Critical" if event.level == "critical" else "Warning",
            subject=event.subject.replace(event.target, _tr(event.target), 1),
            value=event.value,
        )
        factory = InfoBar.error if event.level == "critical" else InfoBar.warning
        factory(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=-1,
            parent=self.host,
        )

    def _notify_system(self, event: AlertEvent) -> None:
        title = APP_DISPLAY_NAME
        content = _tr("{target} {level} 告警\n{subject} 当前值 {value:.4f}").format(
            target=_tr(event.target),
            level="Critical" if event.level == "critical" else "Warning",
            subject=event.subject.replace(event.target, _tr(event.target), 1),
            value=event.value,
        )

        if self._sni_tray is not None and self._sni_tray.is_active:
            urgency = "critical" if event.level == "critical" else "normal"
            self._sni_tray.notify(title, content, urgency)
            return

        if self._tray_icon is None or not self._tray_icon.isVisible():
            return
        icon = QSystemTrayIcon.MessageIcon.Critical if event.level == "critical" else QSystemTrayIcon.MessageIcon.Warning
        self._tray_icon.showMessage(title, content, icon, 5000)

    def _setup_tray_icon(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        tray_icon = QSystemTrayIcon(self.host)
        icon = self._load_app_icon()
        if icon.isNull():
            icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.host.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)
        tray_icon.setIcon(icon)
        tray_icon.setToolTip(APP_DISPLAY_NAME)
        menu = QMenu(self.host)
        open_action = menu.addAction(_tr("显示主窗口"))
        open_action.triggered.connect(self.show_full_window)
        refresh_action = menu.addAction(_tr("刷新"))
        refresh_action.triggered.connect(self._refresh_floating_metrics_callback)
        menu.addSeparator()
        quit_action = menu.addAction(_tr("退出"))
        quit_action.triggered.connect(self._quit_application_callback)
        tray_icon.setContextMenu(menu)
        tray_icon.activated.connect(self._handle_tray_icon_activated)
        tray_icon.show()
        self._tray_icon = tray_icon

    def _handle_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_full_window()

    def _load_app_icon(self) -> QIcon:
        base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
        candidates = [
            base_dir / "assets" / "open-router-key-viewer.png",
            base_dir / "assets" / "open-router-key-viewer.svg",
            Path(sys.argv[0]).resolve().parent / "assets" / "open-router-key-viewer.png",
            Path(sys.argv[0]).resolve().parent / "assets" / "open-router-key-viewer.svg",
            Path.cwd() / "assets" / "open-router-key-viewer.png",
            Path.cwd() / "assets" / "open-router-key-viewer.svg",
        ]
        for path in candidates:
            if path.exists():
                return QIcon(str(path))
        return QIcon()
