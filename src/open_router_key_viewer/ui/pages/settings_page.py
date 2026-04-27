from __future__ import annotations

import io
from collections.abc import Callable
from contextlib import redirect_stdout
from dataclasses import dataclass

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
        MessageBox,
        PrimaryPushButton,
        SegmentedWidget,
        SingleDirectionScrollArea,
        SmoothMode,
        StrongBodyLabel,
        TextEdit,
        TitleLabel,
    )

from open_router_key_viewer.core.settings_coordinator import SettingsActionResult, SettingsCoordinator
from open_router_key_viewer.i18n import LANGUAGE_OPTIONS, tr
from open_router_key_viewer.state import ConfigKey
from open_router_key_viewer.state.app_metadata import DISPLAY_BACKEND_OPTIONS, THEME_MODE_OPTIONS
from open_router_key_viewer.state.settings_view_model import SettingsSnapshotViewModel
from open_router_key_viewer.ui.pages.settings_widgets import (
    AutoQuerySettingRow,
    InputSettingRow,
    PropertyRowsPanel,
    SwitchSettingRow,
)
from open_router_key_viewer.ui.runtime import show_error_bar
from open_router_key_viewer.ui.widgets import MetricCard, PathActionCard, WarningCard

_tr = tr


@dataclass(frozen=True, slots=True)
class SwitchBinding:
    label: str
    key: ConfigKey


@dataclass(frozen=True, slots=True)
class InputBinding:
    label: str
    key: ConfigKey
    placeholder: str


@dataclass(frozen=True, slots=True)
class AutoQueryBinding:
    title: str
    auto_key: ConfigKey
    poll_key: ConfigKey
    interval_key: ConfigKey
    placeholder: str = "300"


AUTO_QUERY_BINDINGS = (
    AutoQueryBinding(
        "Key 配额",
        ConfigKey.AUTO_QUERY_KEY_INFO,
        ConfigKey.POLL_KEY_INFO_ENABLED,
        ConfigKey.POLL_KEY_INFO_INTERVAL_SECONDS,
    ),
    AutoQueryBinding(
        "账户余额",
        ConfigKey.AUTO_QUERY_CREDITS,
        ConfigKey.POLL_CREDITS_ENABLED,
        ConfigKey.POLL_CREDITS_INTERVAL_SECONDS,
    ),
)

ALERT_SWITCH_BINDINGS = (
    SwitchBinding("启用应用内通知", ConfigKey.NOTIFY_IN_APP),
    SwitchBinding("启用系统通知", ConfigKey.NOTIFY_SYSTEM),
    SwitchBinding("启用 Key 配额 Webhook", ConfigKey.NOTIFY_WEBHOOK_KEY_INFO_ENABLED),
    SwitchBinding("Key 配额仅 Critical Webhook", ConfigKey.NOTIFY_WEBHOOK_KEY_INFO_ONLY_CRITICAL),
    SwitchBinding("启用账户余额 Webhook", ConfigKey.NOTIFY_WEBHOOK_CREDITS_ENABLED),
    SwitchBinding("账户余额仅 Critical Webhook", ConfigKey.NOTIFY_WEBHOOK_CREDITS_ONLY_CRITICAL),
)

ALERT_INPUT_BINDINGS = (
    InputBinding("Key 配额 Warning 阈值", ConfigKey.KEY_INFO_WARNING_THRESHOLD, "5.0"),
    InputBinding("Key 配额 Critical 阈值", ConfigKey.KEY_INFO_CRITICAL_THRESHOLD, "1.0"),
    InputBinding("账户余额 Warning 阈值", ConfigKey.CREDITS_WARNING_THRESHOLD, "10.0"),
    InputBinding("账户余额 Critical 阈值", ConfigKey.CREDITS_CRITICAL_THRESHOLD, "2.0"),
    InputBinding("Key 配额 Webhook URL", ConfigKey.NOTIFY_WEBHOOK_KEY_INFO_URL, "https://example.com/key"),
    InputBinding("账户余额 Webhook URL", ConfigKey.NOTIFY_WEBHOOK_CREDITS_URL, "https://example.com/credits"),
)


