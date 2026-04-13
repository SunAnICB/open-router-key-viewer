from __future__ import annotations

import io
from contextlib import redirect_stdout

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import (
        CaptionLabel,
        ElevatedCardWidget,
        FluentIcon,
        PasswordLineEdit,
        PrimaryPushButton,
        PushButton,
        SegmentedWidget,
        StrongBodyLabel,
        TextEdit,
    )

from open_router_key_viewer.i18n import tr
from open_router_key_viewer.ui.widgets import DetailCard, ResultCard, StatusBadge

_tr = tr


class SecretInputCard(ElevatedCardWidget):
    def __init__(self, input_label: str, placeholder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.input_label_widget = StrongBodyLabel(input_label, self)
        self.input_label_widget.setMinimumWidth(210)
        row.addWidget(self.input_label_widget)

        self.secret_input = PasswordLineEdit(self)
        self.secret_input.setPlaceholderText(placeholder)
        row.addWidget(self.secret_input, 1)

        self.paste_button = PushButton(_tr("粘贴"), self)
        self.paste_button.setIcon(FluentIcon.PASTE)
        row.addWidget(self.paste_button)

        self.copy_button = PushButton(_tr("复制"), self)
        self.copy_button.setIcon(FluentIcon.COPY)
        row.addWidget(self.copy_button)

        self.save_button = PushButton(_tr("保存缓存"), self)
        self.save_button.setIcon(FluentIcon.SAVE)
        row.addWidget(self.save_button)

        self.clear_saved_button = PushButton(_tr("删除缓存"), self)
        self.clear_saved_button.setIcon(FluentIcon.DELETE)
        row.addWidget(self.clear_saved_button)
        layout.addLayout(row)

    def retranslate_ui(self, input_label: str, placeholder: str) -> None:
        self.input_label_widget.setText(input_label)
        self.secret_input.setPlaceholderText(placeholder)
        self.paste_button.setText(_tr("粘贴"))
        self.copy_button.setText(_tr("复制"))
        self.save_button.setText(_tr("保存缓存"))
        self.clear_saved_button.setText(_tr("删除缓存"))

    def set_busy(self, busy: bool) -> None:
        self.secret_input.setEnabled(not busy)
        self.paste_button.setEnabled(not busy)
        self.copy_button.setEnabled(not busy)
        self.save_button.setEnabled(not busy)
        self.clear_saved_button.setEnabled(not busy)


class QueryResultCard(ElevatedCardWidget):
    def __init__(
        self,
        button_text: str,
        button_icon: FluentIcon,
        on_show_summary,
        on_show_raw,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(12)

        self.query_button = PrimaryPushButton(button_text, self)
        self.query_button.setIcon(button_icon)
        header.addWidget(self.query_button)

        self.status_badge = StatusBadge(self)
        header.addWidget(self.status_badge)
        header.addStretch(1)

        self.time_label = CaptionLabel(_tr("最近成功: -"), self)
        header.addWidget(self.time_label)

        self.result_mode_switch = SegmentedWidget(self)
        self.result_mode_switch.addItem("summary", _tr("结果卡片"), on_show_summary)
        self.result_mode_switch.addItem("raw", _tr("原始请求"), on_show_raw)
        header.addWidget(self.result_mode_switch)
        layout.addLayout(header)

        self.summary_container = QWidget(self)
        summary_layout = QVBoxLayout(self.summary_container)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(12)
        self.hero_card = ResultCard(self.summary_container)
        self.detail_card = DetailCard(_tr("详细信息"), self.summary_container)
        summary_layout.addWidget(self.hero_card)
        summary_layout.addWidget(self.detail_card)
        layout.addWidget(self.summary_container)

        self.result_output = TextEdit(self)
        self.result_output.setReadOnly(True)
        self.result_output.setMinimumHeight(320)
        mono = QFont("JetBrains Mono")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.result_output.setFont(mono)
        layout.addWidget(self.result_output)

    def retranslate_ui(self, button_text: str) -> None:
        self.query_button.setText(button_text)
        self.detail_card.set_title(_tr("详细信息"))
        self.result_mode_switch.setItemText("summary", _tr("结果卡片"))
        self.result_mode_switch.setItemText("raw", _tr("原始请求"))
        self.status_badge.retranslate_ui()

    def set_busy(self, busy: bool) -> None:
        self.query_button.setEnabled(not busy)

    def show_mode(self, mode: str) -> None:
        showing_summary = mode == "summary"
        self.summary_container.setVisible(showing_summary)
        self.result_output.setVisible(not showing_summary)
        self.result_mode_switch.setCurrentItem(mode)
