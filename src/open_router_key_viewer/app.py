from __future__ import annotations

import io
import json
import sys
import threading
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QStyle, QSystemTrayIcon

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import (
        FluentIcon,
        FluentWindow,
        InfoBar,
        InfoBarPosition,
        setThemeColor,
    )

from open_router_key_viewer import __version__
from open_router_key_viewer.i18n import resolve_language_code, tr
from open_router_key_viewer.services.config_store import ConfigStore
from open_router_key_viewer.ui.pages.about_page import AboutPage
from open_router_key_viewer.ui.pages.query_pages import CreditsPage, KeyInfoPage
from open_router_key_viewer.ui.pages.settings_page import CachePage
from open_router_key_viewer.ui.runtime import (
    APP_DISPLAY_NAME,
    DISPLAY_DATETIME_FORMAT,
    format_currency_value,
    install_language,
)
from open_router_key_viewer.ui.widgets import FloatingWindow

try:
    from open_router_key_viewer.sni_tray import SNITray
except ImportError:
    SNITray = None  # type: ignore[assignment,misc]

_tr = tr


class MainWindow(FluentWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config_store = ConfigStore()
        self._floating_window_supported = self._is_x11_platform()
        self._indicator_available = self._check_indicator_available()
        self._alert_state = {"key-info": "normal", "credits": "normal"}
        self._tray_icon: QSystemTrayIcon | None = None
        self._sni_tray: SNITray | None = None  # type: ignore[assignment]
        self._panel_label_timer: QTimer | None = None
        self._panel_label_phase = 0
        self._floating_key_value = "-"
        self._floating_key_time = "-"
        self._floating_credits_value = "-"
        self._floating_credits_time = "-"
        self.key_timer = QTimer(self)
        self.key_timer.timeout.connect(self.key_info_page_auto_query)
        self.credits_timer = QTimer(self)
        self.credits_timer.timeout.connect(self.credits_page_auto_query)
        self.key_info_page = KeyInfoPage(
            self.config_store,
            self.refresh_cache_views,
            self.handle_query_success,
            self,
        )
        self.credits_page = CreditsPage(
            self.config_store,
            self.refresh_cache_views,
            self.handle_query_success,
            self,
        )
        self.cache_page = CachePage(
            self.config_store,
            self.refresh_cache_views,
            self.apply_language,
            self.show_floating_window,
            self._floating_window_supported,
            self._indicator_available,
            self,
        )
        self.about_page = AboutPage(self)
        self.floating_window: FloatingWindow | None = None
        if self._floating_window_supported:
            self.floating_window = self._create_floating_window(topmost=True)
        self.key_nav_item = self.addSubInterface(self.key_info_page, FluentIcon.CERTIFICATE, _tr("Key 配额"))
        self.credits_nav_item = self.addSubInterface(self.credits_page, FluentIcon.PIE_SINGLE, _tr("账户余额"))
        self.cache_nav_item = self.addSubInterface(self.cache_page, FluentIcon.SETTING, _tr("配置"))
        self.about_nav_item = self.addSubInterface(self.about_page, FluentIcon.INFO, _tr("关于"))
        self.navigationInterface.setReturnButtonVisible(False)
        self.setWindowTitle(APP_DISPLAY_NAME)
        self._apply_initial_geometry()
        self._setup_indicator()
        if self.floating_window is not None:
            self._sync_floating_window()
        QTimer.singleShot(0, self._run_startup_queries)

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

    def _setup_indicator(self) -> None:
        payload = self.config_store.load() or {}
        if self._indicator_available and bool(payload.get("panel_indicator_enabled")):
            sni = SNITray(
                activate=self.show_full_window,
                refresh=self.refresh_floating_metrics,
                show_window=self.show_full_window,
                quit=lambda: QApplication.instance().quit(),
            )
            if sni.register():
                self._sni_tray = sni
                self._start_panel_label_rotation()
                self._set_window_icon()
                return
        self._setup_tray_icon()

    def _set_window_icon(self) -> None:
        icon = self._load_app_icon()
        if icon.isNull():
            icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)

    def _start_panel_label_rotation(self) -> None:
        self._panel_label_timer = QTimer(self)
        self._panel_label_timer.timeout.connect(self._rotate_panel_label)
        self._panel_label_timer.start(4000)
        self._sync_panel_label()

    def _rotate_panel_label(self) -> None:
        self._panel_label_phase = 1 - self._panel_label_phase
        self._sync_panel_label()

    def _sync_panel_label(self) -> None:
        if self._sni_tray is None or not self._sni_tray.is_active:
            return
        if self._panel_label_phase == 0:
            text = f"{_tr('配额')} {self._floating_key_value}"
        else:
            text = f"{_tr('余额')} {self._floating_credits_value}"
        self._sni_tray.set_label(text, f"{_tr('余额')} $99.9999")

    def apply_language(self, language_code: str) -> None:
        app = QApplication.instance()
        if app is None:
            return
        install_language(app, language_code)
        self.retranslate_ui()
        InfoBar.success(
            title=_tr("已保存"),
            content=_tr("界面语言已更新"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2500,
            parent=self,
        )

    def retranslate_ui(self) -> None:
        self.key_nav_item.setText(_tr("Key 配额"))
        self.credits_nav_item.setText(_tr("账户余额"))
        self.cache_nav_item.setText(_tr("配置"))
        self.about_nav_item.setText(_tr("关于"))
        self.key_info_page.retranslate_ui()
        self.credits_page.retranslate_ui()
        self.cache_page.retranslate_ui()
        self.about_page.retranslate_ui()
        if self.floating_window is not None:
            self.floating_window.retranslate_ui()
        self._sync_floating_window()
        self._sync_panel_label()

    def _apply_indicator_settings(self) -> None:
        payload = self.config_store.load() or {}
        want_enabled = self._indicator_available and bool(payload.get("panel_indicator_enabled"))

        if self._sni_tray is None or not self._sni_tray.is_active:
            if want_enabled:
                sni = SNITray(
                    activate=self.show_full_window,
                    refresh=self.refresh_floating_metrics,
                    show_window=self.show_full_window,
                    quit=lambda: QApplication.instance().quit(),
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

    def refresh_cache_views(self) -> None:
        self.key_info_page.load_cached_secret()
        self.credits_page.load_cached_secret()
        self.cache_page.refresh_view()
        self._apply_polling_settings()
        self._apply_indicator_settings()

    def _apply_initial_geometry(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(960, 640)
            return

        available = screen.availableGeometry()
        width = max(800, int(available.width() * 0.8))
        height = max(560, int(available.height() * 0.8))
        width = min(width, available.width())
        height = min(height, available.height())
        self.resize(width, height)

        x = available.x() + (available.width() - width) // 2
        y = available.y() + (available.height() - height) // 2
        self.move(x, y)

    def _run_startup_queries(self) -> None:
        payload = self.config_store.load() or {}
        if payload.get("auto_check_updates", True):
            self.about_page.check_updates_silently()
        if payload.get("auto_query_key_info") and payload.get("api_key"):
            self.key_info_page.auto_query_if_possible()
        if payload.get("auto_query_credits") and payload.get("management_key"):
            self.credits_page.auto_query_if_possible()
        self._apply_polling_settings()

    def _apply_polling_settings(self) -> None:
        payload = self.config_store.load() or {}
        self._apply_timer(
            self.key_timer,
            bool(payload.get("poll_key_info_enabled")) and bool(payload.get("api_key")),
            int(payload.get("poll_key_info_interval_seconds", 300)),
        )
        self._apply_timer(
            self.credits_timer,
            bool(payload.get("poll_credits_enabled")) and bool(payload.get("management_key")),
            int(payload.get("poll_credits_interval_seconds", 300)),
        )

    def _apply_timer(self, timer: QTimer, enabled: bool, interval_seconds: int) -> None:
        if enabled:
            timer.start(max(1, interval_seconds) * 1000)
        else:
            timer.stop()

    def key_info_page_auto_query(self) -> None:
        self.key_info_page.auto_query_if_possible()

    def credits_page_auto_query(self) -> None:
        self.credits_page.auto_query_if_possible()

    def refresh_floating_metrics(self) -> None:
        self.key_info_page.run_query_if_possible()
        self.credits_page.run_query_if_possible()

    def _create_floating_window(self, topmost: bool) -> FloatingWindow:
        window = FloatingWindow()
        window.set_topmost(topmost)
        window.refresh_requested.connect(self.refresh_floating_metrics)
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
                parent=self,
            )
            return
        self._sync_floating_window()
        center = self.frameGeometry().center()
        self.hide()
        target_x = center.x() - self.floating_window.width() // 2
        target_y = center.y() - self.floating_window.height() // 2
        self.floating_window.move(target_x, target_y)
        self.floating_window.show()
        self.floating_window.raise_()
        self.floating_window.activateWindow()

    def show_full_window(self) -> None:
        if self.floating_window is not None:
            self.floating_window.hide()
        self.show()
        self.raise_()
        self.activateWindow()

    def handle_query_success(self, mode: str, payload: dict[str, object]) -> None:
        summary = payload.get("summary", {})
        if not isinstance(summary, dict):
            return
        self._update_floating_metrics(mode, summary)
        self._evaluate_thresholds(mode, summary)

    def _update_floating_metrics(self, mode: str, summary: dict[str, object]) -> None:
        if mode == "key-info":
            value = summary.get("limit_remaining")
            self._floating_key_value = format_currency_value(value)
            self._floating_key_time = self.key_info_page.latest_success_time()
        else:
            value = summary.get("remaining_credits")
            self._floating_credits_value = format_currency_value(value)
            self._floating_credits_time = self.credits_page.latest_success_time()
        self._sync_floating_window()

    def _sync_floating_window(self) -> None:
        if self.floating_window is not None:
            self.floating_window.update_metrics(
                self._floating_key_value,
                self._floating_key_time,
                self._floating_credits_value,
                self._floating_credits_time,
            )
        self._sync_panel_label()

    def _evaluate_thresholds(self, mode: str, summary: dict[str, object]) -> None:
        payload = self.config_store.load() or {}
        if mode == "key-info":
            value = summary.get("limit_remaining")
            warning = payload.get("key_info_warning_threshold")
            critical = payload.get("key_info_critical_threshold")
            target = _tr("Key 配额")
            label = summary.get("label")
            subject = f"{target} · {label}" if isinstance(label, str) and label.strip() else target
        else:
            value = summary.get("remaining_credits")
            warning = payload.get("credits_warning_threshold")
            critical = payload.get("credits_critical_threshold")
            target = _tr("账户余额")
            subject = target

        if not isinstance(value, (int, float)):
            return

        level = self._classify_level(float(value), critical, warning)
        previous = self._alert_state.get(mode, "normal")
        if level == "normal":
            self._alert_state[mode] = "normal"
            return
        if level == previous:
            return

        self._alert_state[mode] = level
        if payload.get("notify_in_app", True):
            self._notify_in_app(level, target, subject, float(value))
        if payload.get("notify_system", True):
            self._notify_system(level, target, subject, float(value))
        self._maybe_send_webhook(mode, level, float(value))

    def _classify_level(self, value: float, critical: object, warning: object) -> str:
        try:
            critical_value = float(critical)
        except (TypeError, ValueError):
            critical_value = -1.0
        try:
            warning_value = float(warning)
        except (TypeError, ValueError):
            warning_value = -1.0

        if critical_value >= 0 and value <= critical_value:
            return "critical"
        if warning_value >= 0 and value <= warning_value:
            return "warning"
        return "normal"

    def _notify_in_app(self, level: str, target: str, subject: str, value: float) -> None:
        title = APP_DISPLAY_NAME
        content = _tr("{target} {level} 告警\n{subject} 当前值 {value:.4f}").format(
            target=target,
            level="Critical" if level == "critical" else "Warning",
            subject=subject,
            value=value,
        )
        factory = InfoBar.error if level == "critical" else InfoBar.warning
        factory(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=-1,
            parent=self,
        )

    def _notify_system(self, level: str, target: str, subject: str, value: float) -> None:
        title = APP_DISPLAY_NAME
        content = _tr("{target} {level} 告警\n{subject} 当前值 {value:.4f}").format(
            target=target,
            level="Critical" if level == "critical" else "Warning",
            subject=subject,
            value=value,
        )

        if self._sni_tray is not None and self._sni_tray.is_active:
            urgency = "critical" if level == "critical" else "normal"
            self._sni_tray.notify(title, content, urgency)
            return

        if self._tray_icon is None or not self._tray_icon.isVisible():
            return
        icon = QSystemTrayIcon.MessageIcon.Critical if level == "critical" else QSystemTrayIcon.MessageIcon.Warning
        self._tray_icon.showMessage(title, content, icon, 5000)

    def _setup_tray_icon(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        tray_icon = QSystemTrayIcon(self)
        icon = self._load_app_icon()
        if icon.isNull():
            icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)
        tray_icon.setIcon(icon)
        tray_icon.setToolTip(APP_DISPLAY_NAME)
        tray_icon.show()
        self._tray_icon = tray_icon

    def _load_app_icon(self) -> QIcon:
        base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
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

    def _maybe_send_webhook(self, mode: str, level: str, value: float) -> None:
        payload = self.config_store.load() or {}
        if mode == "key-info":
            enabled = bool(payload.get("notify_webhook_key_info_enabled"))
            url = payload.get("notify_webhook_key_info_url")
            only_critical = bool(payload.get("notify_webhook_key_info_only_critical", True))
            target = "key_info"
        else:
            enabled = bool(payload.get("notify_webhook_credits_enabled"))
            url = payload.get("notify_webhook_credits_url")
            only_critical = bool(payload.get("notify_webhook_credits_only_critical", True))
            target = "credits"

        if not enabled or not isinstance(url, str) or not url.strip():
            return
        if only_critical and level != "critical":
            return

        body = {
            "event": f"{target}_threshold_triggered",
            "level": level,
            "target": target,
            "current_value": value,
            "timestamp": datetime.now().strftime(DISPLAY_DATETIME_FORMAT),
        }
        threading.Thread(target=self._post_webhook, args=(url, body), daemon=True).start()

    def _post_webhook(self, url: str, body: dict[str, object]) -> None:
        data = json.dumps(body).encode("utf-8")
        request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=10):
                pass
        except Exception:
            pass

    def closeEvent(self, event: QCloseEvent) -> None:
        self.key_timer.stop()
        self.credits_timer.stop()
        if self._panel_label_timer is not None:
            self._panel_label_timer.stop()
        self.key_info_page.stop_worker()
        self.credits_page.stop_worker()
        self.about_page.stop_workers()
        if self.floating_window is not None:
            self.floating_window.blockSignals(True)
            self.floating_window.close_for_shutdown()
        if self._sni_tray is not None:
            self._sni_tray.unregister()
        if self._tray_icon is not None:
            self._tray_icon.hide()
        super().closeEvent(event)


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    config_store = ConfigStore()
    payload = config_store.load() or {}
    install_language(app, resolve_language_code(payload.get("ui_language")))
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    setThemeColor("#0F6CBD")

    window = MainWindow()
    window.show()
    return app.exec()
