from __future__ import annotations

import io
from contextlib import redirect_stdout

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import (
        BodyLabel,
        ElevatedCardWidget,
        SingleDirectionScrollArea,
        StrongBodyLabel,
        TitleLabel,
    )

from open_router_key_viewer.i18n import tr
from open_router_key_viewer.core.about_coordinator import AboutCoordinator
from open_router_key_viewer.state.about_view_model import AboutViewModel
from open_router_key_viewer.state.app_metadata import APP_DISPLAY_NAME
from open_router_key_viewer.ui.controllers.install_controller import AboutInstallController
from open_router_key_viewer.ui.controllers.update_controller import AboutUpdateController
from open_router_key_viewer.ui.widgets import DetailCard, InstallCard, UpdateCard

_tr = tr


class AboutPage(QWidget):
    def __init__(self, about_coordinator: AboutCoordinator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("about-page")
        self._about_coordinator = about_coordinator
        self._build_ui()
        self.install_controller = AboutInstallController(self, self.install_card, self._refresh_install_info)
        parent_quit = getattr(parent, "quit_application", None)
        self.update_controller = AboutUpdateController(
            self,
            self.update_card,
            quit_application=parent_quit if callable(parent_quit) else None,
        )
        self._refresh_about_view()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll_area = SingleDirectionScrollArea(self, Qt.Vertical)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll_area)

        content = QWidget(scroll_area)
        scroll_area.setWidget(content)
        scroll_area.enableTransparentBackground()
        content.setStyleSheet("background: transparent;")

        root = QVBoxLayout(content)
        root.setContentsMargins(36, 28, 36, 36)
        root.setSpacing(18)

        self.title_label = TitleLabel(_tr("关于"), self)
        root.addWidget(self.title_label)

        hero_card = ElevatedCardWidget(self)
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(24, 22, 24, 22)
        hero_layout.setSpacing(8)
        self.app_name_label = StrongBodyLabel(APP_DISPLAY_NAME, hero_card)
        hero_layout.addWidget(self.app_name_label)
        self.version_label = TitleLabel("", hero_card)
        hero_layout.addWidget(self.version_label)

        self.description_label = BodyLabel(
            _tr("用于查询 OpenRouter API Key 配额和 OpenRouter Management Key 账户余额。"),
            hero_card,
        )
        self.description_label.setWordWrap(True)
        hero_layout.addWidget(self.description_label)
        root.addWidget(hero_card)

        self.update_card = UpdateCard(self)
        root.addWidget(self.update_card)

        self.install_card = InstallCard(self)
        root.addWidget(self.install_card)

        self.details_card = DetailCard(_tr("版本信息"), self)
        root.addWidget(self.details_card)

        self.notes_card = DetailCard(_tr("项目"), self)
        root.addWidget(self.notes_card)

    def retranslate_ui(self) -> None:
        self._refresh_install_info()
        self.install_controller.retranslate_ui()
        self.update_controller.retranslate_ui()
        self._refresh_about_view()

    def check_updates_silently(self) -> None:
        self.update_controller.check_updates_silently()

    def _refresh_install_info(self) -> None:
        self.install_controller.refresh_install_info()
        self._refresh_about_view()

    def _refresh_about_view(self) -> None:
        view_model = self._build_about_view_model()
        self._apply_about_view_model(view_model)

    def _build_about_view_model(self) -> AboutViewModel:
        build_info = getattr(self, "update_controller", None)
        install_controller = getattr(self, "install_controller", None)
        binary_update_supported = build_info.binary_update_supported if build_info is not None else False
        if build_info is not None:
            self._about_coordinator.build_info = build_info.build_info
        return self._about_coordinator.build_view_model(
            install_info=install_controller.install_info,
            binary_update_supported=binary_update_supported,
        )

    def _apply_about_view_model(self, view_model: AboutViewModel) -> None:
        self.title_label.setText(_tr(view_model.title))
        self.app_name_label.setText(view_model.app_name)
        self.version_label.setText(view_model.version)
        self.description_label.setText(_tr(view_model.description))
        self.details_card.set_title(_tr(view_model.details_title))
        self.details_card.set_rows(
            [(_tr(row.label), _tr(row.value), _tr(row.note), row.url) for row in view_model.detail_rows]
        )
        self.notes_card.set_title(_tr(view_model.notes_title))
        self.notes_card.set_rows(
            [(_tr(row.label), _tr(row.value), _tr(row.note), row.url) for row in view_model.note_rows]
        )

    def stop_workers(self) -> None:
        self.update_controller.stop()
