from __future__ import annotations

import io
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget

with redirect_stdout(io.StringIO()):
    from qfluentwidgets import InfoBar, InfoBarPosition, MessageBox

from open_router_key_viewer.i18n import tr
from open_router_key_viewer.services.installer import AppInstallError, AppInstaller
from open_router_key_viewer.ui.runtime import APP_DISPLAY_NAME, show_error_bar
from open_router_key_viewer.ui.widgets import InstallCard

_tr = tr


class AboutInstallController:
    """Coordinate in-app user-level installation for packaged binaries."""

    def __init__(self, host: QWidget, install_card: InstallCard, on_install_state_changed: Callable[[], None]) -> None:
        self.host = host
        self.install_card = install_card
        self._on_install_state_changed = on_install_state_changed
        self._installer = AppInstaller(Path(sys.executable), is_binary_runtime=bool(getattr(sys, "frozen", False)))
        self._install_info = self._installer.inspect()
        self._refresh_state: Callable[[], None] = lambda: None

        self.install_card.install_button.clicked.connect(self.install_or_upgrade)
        self.install_card.open_button.clicked.connect(self.open_install_directory)
        self.install_card.remove_button.clicked.connect(self.remove_installation)
        self.show_state()

    def retranslate_ui(self) -> None:
        self.install_card.retranslate_ui()
        self._refresh_state()

    def show_state(self) -> None:
        if not self._install_info.is_binary_runtime:
            self.install_card.set_state(
                _tr("当前不可安装"),
                _tr("当前是源码运行模式。安装功能仅在打包后的二进制运行时可用。"),
                _tr("请先运行打包后的 open-router-key-viewer 二进制。"),
                install_enabled=False,
            )
            self._refresh_state = self.show_state
            return

        if self._install_info.is_installed and self._install_info.install_root is not None:
            self.install_card.set_state(
                _tr("已安装"),
                (
                    _tr("当前正在运行已安装版本。")
                    if self._install_info.current_is_installed
                    else _tr("检测到已安装副本，可重新安装覆盖或直接移除。")
                ),
                _tr("固定安装目录：{root}").format(root=str(self._install_info.install_root)),
                can_open_directory=True,
                can_remove=True,
                install_button_text=_tr("重新安装到固定位置"),
            )
        else:
            self.install_card.set_state(
                _tr("未安装"),
                _tr("可将当前二进制安装到固定用户目录，并自动创建启动入口。"),
                _tr("固定安装目录：{root}").format(root=str(self._installer.install_root)),
                can_open_directory=False,
                can_remove=False,
                install_button_text=_tr("安装到固定位置"),
            )
        self._refresh_state = self.show_state

    def install_or_upgrade(self) -> None:
        box = MessageBox(
            _tr("安装到固定位置"),
            _tr("将当前二进制安装到固定目录：{root}\n同时会写入 ~/.local/bin 启动入口、桌面启动器和图标。是否继续？").format(
                root=str(self._installer.install_root)
            ),
            self.host.window(),
        )
        box.yesButton.setText(_tr("继续"))
        box.cancelButton.setText(_tr("取消"))
        if not box.exec():
            return
        try:
            self._install_info = self._installer.install(app_display_name=APP_DISPLAY_NAME)
        except AppInstallError as exc:
            show_error_bar(self.host, _tr("安装失败"), str(exc))
            return

        InfoBar.success(
            title=_tr("安装完成"),
            content=_tr("已安装到 {root}").format(root=str(self._installer.install_root)),
            parent=self.host,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
        )
        self.show_state()
        self._on_install_state_changed()

    def remove_installation(self) -> None:
        if not self._install_info.is_installed:
            return
        box = MessageBox(
            _tr("移除安装"),
            _tr("将移除固定安装目录、启动入口、桌面启动器和图标。当前配置文件不会删除。是否继续？"),
            self.host.window(),
        )
        box.yesButton.setText(_tr("确认移除"))
        box.cancelButton.setText(_tr("取消"))
        if not box.exec():
            return
        try:
            self._installer.uninstall()
        except (AppInstallError, OSError) as exc:
            show_error_bar(self.host, _tr("移除失败"), str(exc))
            return

        self._install_info = self._installer.inspect()
        InfoBar.success(
            title=_tr("已移除"),
            content=_tr("已移除本地安装副本"),
            parent=self.host,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
        )
        self.show_state()
        self._on_install_state_changed()

    def open_install_directory(self) -> None:
        if self._install_info.install_root is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._install_info.install_root)))
