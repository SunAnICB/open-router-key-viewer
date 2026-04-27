from __future__ import annotations

import sys

from PySide6.QtCore import qVersion

from open_router_key_viewer import __version__
from open_router_key_viewer.services.build_info import BuildInfo
from open_router_key_viewer.services.installer import InstallInfo
from open_router_key_viewer.state.about_view_model import AboutViewModel, DetailRowViewModel
from open_router_key_viewer.state.app_metadata import (
    APP_AUTHOR,
    APP_AUTHOR_URL,
    APP_DATA_SOURCE_URL,
    APP_DISPLAY_NAME,
    APP_LICENSE_NAME,
    APP_REPOSITORY_URL,
)


def build_about_view_model(
    *,
    build_info: BuildInfo,
    install_info: InstallInfo,
    binary_update_supported: bool,
) -> AboutViewModel:
    return AboutViewModel(
        title="关于",
        app_name=APP_DISPLAY_NAME,
        version=f"v{__version__}",
        description="用于查询 OpenRouter API Key 配额和 OpenRouter Management Key 账户余额。",
        details_title="版本信息",
        detail_rows=[
            DetailRowViewModel("应用名称", APP_DISPLAY_NAME),
            DetailRowViewModel(
                "版本",
                f"v{__version__}",
                f"{_short_commit(build_info.commit_sha)} · {'dirty' if build_info.dirty else 'clean'}",
            ),
            DetailRowViewModel("运行方式", "二进制发布" if binary_update_supported else "源码运行"),
            DetailRowViewModel(
                "安装状态",
                "已安装" if install_info.is_installed else "便携运行",
                str(install_info.install_root) if install_info.install_root is not None else "",
            ),
            DetailRowViewModel("作者", APP_AUTHOR, "", APP_AUTHOR_URL),
            DetailRowViewModel("Python", sys.version.split()[0]),
            DetailRowViewModel("Qt", qVersion()),
            DetailRowViewModel("许可证", APP_LICENSE_NAME),
        ],
        notes_title="项目",
        note_rows=[
            DetailRowViewModel("仓库地址", "GitHub Repository", "", APP_REPOSITORY_URL),
            DetailRowViewModel("数据来源", "OpenRouter API Reference", "", APP_DATA_SOURCE_URL),
        ],
    )


def _short_commit(commit_sha: str) -> str:
    stripped = commit_sha.strip()
    if not stripped or stripped == "unknown":
        return "unknown"
    return stripped[:8]
