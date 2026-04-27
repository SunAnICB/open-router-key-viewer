from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from open_router_key_viewer.services.installer import InstallInfo


@dataclass(frozen=True, slots=True)
class TextSpec:
    source: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UpdateCardViewModel:
    title: TextSpec
    note: TextSpec
    meta: TextSpec
    can_open_release: bool = False
    can_replace: bool = False


@dataclass(frozen=True, slots=True)
class InstallCardViewModel:
    title: TextSpec
    note: TextSpec
    meta: TextSpec
    install_enabled: bool = True
    can_open_directory: bool = False
    can_remove: bool = False
    install_button_text: TextSpec | None = None


def text(source: str, **args: Any) -> TextSpec:
    return TextSpec(source, args)


def build_update_intro_state(binary_update_supported: bool) -> UpdateCardViewModel:
    if binary_update_supported:
        return UpdateCardViewModel(
            text("可检查二进制更新"),
            text("当前为打包后的二进制运行。点击“检查更新”后，将对比 GitHub Release 中的最新版本。"),
            text("支持打开 Release 页面，也支持下载并在应用退出后替换当前二进制文件。"),
            can_open_release=True,
        )
    return UpdateCardViewModel(
        text("可检查更新"),
        text("当前是源码运行模式。你仍然可以查看最新 Release 和版本信息。"),
        text("源码运行不支持下载后直接替换当前二进制文件。"),
        can_open_release=True,
    )


def build_update_checking_state() -> UpdateCardViewModel:
    return UpdateCardViewModel(
        text("正在检查更新"),
        text("正在查询 GitHub Release 中的最新已发布版本。"),
        text("仅检查正式 Release，不包含 draft 或 prerelease。"),
    )


def build_update_available_state(
    *,
    current_version: str,
    release_version: str,
    asset_note: TextSpec,
    published_at: str,
    replace_note: str,
    can_replace: bool,
) -> UpdateCardViewModel:
    return UpdateCardViewModel(
        text("发现新版本 v{version}", version=release_version),
        text(
            "当前版本 v{current_version}，最新版本 v{release_version}。",
            current_version=current_version,
            release_version=release_version,
        ),
        text(
            "{asset_note}  发布时间：{published_at}{replace_note}",
            asset_note=asset_note,
            published_at=published_at,
            replace_note=replace_note,
        ),
        can_open_release=True,
        can_replace=can_replace,
    )


def build_dev_build_state(
    *,
    current_version: str,
    release_version: str,
    tag_name: str,
    published_at: str,
    commit_note: TextSpec | None,
) -> UpdateCardViewModel:
    return UpdateCardViewModel(
        text("当前是非 Release 的开发版本"),
        text(
            "当前构建与最新 Release 不完全一致。版本：v{current_version}，最新 Release：v{release_version}。",
            current_version=current_version,
            release_version=release_version,
        ),
        text(
            "最新公开标签：{tag_name}  发布时间：{published_at}{commit_note}",
            tag_name=tag_name,
            published_at=published_at,
            commit_note=commit_note or text(""),
        ),
        can_open_release=True,
        can_replace=False,
    )


def build_latest_state(*, current_version: str, tag_name: str, published_at: str) -> UpdateCardViewModel:
    return UpdateCardViewModel(
        text("当前已是最新版本"),
        text("当前版本 v{current_version} 已与最新 Release 保持一致。", current_version=current_version),
        text("最新标签：{tag_name}  发布时间：{published_at}", tag_name=tag_name, published_at=published_at),
        can_open_release=True,
        can_replace=False,
    )


def build_update_failure_state(message: str) -> UpdateCardViewModel:
    return UpdateCardViewModel(
        text("检查更新失败"),
        text(message),
        text("请稍后重试，或手动打开 GitHub Release 页面查看。"),
        can_open_release=True,
        can_replace=False,
    )


def build_downloading_state(*, name: str, meta: TextSpec, note: TextSpec | None = None) -> UpdateCardViewModel:
    return UpdateCardViewModel(
        text("正在下载更新"),
        note or text("正在下载 {name}。", name=name),
        meta,
        can_open_release=False,
        can_replace=False,
    )


def build_downloaded_state(*, filename: str) -> UpdateCardViewModel:
    return UpdateCardViewModel(
        text("更新已下载完成"),
        text("正在退出当前程序并应用新版本。"),
        text("目标文件：{filename}  程序将自动重新启动。", filename=filename),
        can_open_release=False,
        can_replace=False,
    )


def build_download_failed_state(
    message: str,
    *,
    binary_update_supported: bool,
    has_asset: bool,
) -> UpdateCardViewModel:
    return UpdateCardViewModel(
        text("下载更新失败"),
        text(message),
        text("你仍然可以打开 Release 页面手动下载。"),
        can_open_release=True,
        can_replace=binary_update_supported and has_asset,
    )


def build_asset_note(name: str | None) -> TextSpec:
    if name:
        return text("下载文件：{name}", name=name)
    return text("该 Release 未找到匹配的二进制资产，将打开发布页面。")


def build_commit_note(current_commit: str, release_commit: str) -> TextSpec:
    return text(
        "  当前 Commit：{current_commit}  Release Commit：{release_commit}",
        current_commit=current_commit,
        release_commit=release_commit,
    )


def build_install_state(install_info: InstallInfo, install_root: Path) -> InstallCardViewModel:
    if not install_info.is_binary_runtime:
        return InstallCardViewModel(
            text("当前不可安装"),
            text("当前是源码运行模式。安装功能仅在打包后的二进制运行时可用。"),
            text("请先运行打包后的 open-router-key-viewer 二进制。"),
            install_enabled=False,
        )

    if install_info.is_installed and install_info.install_root is not None:
        note = (
            text("当前正在运行已安装版本。")
            if install_info.current_is_installed
            else text("检测到已安装副本，可重新安装覆盖或直接移除。")
        )
        return InstallCardViewModel(
            text("已安装"),
            note,
            text("固定安装目录：{root}", root=str(install_info.install_root)),
            can_open_directory=True,
            can_remove=True,
            install_button_text=text("重新安装到固定位置"),
        )

    return InstallCardViewModel(
        text("未安装"),
        text("可将当前二进制安装到固定用户目录，并自动创建启动入口。"),
        text("固定安装目录：{root}", root=str(install_root)),
        can_open_directory=False,
        can_remove=False,
        install_button_text=text("安装到固定位置"),
    )
