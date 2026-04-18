from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

from PySide6.QtCore import Qt, qVersion
from PySide6.QtWidgets import QApplication, QFrame, QVBoxLayout, QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import (
        BodyLabel,
        ElevatedCardWidget,
        SingleDirectionScrollArea,
        StrongBodyLabel,
        TitleLabel,
    )

from open_router_key_viewer import __version__
from open_router_key_viewer.i18n import tr
from open_router_key_viewer.services.build_info import get_build_info
from open_router_key_viewer.services.installer import AppInstaller
from open_router_key_viewer.ui.controllers.install_controller import AboutInstallController
from open_router_key_viewer.ui.controllers.update_controller import AboutUpdateController
from open_router_key_viewer.ui.runtime import (
    APP_AUTHOR,
    APP_AUTHOR_URL,
    APP_DATA_SOURCE_URL,
    APP_DISPLAY_NAME,
    APP_LICENSE_NAME,
    APP_REPOSITORY_URL,
)
from open_router_key_viewer.ui.widgets import DetailCard, InstallCard, UpdateCard

_tr = tr


class AboutPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("about-page")
        self._build_info = get_build_info()
        self._binary_update_supported = bool(getattr(sys, "frozen", False))
        self._install_info = AppInstaller(
            Path(sys.executable),
            is_binary_runtime=bool(getattr(sys, "frozen", False)),
        ).inspect()
        self._build_ui()
        self.install_controller = AboutInstallController(self, self.install_card, self._refresh_install_info)
        self.update_controller = AboutUpdateController(self, self.update_card)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll_area = SingleDirectionScrollArea(self, Qt.Vertical)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.enableTransparentBackground()
        outer.addWidget(scroll_area)

        content = QWidget(scroll_area)
        scroll_area.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(36, 28, 36, 36)
        root.setSpacing(18)

        self.title_label = TitleLabel(_tr("关于"), self)
        root.addWidget(self.title_label)

        hero_card = ElevatedCardWidget(self)
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(24, 22, 24, 22)
        hero_layout.setSpacing(8)
        hero_layout.addWidget(StrongBodyLabel(APP_DISPLAY_NAME, hero_card))
        hero_layout.addWidget(TitleLabel(f"v{__version__}", hero_card))

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
        self._refresh_details_card()
        root.addWidget(self.details_card)

        self.notes_card = DetailCard(_tr("项目"), self)
        self.notes_card.set_rows(
            [
                (_tr("仓库地址"), "GitHub Repository", "", APP_REPOSITORY_URL),
                (_tr("数据来源"), "OpenRouter API Reference", "", APP_DATA_SOURCE_URL),
            ]
        )
        root.addWidget(self.notes_card)

    def retranslate_ui(self) -> None:
        self.title_label.setText(_tr("关于"))
        self.description_label.setText(_tr("用于查询 OpenRouter API Key 配额和 OpenRouter Management Key 账户余额。"))
        self._refresh_install_info()
        self.install_controller.retranslate_ui()
        self.update_controller.retranslate_ui()
        self._refresh_details_card()
        self.notes_card.set_title(_tr("项目"))
        self.notes_card.set_rows(
            [
                (_tr("仓库地址"), "GitHub Repository", "", APP_REPOSITORY_URL),
                (_tr("数据来源"), "OpenRouter API Reference", "", APP_DATA_SOURCE_URL),
            ]
        )

    def check_updates_silently(self) -> None:
        self.update_controller.check_updates_silently()

    def _refresh_install_info(self) -> None:
        self._install_info = AppInstaller(
            Path(sys.executable),
            is_binary_runtime=bool(getattr(sys, "frozen", False)),
        ).inspect()
        self._refresh_details_card()

    def _refresh_details_card(self) -> None:
        build_info = getattr(self, "update_controller", None)
        active_build = build_info.build_info if build_info is not None else self._build_info
        binary_update_supported = (
            build_info.binary_update_supported if build_info is not None else self._binary_update_supported
        )
        self.details_card.set_title(_tr("版本信息"))
        self.details_card.set_rows(
            [
                (_tr("应用名称"), APP_DISPLAY_NAME, ""),
                (
                    _tr("版本"),
                    f"v{__version__}",
                    f"{self._short_commit(active_build.commit_sha)} · "
                    f"{'dirty' if active_build.dirty else 'clean'}",
                ),
                (_tr("运行方式"), _tr("二进制发布") if binary_update_supported else _tr("源码运行"), ""),
                (
                    _tr("安装状态"),
                    _tr("已安装") if self._install_info.is_installed else _tr("便携运行"),
                    str(self._install_info.install_root) if self._install_info.install_root is not None else "",
                ),
                (_tr("作者"), APP_AUTHOR, "", APP_AUTHOR_URL),
                ("Python", sys.version.split()[0], ""),
                ("Qt", qVersion(), ""),
                (_tr("许可证"), APP_LICENSE_NAME, ""),
            ]
        )

    def _short_commit(self, commit_sha: str) -> str:
        stripped = commit_sha.strip()
        if not stripped or stripped == "unknown":
            return "unknown"
        return stripped[:8]

    def stop_workers(self) -> None:
        self.update_controller.stop()