class CachePage(QWidget):
    def __init__(
        self,
        settings_coordinator: SettingsCoordinator,
        on_runtime_settings_changed: Callable[[], None],
        on_global_config_changed: Callable[[], None],
        on_language_changed: Callable[[str], None],
        on_theme_changed: Callable[[str], None],
        on_open_floating_window: Callable[[], None],
        floating_window_supported: bool,
        indicator_available: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("cache-page")
        self.on_runtime_settings_changed = on_runtime_settings_changed
        self.on_global_config_changed = on_global_config_changed
        self.on_language_changed = on_language_changed
        self.on_theme_changed = on_theme_changed
        self.on_open_floating_window = on_open_floating_window
        self.floating_window_supported = floating_window_supported
        self.indicator_available = indicator_available
        self._mode = "data"
        self._file_text = ""
        self._settings_coordinator = settings_coordinator
        self._switch_rows: dict[ConfigKey, SwitchSettingRow] = {}
        self._input_rows: dict[ConfigKey, InputSettingRow] = {}
        self._auto_query_rows: list[tuple[AutoQueryBinding, AutoQuerySettingRow]] = []
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
        self.scroll_area.setSmoothMode(SmoothMode.NO_SMOOTH)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll_area)

        content = QWidget(self.scroll_area)
        self.scroll_area.setWidget(content)
        self.scroll_area.enableTransparentBackground()
        content.setStyleSheet("background: transparent;")

        root = QVBoxLayout(content)
        root.setContentsMargins(36, 28, 36, 36)
        root.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(12)
        self.page_title_label = TitleLabel(_tr("配置"), self)
        header.addWidget(self.page_title_label)
        header.addStretch(1)
        self.display_backend_label = CaptionLabel(_tr("显示后端"), self)
        header.addWidget(self.display_backend_label)
        self.display_backend_combo = ComboBox(self)
        for code, label in DISPLAY_BACKEND_OPTIONS:
            self.display_backend_combo.addItem(_tr(label), userData=code)
        self.display_backend_combo.currentIndexChanged.connect(self._handle_display_backend_changed)
        header.addWidget(self.display_backend_combo)
        self.language_label = CaptionLabel(_tr("界面语言"), self)
        header.addWidget(self.language_label)
        self.language_combo = ComboBox(self)
        for code, label in LANGUAGE_OPTIONS:
            self.language_combo.addItem(label, userData=code)
        self.language_combo.currentIndexChanged.connect(self._handle_language_changed)
        header.addWidget(self.language_combo)
        self.theme_mode_label = CaptionLabel(_tr("主题模式"), self)
        header.addWidget(self.theme_mode_label)
        self.theme_mode_combo = ComboBox(self)
        for code, label in THEME_MODE_OPTIONS:
            self.theme_mode_combo.addItem(_tr(label), userData=code)
        self.theme_mode_combo.currentIndexChanged.connect(self._handle_theme_mode_changed)
        header.addWidget(self.theme_mode_combo)
        root.addLayout(header)

        self.warning_card = WarningCard(
            _tr("敏感信息提示"),
            _tr(
                "保存后的 OpenRouter API Key、OpenRouter Management Key 和 Webhook URL 会以明文写入本地 config.json。 如果设备由多人共用，请谨慎启用保存功能。"
            ),
            self,
        )
        root.addWidget(self.warning_card)

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

        root.addWidget(self._build_floating_card())
        root.addWidget(self._build_runtime_card())
        root.addWidget(self._build_indicator_card())
        root.addWidget(self._build_auto_query_card())
        root.addWidget(self._build_alerts_card())
        root.addWidget(self._build_update_card())
        root.addWidget(self._build_content_card(), 1)
        self._show_mode("data")

    def _build_floating_card(self) -> QWidget:
        card = ElevatedCardWidget(self)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        self.floating_title_label = StrongBodyLabel(_tr("悬浮小窗"), card)
        text_layout.addWidget(self.floating_title_label)
        hint_text = (
            _tr("切换到仅显示剩余配额和账户余额的顶层小窗。")
            if self.floating_window_supported
            else _tr("当前仅在 X11/xcb 启动时支持悬浮小窗。")
        )
        self.floating_hint_label = CaptionLabel(hint_text, card)
        self.floating_hint_label.setWordWrap(True)
        text_layout.addWidget(self.floating_hint_label)
        layout.addLayout(text_layout, 1)

        self.open_floating_button = PrimaryPushButton(_tr("打开悬浮小窗"), card)
        self.open_floating_button.setIcon(FluentIcon.OPEN_PANE if hasattr(FluentIcon, "OPEN_PANE") else FluentIcon.HOME)
        self.open_floating_button.clicked.connect(self.on_open_floating_window)
        self.open_floating_button.setEnabled(self.floating_window_supported)
        layout.addWidget(self.open_floating_button)
        return card

    def _build_indicator_card(self) -> QWidget:
        card = ElevatedCardWidget(self)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        self.indicator_title_label = StrongBodyLabel(_tr("顶栏指示器"), card)
        text_layout.addWidget(self.indicator_title_label)
        hint_text = (
            _tr("在 GNOME 顶栏显示滚动的配额和余额数据（Ubuntu 开箱即用，其他发行版需安装 AppIndicator 扩展）。")
            if self.indicator_available
            else _tr("当前环境不支持顶栏指示器（需要 D-Bus StatusNotifierWatcher 服务）。")
        )
        self.indicator_hint_label = CaptionLabel(hint_text, card)
        self.indicator_hint_label.setWordWrap(True)
        text_layout.addWidget(self.indicator_hint_label)
        layout.addLayout(text_layout, 1)

        self.indicator_switch_row = self._create_switch_row(_tr("启用顶栏指示器"), ConfigKey.PANEL_INDICATOR_ENABLED, card)
        self.indicator_switch_row.setEnabled(self.indicator_available)
        layout.addWidget(self.indicator_switch_row)
        return card

    def _build_runtime_card(self) -> QWidget:
        card = ElevatedCardWidget(self)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        self.runtime_title_label = StrongBodyLabel(_tr("运行行为"), card)
        text_layout.addWidget(self.runtime_title_label)
        self.runtime_hint_label = CaptionLabel(
            _tr("单实例用于阻止重复启动；“关闭窗口时驻留后台”仅在启用单实例模式后可用。"),
            card,
        )
        self.runtime_hint_label.setWordWrap(True)
        text_layout.addWidget(self.runtime_hint_label)
        layout.addLayout(text_layout, 1)

        switches = QVBoxLayout()
        switches.setContentsMargins(0, 0, 0, 0)
        switches.setSpacing(8)
        self.single_instance_row = self._create_switch_row(_tr("启用单实例模式"), ConfigKey.SINGLE_INSTANCE_ENABLED, card)
        self.background_resident_row = self._create_switch_row(_tr("关闭窗口时驻留后台"), ConfigKey.BACKGROUND_RESIDENT_ON_CLOSE, card)
        switches.addWidget(self.single_instance_row)
        switches.addWidget(self.background_resident_row)
        layout.addLayout(switches)
        return card

    def _build_auto_query_card(self) -> QWidget:
        card = ElevatedCardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        self.auto_query_title_label = StrongBodyLabel(_tr("自动查询"), card)
        layout.addWidget(self.auto_query_title_label)
        self.auto_query_hint_label = CaptionLabel(_tr("每个对象在同一行设置启动时查询、定时查询和查询间隔。"), card)
        layout.addWidget(self.auto_query_hint_label)

        for binding in AUTO_QUERY_BINDINGS:
            row = self._create_auto_query_row(binding, card)
            self._auto_query_rows.append((binding, row))
            layout.addWidget(row)
        return card

    def _build_alerts_card(self) -> QWidget:
        card = ElevatedCardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        self.alerts_title_label = StrongBodyLabel(_tr("告警与通知"), card)
        layout.addWidget(self.alerts_title_label)

        for binding in ALERT_SWITCH_BINDINGS:
            layout.addWidget(self._create_switch_row(_tr(binding.label), binding.key, card))
        for binding in ALERT_INPUT_BINDINGS:
            layout.addWidget(self._create_input_row(_tr(binding.label), binding.key, binding.placeholder, card))
        return card

    def _build_update_card(self) -> QWidget:
        card = ElevatedCardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        self.update_title_label = StrongBodyLabel(_tr("软件更新"), card)
        layout.addWidget(self.update_title_label)
        self.update_hint_label = CaptionLabel(_tr("控制软件启动时是否自动检查 GitHub Release 更新。"), card)
        self.update_hint_label.setWordWrap(True)
        layout.addWidget(self.update_hint_label)
        self.auto_update_row = self._create_switch_row(_tr("启动时自动检查更新"), ConfigKey.AUTO_CHECK_UPDATES, card)
        layout.addWidget(self.auto_update_row)
        return card

    def _build_content_card(self) -> QWidget:
        card = ElevatedCardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)
        self.status_label = BodyLabel("", card)
        header.addWidget(self.status_label)
        header.addStretch(1)

        self.refresh_button = PrimaryPushButton(_tr("刷新"), card)
        self.refresh_button.setIcon(FluentIcon.SYNC)
        self.refresh_button.clicked.connect(self.refresh_view)
        header.addWidget(self.refresh_button)

        self.content_mode_switch = SegmentedWidget(card)
        self.content_mode_switch.addItem("data", _tr("解析数据"), lambda: self._show_mode("data"))
        self.content_mode_switch.addItem("file", _tr("原始文件"), lambda: self._show_mode("file"))
        header.addWidget(self.content_mode_switch)
        layout.addLayout(header)

        self.parsed_container = QWidget(card)
        self.parsed_layout = QVBoxLayout(self.parsed_container)
        self.parsed_layout.setContentsMargins(0, 0, 0, 0)
        self.parsed_layout.setSpacing(10)
        self.parsed_title = StrongBodyLabel(_tr("已解析的数据"), self.parsed_container)
        self.parsed_layout.addWidget(self.parsed_title)
        self.parsed_rows = PropertyRowsPanel(self.parsed_container)
        self.parsed_layout.addWidget(self.parsed_rows)
        layout.addWidget(self.parsed_container)

        self.content_output = TextEdit(card)
        self.content_output.setReadOnly(True)
        mono = QFont("JetBrains Mono")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.content_output.setFont(mono)
        self.content_output.setMinimumHeight(420)
        layout.addWidget(self.content_output)
        return card

    def retranslate_ui(self) -> None:
        self.page_title_label.setText(_tr("配置"))
        self.display_backend_label.setText(_tr("显示后端"))
        self.language_label.setText(_tr("界面语言"))
        self.theme_mode_label.setText(_tr("主题模式"))
        self.warning_card.retranslate_ui(
            _tr("敏感信息提示"),
            _tr(
                "保存后的 OpenRouter API Key、OpenRouter Management Key 和 Webhook URL 会以明文写入本地 config.json。 如果设备由多人共用，请谨慎启用保存功能。"
            ),
        )
        self.dir_exists_card.set_labels(_tr("缓存目录"), _tr("删除整个缓存目录"))
        self.config_exists_card.set_labels(_tr("配置文件"), _tr("删除配置文件"))
        self.entry_count_card.set_title(_tr("已缓存项目"))
        self.file_count_card.set_title(_tr("目录内文件"))
        self.floating_title_label.setText(_tr("悬浮小窗"))
        self.floating_hint_label.setText(
            _tr("切换到仅显示剩余配额和账户余额的顶层小窗。")
            if self.floating_window_supported
            else _tr("当前仅在 X11/xcb 启动时支持悬浮小窗。")
        )
        self.open_floating_button.setText(_tr("打开悬浮小窗"))
        self.indicator_title_label.setText(_tr("顶栏指示器"))
        self.indicator_hint_label.setText(
            _tr("在 GNOME 顶栏显示滚动的配额和余额数据（Ubuntu 开箱即用，其他发行版需安装 AppIndicator 扩展）。")
            if self.indicator_available
            else _tr("当前环境不支持顶栏指示器（需要 D-Bus StatusNotifierWatcher 服务）。")
        )
        self.indicator_switch_row.retranslate_ui(_tr("启用顶栏指示器"))
        self.runtime_title_label.setText(_tr("运行行为"))
        self.runtime_hint_label.setText(_tr("单实例用于阻止重复启动；“关闭窗口时驻留后台”仅在启用单实例模式后可用。"))
        self.single_instance_row.retranslate_ui(_tr("启用单实例模式"))
        self.background_resident_row.retranslate_ui(_tr("关闭窗口时驻留后台"))
        self.auto_query_title_label.setText(_tr("自动查询"))
        self.auto_query_hint_label.setText(_tr("每个对象在同一行设置启动时查询、定时查询和查询间隔。"))
        for binding, row in self._auto_query_rows:
            row.retranslate_ui(_tr(binding.title), binding.placeholder)
        self.alerts_title_label.setText(_tr("告警与通知"))
        self._retranslate_setting_rows()
        self.update_title_label.setText(_tr("软件更新"))
        self.update_hint_label.setText(_tr("控制软件启动时是否自动检查 GitHub Release 更新。"))
        self.auto_update_row.retranslate_ui(_tr("启动时自动检查更新"))
        self.refresh_button.setText(_tr("刷新"))
        self.parsed_title.setText(_tr("已解析的数据"))
        self.content_mode_switch.setItemText("data", _tr("解析数据"))
        self.content_mode_switch.setItemText("file", _tr("原始文件"))
        self._retranslate_combo_items()
        self.refresh_view()

    def sync_runtime_capabilities(self, *, floating_window_supported: bool, indicator_available: bool) -> None:
        self.floating_window_supported = floating_window_supported
        self.indicator_available = indicator_available
        self.floating_hint_label.setText(
            _tr("切换到仅显示剩余配额和账户余额的顶层小窗。")
            if self.floating_window_supported
            else _tr("当前仅在 X11/xcb 启动时支持悬浮小窗。")
        )
        self.open_floating_button.setEnabled(self.floating_window_supported)
        self.indicator_hint_label.setText(
            _tr("在 GNOME 顶栏显示滚动的配额和余额数据（Ubuntu 开箱即用，其他发行版需安装 AppIndicator 扩展）。")
            if self.indicator_available
            else _tr("当前环境不支持顶栏指示器（需要 D-Bus StatusNotifierWatcher 服务）。")
        )
        self.indicator_switch_row.setEnabled(self.indicator_available)

    def refresh_view(self) -> None:
        snapshot_view = self._settings_coordinator.build_snapshot()
        config = snapshot_view.config
        self._apply_snapshot_view(snapshot_view)
        self._sync_display_backend_combo(config.display_backend)
        self._sync_language_combo(config.ui_language)
        self._sync_theme_mode_combo(config.theme_mode)
        for binding, row in self._auto_query_rows:
            row.sync_state(
                bool(getattr(config, binding.auto_key.value)),
                bool(getattr(config, binding.poll_key.value)),
                getattr(config, binding.interval_key.value),
            )
        for key, row in self._switch_rows.items():
            row.sync_state(bool(getattr(config, key.value)))
        self._sync_runtime_option_state(config.single_instance_enabled)

        for key, row in self._input_rows.items():
            row.sync_value(getattr(config, key.value))

        self._file_text = _tr(snapshot_view.raw_file_text)
        self.content_output.setPlainText(self._file_text)
        self._show_mode(self._mode)

    def _apply_snapshot_view(self, view_model: SettingsSnapshotViewModel) -> None:
        self.dir_exists_card.set_content(
            _tr(view_model.directory.status),
            _tr(view_model.directory.note),
            view_model.directory.path,
            view_model.directory.exists,
        )
        self.config_exists_card.set_content(
            _tr(view_model.config_file.status),
            _tr(view_model.config_file.note),
            view_model.config_file.path,
            view_model.config_file.exists,
        )
        self.entry_count_card.set_value(view_model.entry_count.value, _tr(view_model.entry_count.note))
        self.file_count_card.set_value(view_model.file_count.value, _tr(view_model.file_count.note))
        self.status_label.setText(_tr(view_model.status))
        self.parsed_rows.set_rows([(_tr(label), _tr(value), _tr(note)) for label, value, note in view_model.parsed_rows])

    def _sync_display_backend_combo(self, backend: str) -> None:
        index = self.display_backend_combo.findData(backend)
        if index < 0:
            index = 0
        self.display_backend_combo.blockSignals(True)
        self.display_backend_combo.setCurrentIndex(index)
        self.display_backend_combo.blockSignals(False)

    def _retranslate_combo_items(self) -> None:
        for index, (_, label) in enumerate(DISPLAY_BACKEND_OPTIONS):
            self.display_backend_combo.setItemText(index, _tr(label))
        for index, (_, label) in enumerate(LANGUAGE_OPTIONS):
            self.language_combo.setItemText(index, label)
        for index, (_, label) in enumerate(THEME_MODE_OPTIONS):
            self.theme_mode_combo.setItemText(index, _tr(label))

    def _handle_display_backend_changed(self, index: int) -> None:
        _ = index
        backend = self.display_backend_combo.currentData()
        if not isinstance(backend, str):
            return
        self._apply_settings_result(self._settings_coordinator.set_display_backend(backend))

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
        self._apply_settings_result(self._settings_coordinator.set_language(language_code), show_success=False)

    def _sync_theme_mode_combo(self, theme_mode: str) -> None:
        index = self.theme_mode_combo.findData(theme_mode)
        if index < 0:
            index = 0
        self.theme_mode_combo.blockSignals(True)
        self.theme_mode_combo.setCurrentIndex(index)
        self.theme_mode_combo.blockSignals(False)

    def _handle_theme_mode_changed(self, index: int) -> None:
        _ = index
        theme_mode = self.theme_mode_combo.currentData()
        if not isinstance(theme_mode, str):
            return
        self._apply_settings_result(self._settings_coordinator.set_theme_mode(theme_mode), show_success=False)

    def _show_mode(self, mode: str) -> None:
        self._mode = mode
        showing_data = mode == "data"
        self.parsed_container.setVisible(showing_data)
        self.content_output.setVisible(not showing_data)
        self.content_mode_switch.setCurrentItem(mode)

    def _create_switch_row(self, text: str, config_key: ConfigKey, parent: QWidget) -> SwitchSettingRow:
        row = SwitchSettingRow(
            text,
            lambda checked, key=config_key: self._toggle_switch_value(key, checked),
            parent,
        )
        self._switch_rows[config_key] = row
        return row

    def _create_auto_query_row(
        self,
        binding: AutoQueryBinding,
        parent: QWidget,
    ) -> AutoQuerySettingRow:
        return AutoQuerySettingRow(
            _tr(binding.title),
            binding.placeholder,
            lambda checked, key=binding.auto_key: self._toggle_switch_value(key, checked),
            lambda checked, key=binding.poll_key: self._toggle_switch_value(key, checked),
            lambda raw, key=binding.interval_key: self._save_input_value(key, raw),
            parent,
        )

    def _create_input_row(self, text: str, config_key: ConfigKey, placeholder: str, parent: QWidget) -> InputSettingRow:
        row = InputSettingRow(
            text,
            placeholder,
            lambda raw, key=config_key: self._save_input_value(key, raw),
            parent,
        )
        self._input_rows[config_key] = row
        return row

    def _retranslate_setting_rows(self) -> None:
        for binding in ALERT_SWITCH_BINDINGS:
            self._switch_rows[binding.key].retranslate_ui(_tr(binding.label))
        for binding in ALERT_INPUT_BINDINGS:
            self._input_rows[binding.key].retranslate_ui(_tr(binding.label), binding.placeholder)

    def _toggle_switch_value(self, config_key: ConfigKey, checked: bool) -> None:
        result = self._settings_coordinator.set_switch(config_key, checked)
        if not result.ok:
            self._show_error(result.message)
            return
        if config_key == ConfigKey.SINGLE_INSTANCE_ENABLED:
            self._sync_runtime_option_state(checked)
        self._apply_settings_result(result, show_success=False)

    def _sync_runtime_option_state(self, single_instance_enabled: bool) -> None:
        self.background_resident_row.setEnabled(single_instance_enabled)
        self.background_resident_row.setToolTip("" if single_instance_enabled else _tr("需先启用单实例模式"))

    def _save_input_value(self, config_key: ConfigKey, raw_value: str) -> None:
        self._apply_settings_result(self._settings_coordinator.set_input(config_key, raw_value))

    def _show_error(self, message: str) -> None:
        show_error_bar(self.window(), _tr("配置无效"), message)

    def _delete_config_file(self) -> None:
        if not self._confirm(_tr("删除配置文件"), _tr("确认删除 config.json 吗？")):
            return
        self._apply_settings_result(self._settings_coordinator.delete_config_file())

    def _delete_config_dir(self) -> None:
        if not self._confirm(_tr("删除缓存目录"), _tr("确认删除整个 ~/.config/open-router-key-viewer 目录吗？")):
            return
        self._apply_settings_result(self._settings_coordinator.delete_config_dir())

    def _apply_settings_result(self, result: SettingsActionResult, *, show_success: bool = True) -> None:
        if not result.ok:
            self._show_error(_tr(result.message))
            return
        if result.effect is None:
            return
        self.refresh_view()
        if result.effect == "runtime":
            self.on_runtime_settings_changed()
        elif result.effect == "global":
            self.on_global_config_changed()
        elif result.effect == "language" and isinstance(result.value, str):
            QTimer.singleShot(0, lambda value=result.value: self.on_language_changed(value))
        elif result.effect == "theme" and isinstance(result.value, str):
            QTimer.singleShot(0, lambda value=result.value: self.on_theme_changed(value))
        if show_success:
            self._show_success(result.success_title, result.success_message)

    def _show_success(self, title: str, message: str) -> None:
        InfoBar.success(
            title=_tr(title),
            content=_tr(message),
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
