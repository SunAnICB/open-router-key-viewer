from __future__ import annotations

import io
from collections.abc import Callable
from contextlib import redirect_stdout

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import (
        BodyLabel,
        CaptionLabel,
        ComboBox,
        ElevatedCardWidget,
        FluentIcon,
        InfoBar,
        InfoBarPosition,
        LineEdit,
        MessageBox,
        PrimaryPushButton,
        PushButton,
        SegmentedWidget,
        SingleDirectionScrollArea,
        StrongBodyLabel,
        SwitchButton,
        TextEdit,
        TitleLabel,
    )

from open_router_key_viewer.i18n import LANGUAGE_OPTIONS, resolve_language_code, tr
from open_router_key_viewer.services.config_store import ConfigStore
from open_router_key_viewer.ui.runtime import DISPLAY_BACKEND_OPTIONS, show_error_bar
from open_router_key_viewer.ui.widgets import MetricCard, PathActionCard, WarningCard

_tr = tr


class CachePage(QWidget):
    def __init__(
        self,
        config_store: ConfigStore,
        on_cache_changed: Callable[[], None],
        on_language_changed: Callable[[str], None],
        on_open_floating_window: Callable[[], None],
        floating_window_supported: bool,
        indicator_available: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("cache-page")
        self.config_store = config_store
        self.on_cache_changed = on_cache_changed
        self.on_language_changed = on_language_changed
        self.on_open_floating_window = on_open_floating_window
        self.floating_window_supported = floating_window_supported
        self.indicator_available = indicator_available
        self._mode = "data"
        self._file_text = ""
        self._build_ui()
        self.refresh_view()

    def _build_ui(self) -> None:
        existing_layout = self.layout()
        if isinstance(existing_layout, QVBoxLayout):
            outer = existing_layout
        else:
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = SingleDirectionScrollArea(self, Qt.Vertical)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.enableTransparentBackground()
        outer.addWidget(self.scroll_area)

        content = QWidget(self.scroll_area)
        self.scroll_area.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(36, 28, 36, 36)
        root.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(TitleLabel(_tr("配置"), self))
        header.addStretch(1)
        header.addWidget(CaptionLabel(_tr("显示后端"), self))
        self.display_backend_combo = ComboBox(self)
        for code, label in DISPLAY_BACKEND_OPTIONS:
            self.display_backend_combo.addItem(_tr(label), userData=code)
        self.display_backend_combo.currentIndexChanged.connect(self._handle_display_backend_changed)
        header.addWidget(self.display_backend_combo)
        header.addWidget(CaptionLabel(_tr("界面语言"), self))
        self.language_combo = ComboBox(self)
        for code, label in LANGUAGE_OPTIONS:
            self.language_combo.addItem(label, userData=code)
        self.language_combo.currentIndexChanged.connect(self._handle_language_changed)
        header.addWidget(self.language_combo)
        root.addLayout(header)
        root.addWidget(
            WarningCard(
                _tr("敏感信息提示"),
                _tr(
                    "保存后的 OpenRouter API Key、OpenRouter Management Key 和 Webhook URL 会以明文写入本地 config.json。 如果设备由多人共用，请谨慎启用保存功能。"
                ),
                self,
            )
        )

        summary_card = ElevatedCardWidget(self)
        summary_layout = QGridLayout(summary_card)
        summary_layout.setContentsMargins(24, 24, 24, 24)
        summary_layout.setHorizontalSpacing(12)
        summary_layout.setVerticalSpacing(12)

        self.dir_exists_card = PathActionCard(
            _tr("缓存目录"),
            _tr("删除整个缓存目录"),
            FluentIcon.DELETE,
            self._delete_config_dir,
            summary_card,
        )
        self.config_exists_card = PathActionCard(
            _tr("配置文件"),
            _tr("删除配置文件"),
            FluentIcon.DELETE,
            self._delete_config_file,
            summary_card,
        )
        self.entry_count_card = MetricCard(_tr("已缓存项目"), "-", "", summary_card)
        self.file_count_card = MetricCard(_tr("目录内文件"), "-", "", summary_card)

        summary_layout.addWidget(self.dir_exists_card, 0, 0)
        summary_layout.addWidget(self.config_exists_card, 0, 1)
        summary_layout.addWidget(self.file_count_card, 1, 0)
        summary_layout.addWidget(self.entry_count_card, 1, 1)
        root.addWidget(summary_card)

        floating_card = ElevatedCardWidget(self)
        floating_layout = QHBoxLayout(floating_card)
        floating_layout.setContentsMargins(24, 22, 24, 22)
        floating_layout.setSpacing(12)
        floating_text = QVBoxLayout()
        floating_text.setContentsMargins(0, 0, 0, 0)
        floating_text.setSpacing(4)
        floating_text.addWidget(StrongBodyLabel(_tr("悬浮小窗"), floating_card))
        floating_hint_text = (
            _tr("切换到仅显示剩余配额和账户余额的顶层小窗。")
            if self.floating_window_supported
            else _tr("当前仅在 X11/xcb 启动时支持悬浮小窗。")
        )
        floating_hint = CaptionLabel(floating_hint_text, floating_card)
        floating_hint.setWordWrap(True)
        floating_text.addWidget(floating_hint)
        floating_layout.addLayout(floating_text, 1)

        self.open_floating_button = PrimaryPushButton(_tr("打开悬浮小窗"), floating_card)
        self.open_floating_button.setIcon(FluentIcon.OPEN_PANE if hasattr(FluentIcon, "OPEN_PANE") else FluentIcon.HOME)
        self.open_floating_button.clicked.connect(self.on_open_floating_window)
        self.open_floating_button.setEnabled(self.floating_window_supported)
        floating_layout.addWidget(self.open_floating_button)
        root.addWidget(floating_card)

        indicator_card = ElevatedCardWidget(self)
        indicator_layout = QHBoxLayout(indicator_card)
        indicator_layout.setContentsMargins(24, 22, 24, 22)
        indicator_layout.setSpacing(12)
        indicator_text = QVBoxLayout()
        indicator_text.setContentsMargins(0, 0, 0, 0)
        indicator_text.setSpacing(4)
        indicator_text.addWidget(StrongBodyLabel(_tr("顶栏指示器"), indicator_card))
        indicator_hint_text = (
            _tr("在 GNOME 顶栏显示滚动的配额和余额数据（Ubuntu 开箱即用，其他发行版需安装 AppIndicator 扩展）。")
            if self.indicator_available
            else _tr("当前环境不支持顶栏指示器（需要 D-Bus StatusNotifierWatcher 服务）。")
        )
        indicator_hint = CaptionLabel(indicator_hint_text, indicator_card)
        indicator_hint.setWordWrap(True)
        indicator_text.addWidget(indicator_hint)
        indicator_layout.addLayout(indicator_text, 1)
        self.indicator_switch_row = self._create_switch_row(
            _tr("启用顶栏指示器"),
            "panel_indicator_enabled",
            indicator_card,
        )
        self.indicator_switch_row.setEnabled(self.indicator_available)
        indicator_layout.addWidget(self.indicator_switch_row)
        root.addWidget(indicator_card)

        auto_query_card = ElevatedCardWidget(self)
        auto_query_layout = QVBoxLayout(auto_query_card)
        auto_query_layout.setContentsMargins(24, 22, 24, 22)
        auto_query_layout.setSpacing(12)
        auto_query_layout.addWidget(StrongBodyLabel(_tr("自动查询"), auto_query_card))

        auto_query_hint = CaptionLabel(_tr("每个对象在同一行设置启动时查询、定时查询和查询间隔。"), auto_query_card)
        auto_query_layout.addWidget(auto_query_hint)

        self.auto_key_row = self._create_auto_query_row(
            _tr("Key 配额"),
            "auto_query_key_info",
            "poll_key_info_enabled",
            "poll_key_info_interval_seconds",
            "300",
            auto_query_card,
        )
        auto_query_layout.addWidget(self.auto_key_row)

        self.auto_credits_row = self._create_auto_query_row(
            _tr("账户余额"),
            "auto_query_credits",
            "poll_credits_enabled",
            "poll_credits_interval_seconds",
            "300",
            auto_query_card,
        )
        auto_query_layout.addWidget(self.auto_credits_row)
        root.addWidget(auto_query_card)

        alerts_card = ElevatedCardWidget(self)
        alerts_layout = QVBoxLayout(alerts_card)
        alerts_layout.setContentsMargins(24, 22, 24, 22)
        alerts_layout.setSpacing(12)
        alerts_layout.addWidget(StrongBodyLabel(_tr("告警与通知"), alerts_card))

        self.notify_in_app_row = self._create_switch_row(_tr("启用应用内通知"), "notify_in_app", alerts_card)
        alerts_layout.addWidget(self.notify_in_app_row)
        self.notify_system_row = self._create_switch_row(_tr("启用系统通知"), "notify_system", alerts_card)
        alerts_layout.addWidget(self.notify_system_row)

        self.key_warning_row = self._create_input_row(_tr("Key 配额 Warning 阈值"), "key_info_warning_threshold", "5.0", alerts_card)
        alerts_layout.addWidget(self.key_warning_row)
        self.key_critical_row = self._create_input_row(_tr("Key 配额 Critical 阈值"), "key_info_critical_threshold", "1.0", alerts_card)
        alerts_layout.addWidget(self.key_critical_row)
        self.credits_warning_row = self._create_input_row(_tr("账户余额 Warning 阈值"), "credits_warning_threshold", "10.0", alerts_card)
        alerts_layout.addWidget(self.credits_warning_row)
        self.credits_critical_row = self._create_input_row(_tr("账户余额 Critical 阈值"), "credits_critical_threshold", "2.0", alerts_card)
        alerts_layout.addWidget(self.credits_critical_row)

        self.webhook_key_switch_row = self._create_switch_row(_tr("启用 Key 配额 Webhook"), "notify_webhook_key_info_enabled", alerts_card)
        alerts_layout.addWidget(self.webhook_key_switch_row)
        self.webhook_key_only_critical_row = self._create_switch_row(_tr("Key 配额仅 Critical Webhook"), "notify_webhook_key_info_only_critical", alerts_card)
        alerts_layout.addWidget(self.webhook_key_only_critical_row)
        self.webhook_key_url_row = self._create_input_row(_tr("Key 配额 Webhook URL"), "notify_webhook_key_info_url", "https://example.com/key", alerts_card)
        alerts_layout.addWidget(self.webhook_key_url_row)

        self.webhook_credits_switch_row = self._create_switch_row(_tr("启用账户余额 Webhook"), "notify_webhook_credits_enabled", alerts_card)
        alerts_layout.addWidget(self.webhook_credits_switch_row)
        self.webhook_credits_only_critical_row = self._create_switch_row(_tr("账户余额仅 Critical Webhook"), "notify_webhook_credits_only_critical", alerts_card)
        alerts_layout.addWidget(self.webhook_credits_only_critical_row)
        self.webhook_credits_url_row = self._create_input_row(_tr("账户余额 Webhook URL"), "notify_webhook_credits_url", "https://example.com/credits", alerts_card)
        alerts_layout.addWidget(self.webhook_credits_url_row)
        root.addWidget(alerts_card)

        update_card = ElevatedCardWidget(self)
        update_layout = QVBoxLayout(update_card)
        update_layout.setContentsMargins(24, 22, 24, 22)
        update_layout.setSpacing(12)
        update_layout.addWidget(StrongBodyLabel(_tr("软件更新"), update_card))

        update_hint = CaptionLabel(_tr("控制软件启动时是否自动检查 GitHub Release 更新。"), update_card)
        update_hint.setWordWrap(True)
        update_layout.addWidget(update_hint)

        self.auto_update_row = self._create_switch_row(_tr("启动时自动检查更新"), "auto_check_updates", update_card)
        update_layout.addWidget(self.auto_update_row)
        root.addWidget(update_card)

        content_card = ElevatedCardWidget(self)
        content_layout = QVBoxLayout(content_card)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(12)

        content_header = QHBoxLayout()
        content_header.setSpacing(12)

        self.status_label = BodyLabel("", content_card)
        content_header.addWidget(self.status_label)
        content_header.addStretch(1)

        self.refresh_button = PrimaryPushButton(_tr("刷新"), content_card)
        self.refresh_button.setIcon(FluentIcon.SYNC)
        self.refresh_button.clicked.connect(self.refresh_view)
        content_header.addWidget(self.refresh_button)

        self.content_mode_switch = SegmentedWidget(content_card)
        self.content_mode_switch.addItem("data", _tr("解析数据"), lambda: self._show_mode("data"))
        self.content_mode_switch.addItem("file", _tr("原始文件"), lambda: self._show_mode("file"))
        content_header.addWidget(self.content_mode_switch)

        content_layout.addLayout(content_header)

        self.parsed_container = QWidget(content_card)
        self.parsed_layout = QVBoxLayout(self.parsed_container)
        self.parsed_layout.setContentsMargins(0, 0, 0, 0)
        self.parsed_layout.setSpacing(10)
        self.parsed_title = StrongBodyLabel(_tr("已解析的数据"), self.parsed_container)
        self.parsed_layout.addWidget(self.parsed_title)
        self.parsed_rows = QWidget(self.parsed_container)
        self.parsed_rows_layout = QVBoxLayout(self.parsed_rows)
        self.parsed_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.parsed_rows_layout.setSpacing(10)
        self.parsed_layout.addWidget(self.parsed_rows)
        content_layout.addWidget(self.parsed_container)

        self.content_output = TextEdit(content_card)
        self.content_output.setReadOnly(True)
        mono = QFont("JetBrains Mono")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.content_output.setFont(mono)
        self.content_output.setMinimumHeight(420)
        content_layout.addWidget(self.content_output)

        root.addWidget(content_card, 1)
        self._show_mode("data")

    def retranslate_ui(self) -> None:
        scroll_value = self.scroll_area.verticalScrollBar().value()
        while self.layout().count():
            item = self.layout().takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                while child_layout.count():
                    child_item = child_layout.takeAt(0)
                    child_widget = child_item.widget()
                    if child_widget is not None:
                        child_widget.deleteLater()
        self._build_ui()
        self.refresh_view()
        QTimer.singleShot(0, lambda: self.scroll_area.verticalScrollBar().setValue(scroll_value))

    def refresh_view(self) -> None:
        snapshot = self.config_store.inspect()
        loaded_config = snapshot.get("loaded_config")
        payload = loaded_config if isinstance(loaded_config, dict) else {}
        language_code = resolve_language_code(payload.get("ui_language"))
        display_backend = self._resolve_display_backend(payload.get("display_backend"))
        files = snapshot.get("files", [])
        file_count = sum(1 for item in files if item.get("type") == "file")
        entry_count = len(payload)

        self.dir_exists_card.set_content(
            _tr("已存在") if snapshot["dir_exists"] else _tr("不存在"),
            _tr("缓存目录路径"),
            str(snapshot["config_dir"]),
            bool(snapshot["dir_exists"]),
        )
        self.config_exists_card.set_content(
            _tr("已存在") if snapshot["config_exists"] else _tr("不存在"),
            _tr("config.json 文件路径"),
            str(snapshot["config_path"]),
            bool(snapshot["config_exists"]),
        )
        self.entry_count_card.set_value(str(entry_count), _tr("当前解析出的缓存键数量"))
        self.file_count_card.set_value(str(file_count), _tr("缓存目录内的文件数量"))

        self.status_label.setText(_tr("已解析本地缓存") if snapshot["config_exists"] else _tr("未找到配置文件"))
        self._sync_display_backend_combo(display_backend)
        self._sync_language_combo(language_code)
        self._sync_auto_query_row(self.auto_key_row, bool(payload.get("auto_query_key_info", False)), bool(payload.get("poll_key_info_enabled", False)), payload.get("poll_key_info_interval_seconds", 300))
        self._sync_auto_query_row(self.auto_credits_row, bool(payload.get("auto_query_credits", False)), bool(payload.get("poll_credits_enabled", False)), payload.get("poll_credits_interval_seconds", 300))
        self._sync_switch_state(self.auto_update_row, bool(payload.get("auto_check_updates", True)))
        self._sync_switch_state(self.indicator_switch_row, bool(payload.get("panel_indicator_enabled", False)))
        self._sync_switch_state(self.notify_in_app_row, bool(payload.get("notify_in_app", True)))
        self._sync_switch_state(self.notify_system_row, bool(payload.get("notify_system", True)))
        self._sync_switch_state(self.webhook_key_switch_row, bool(payload.get("notify_webhook_key_info_enabled", False)))
        self._sync_switch_state(self.webhook_key_only_critical_row, bool(payload.get("notify_webhook_key_info_only_critical", True)))
        self._sync_switch_state(self.webhook_credits_switch_row, bool(payload.get("notify_webhook_credits_enabled", False)))
        self._sync_switch_state(self.webhook_credits_only_critical_row, bool(payload.get("notify_webhook_credits_only_critical", True)))

        self._sync_input_row(self.key_warning_row, payload.get("key_info_warning_threshold", 5.0))
        self._sync_input_row(self.key_critical_row, payload.get("key_info_critical_threshold", 1.0))
        self._sync_input_row(self.credits_warning_row, payload.get("credits_warning_threshold", 10.0))
        self._sync_input_row(self.credits_critical_row, payload.get("credits_critical_threshold", 2.0))
        self._sync_input_row(self.webhook_key_url_row, payload.get("notify_webhook_key_info_url", ""))
        self._sync_input_row(self.webhook_credits_url_row, payload.get("notify_webhook_credits_url", ""))

        self._render_parsed_data(payload)
        self._file_text = self.config_store.read_raw_config() or _tr("未找到 config.json 文件")
        self.content_output.setPlainText(self._file_text)
        self._show_mode(self._mode)

    def _resolve_display_backend(self, value: object) -> str:
        if isinstance(value, str) and value in {code for code, _ in DISPLAY_BACKEND_OPTIONS}:
            return value
        return "auto"

    def _sync_display_backend_combo(self, backend: str) -> None:
        index = self.display_backend_combo.findData(backend)
        if index < 0:
            index = 0
        self.display_backend_combo.blockSignals(True)
        self.display_backend_combo.setCurrentIndex(index)
        self.display_backend_combo.blockSignals(False)

    def _handle_display_backend_changed(self, index: int) -> None:
        _ = index
        backend = self.display_backend_combo.currentData()
        if not isinstance(backend, str):
            return
        current_backend = self._resolve_display_backend((self.config_store.load() or {}).get("display_backend"))
        if backend == current_backend:
            return
        if backend == "auto":
            self.config_store.delete_value("display_backend")
        else:
            self.config_store.save_value("display_backend", backend)
        InfoBar.success(
            title=_tr("已保存"),
            content=_tr("显示后端已更新，重启后生效"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self.window(),
        )
        self.on_cache_changed()

    def _sync_language_combo(self, language_code: str) -> None:
        index = self.language_combo.findData(language_code)
        if index < 0:
            index = 0
        self.language_combo.blockSignals(True)
        self.language_combo.setCurrentIndex(index)
        self.language_combo.blockSignals(False)

    def _handle_language_changed(self, index: int) -> None:
        _ = index
        language_code = self.language_combo.currentData()
        if not isinstance(language_code, str):
            return
        current_language = resolve_language_code((self.config_store.load() or {}).get("ui_language"))
        if language_code == current_language:
            return
        self.config_store.save_value("ui_language", language_code)
        self.on_language_changed(language_code)

    def _show_mode(self, mode: str) -> None:
        self._mode = mode
        showing_data = mode == "data"
        self.parsed_container.setVisible(showing_data)
        self.content_output.setVisible(not showing_data)
        self.content_mode_switch.setCurrentItem(mode)

    def _display_config_key(self, key: str) -> str:
        mapping = {
            "api_key": "OpenRouter API Key",
            "management_key": "OpenRouter Management Key",
            "display_backend": "显示后端",
            "ui_language": "界面语言",
            "auto_check_updates": "启动时自动检查更新",
            "auto_query_key_info": "启动时自动查询 Key 配额",
            "auto_query_credits": "启动时自动查询账户余额",
            "poll_key_info_enabled": "启用 Key 配额定时查询",
            "poll_key_info_interval_seconds": "Key 配额间隔（秒）",
            "poll_credits_enabled": "启用账户余额定时查询",
            "poll_credits_interval_seconds": "账户余额间隔（秒）",
            "panel_indicator_enabled": "启用顶栏指示器",
            "notify_in_app": "启用应用内通知",
            "notify_system": "启用系统通知",
            "key_info_warning_threshold": "Key 配额 Warning 阈值",
            "key_info_critical_threshold": "Key 配额 Critical 阈值",
            "credits_warning_threshold": "账户余额 Warning 阈值",
            "credits_critical_threshold": "账户余额 Critical 阈值",
            "notify_webhook_key_info_enabled": "启用 Key 配额 Webhook",
            "notify_webhook_key_info_only_critical": "Key 配额仅 Critical Webhook",
            "notify_webhook_key_info_url": "Key 配额 Webhook URL",
            "notify_webhook_credits_enabled": "启用账户余额 Webhook",
            "notify_webhook_credits_only_critical": "账户余额仅 Critical Webhook",
            "notify_webhook_credits_url": "账户余额 Webhook URL",
        }
        return _tr(mapping.get(key, key))

    def _render_parsed_data(self, loaded_config: object) -> None:
        if not isinstance(loaded_config, dict) or not loaded_config:
            rows = [(_tr("状态"), _tr("暂无数据"), "")]
        else:
            rows = [
                (self._display_config_key(key), self._display_config_value(key, value), "")
                for key, value in loaded_config.items()
            ]
        self._render_property_rows(self.parsed_rows_layout, rows)

    def _display_config_value(self, key: str, value: object) -> str:
        if key == "ui_language" and isinstance(value, str):
            label_map = {code: label for code, label in LANGUAGE_OPTIONS}
            return label_map.get(value, value)
        if key == "display_backend" and isinstance(value, str):
            label_map = {code: _tr(label) for code, label in DISPLAY_BACKEND_OPTIONS}
            return label_map.get(value, value)
        return str(value)

    def _render_property_rows(
        self,
        layout: QVBoxLayout,
        rows: list[tuple[str, str, str]],
    ) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for label, value, note in rows:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(12)

            label_widget = CaptionLabel(label, row)
            label_widget.setMinimumWidth(96)
            row_layout.addWidget(label_widget)

            value_widget = StrongBodyLabel(value, row)
            value_widget.setMinimumWidth(280)
            row_layout.addWidget(value_widget, 1)

            if note:
                note_widget = CaptionLabel(note, row)
                note_widget.setStyleSheet("color: rgba(0, 0, 0, 0.62);")
                note_widget.setMinimumWidth(180)
                row_layout.addWidget(note_widget, 1)

            layout.addWidget(row)
        layout.addStretch(1)

    def _create_switch_row(self, text: str, config_key: str, parent: QWidget) -> QWidget:
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        label = StrongBodyLabel(text, row)
        layout.addWidget(label)
        layout.addStretch(1)

        switch = SwitchButton(row)
        switch.checkedChanged.connect(
            lambda checked, key=config_key, button=switch: self._toggle_auto_query(key, button, checked)
        )
        layout.addWidget(switch)

        row._switch = switch  # type: ignore[attr-defined]
        return row

    def _create_auto_query_row(
        self,
        title: str,
        auto_query_key: str,
        poll_key: str,
        interval_key: str,
        placeholder: str,
        parent: QWidget,
    ) -> QWidget:
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        title_label = StrongBodyLabel(title, row)
        title_label.setMinimumWidth(96)
        layout.addWidget(title_label)

        auto_label = CaptionLabel(_tr("启动时查询"), row)
        layout.addWidget(auto_label)

        auto_switch = SwitchButton(row)
        auto_switch.checkedChanged.connect(
            lambda checked, key=auto_query_key, button=auto_switch: self._toggle_auto_query(key, button, checked)
        )
        layout.addWidget(auto_switch)

        poll_label = CaptionLabel(_tr("定时查询"), row)
        layout.addWidget(poll_label)

        poll_switch = SwitchButton(row)
        poll_switch.checkedChanged.connect(
            lambda checked, key=poll_key, button=poll_switch: self._toggle_auto_query(key, button, checked)
        )
        layout.addWidget(poll_switch)

        interval_label = CaptionLabel(_tr("查询间隔（秒）"), row)
        layout.addWidget(interval_label)

        interval_input = LineEdit(row)
        interval_input.setPlaceholderText(placeholder)
        interval_input.setFixedWidth(120)
        interval_input.editingFinished.connect(
            lambda key=interval_key, line_edit=interval_input: self._save_input_value(
                key, line_edit.text().strip(), placeholder
            )
        )
        layout.addWidget(interval_input)
        layout.addStretch(1)

        row._auto_switch = auto_switch  # type: ignore[attr-defined]
        row._poll_switch = poll_switch  # type: ignore[attr-defined]
        row._line_edit = interval_input  # type: ignore[attr-defined]
        return row

    def _create_input_row(self, text: str, config_key: str, placeholder: str, parent: QWidget) -> QWidget:
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        label = StrongBodyLabel(text, row)
        label.setMinimumWidth(220)
        layout.addWidget(label)

        line_edit = LineEdit(row)
        line_edit.setPlaceholderText(placeholder)
        layout.addWidget(line_edit, 1)

        save_button = PushButton(_tr("保存"), row)
        save_button.clicked.connect(
            lambda: self._save_input_value(config_key, line_edit.text().strip(), placeholder)
        )
        layout.addWidget(save_button)

        row._line_edit = line_edit  # type: ignore[attr-defined]
        return row

    def _toggle_auto_query(self, config_key: str, button: SwitchButton, checked: bool) -> None:
        self.config_store.save_flag(config_key, checked)
        self._sync_switch_button(button, checked)
        self.on_cache_changed()

    def _sync_switch_state(self, row: QWidget, checked: bool) -> None:
        button = row._switch  # type: ignore[attr-defined]
        button.blockSignals(True)
        button.setChecked(checked)
        button.blockSignals(False)
        self._sync_switch_button(button, checked)

    def _sync_auto_query_row(
        self,
        row: QWidget,
        auto_checked: bool,
        poll_checked: bool,
        interval_value: object,
    ) -> None:
        auto_switch = row._auto_switch  # type: ignore[attr-defined]
        poll_switch = row._poll_switch  # type: ignore[attr-defined]
        line_edit = row._line_edit  # type: ignore[attr-defined]

        for button, checked in ((auto_switch, auto_checked), (poll_switch, poll_checked)):
            button.blockSignals(True)
            button.setChecked(checked)
            button.blockSignals(False)
            self._sync_switch_button(button, checked)

        line_edit.blockSignals(True)
        line_edit.setText("" if interval_value is None else str(interval_value))
        line_edit.blockSignals(False)

    def _sync_switch_button(self, button: SwitchButton, checked: bool) -> None:
        _ = checked
        button.setOnText(_tr("开启"))
        button.setOffText(_tr("关闭"))

    def _save_input_value(self, config_key: str, raw_value: str, placeholder: str) -> None:
        _ = placeholder
        if not raw_value:
            self.config_store.delete_value(config_key)
        else:
            value: object = raw_value
            if config_key.endswith("_interval_seconds"):
                try:
                    value = max(1, int(raw_value))
                except ValueError:
                    self._show_error(_tr("间隔必须是整数秒"))
                    return
            elif config_key.endswith("_threshold"):
                try:
                    value = float(raw_value)
                except ValueError:
                    self._show_error(_tr("阈值必须是数字"))
                    return
            self.config_store.save_value(config_key, value)

        self.on_cache_changed()
        InfoBar.success(
            title=_tr("已保存"),
            content=_tr("配置已更新"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=1500,
            parent=self.window(),
        )

    def _sync_input_row(self, row: QWidget, value: object) -> None:
        line_edit = row._line_edit  # type: ignore[attr-defined]
        line_edit.blockSignals(True)
        line_edit.setText("" if value is None else str(value))
        line_edit.blockSignals(False)

    def _show_error(self, message: str) -> None:
        show_error_bar(self.window(), _tr("配置无效"), message)

    def _delete_config_file(self) -> None:
        if not self._confirm(_tr("删除配置文件"), _tr("确认删除 config.json 吗？")):
            return
        self.config_store.delete_config_file()
        self.on_cache_changed()
        InfoBar.success(
            title=_tr("已删除"),
            content=_tr("配置文件已删除"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self.window(),
        )

    def _delete_config_dir(self) -> None:
        if not self._confirm(_tr("删除缓存目录"), _tr("确认删除整个 ~/.config/open-router-key-viewer 目录吗？")):
            return
        self.config_store.delete_config_dir()
        self.on_cache_changed()
        InfoBar.success(
            title=_tr("已删除"),
            content=_tr("缓存目录已删除"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self.window(),
        )

    def _confirm(self, title: str, message: str) -> bool:
        box = MessageBox(title, message, self.window())
        box.yesButton.setText(_tr("确认"))
        box.cancelButton.setText(_tr("取消"))
        return bool(box.exec())

