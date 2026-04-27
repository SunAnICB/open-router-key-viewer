from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProgressStep:
    id: str
    percent: int
    message: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ProgressState:
    percent: int
    message: str
    detail: str = ""


STARTUP_STEPS: tuple[ProgressStep, ...] = (
    ProgressStep("load_config", 5, "正在启动应用...", "加载本地配置"),
    ProgressStep("check_single_instance", 15, "正在检查运行模式...", "检查单实例设置"),
    ProgressStep("apply_ui_settings", 25, "正在应用界面设置...", "加载语言和主题"),
    ProgressStep("create_context", 30, "正在准备运行环境...", "初始化配置、状态和服务"),
    ProgressStep("create_window", 34, "正在初始化主窗口...", "准备主界面"),
    ProgressStep("connect_single_instance", 98, "正在完成启动...", "连接单实例唤起能力"),
    ProgressStep("ready", 100, "初始化完成", "准备显示主窗口"),
)

MAIN_WINDOW_STEPS: tuple[ProgressStep, ...] = (
    ProgressStep("init_state", 35, "正在初始化主窗口...", "加载运行状态"),
    ProgressStep("key_page", 45, "正在初始化查询页面...", "加载 Key 配额页面"),
    ProgressStep("credits_page", 55, "正在初始化查询页面...", "加载账户余额页面"),
    ProgressStep("settings_page", 68, "正在初始化配置页面...", "读取本地配置"),
    ProgressStep("about_page", 78, "正在初始化关于页面...", "加载版本与更新信息"),
    ProgressStep("shell_controller", 84, "正在初始化窗口能力...", "准备托盘、悬浮窗和顶栏指示器"),
    ProgressStep("kernel", 88, "正在初始化运行内核...", "准备定时任务与启动任务"),
    ProgressStep("capabilities", 92, "正在同步运行能力...", "刷新配置页状态"),
    ProgressStep("navigation", 94, "正在初始化导航...", "注册页面入口"),
    ProgressStep("window_ready", 96, "正在准备窗口...", "应用窗口大小和系统指示器"),
)

LANGUAGE_SWITCH_STEPS: tuple[ProgressStep, ...] = (
    ProgressStep("install_language", 15, "正在切换语言...", "加载语言资源"),
    ProgressStep("navigation", 30, "正在切换语言...", "刷新导航文案"),
    ProgressStep("key_page", 45, "正在切换语言...", "刷新 Key 配额页面"),
    ProgressStep("credits_page", 58, "正在切换语言...", "刷新账户余额页面"),
    ProgressStep("settings_page", 72, "正在切换语言...", "刷新配置页面"),
    ProgressStep("about_page", 86, "正在切换语言...", "刷新关于页面"),
    ProgressStep("shell", 96, "正在切换语言...", "刷新窗口附属组件"),
    ProgressStep("done", 100, "语言切换完成", "准备刷新界面"),
)

THEME_SWITCH_STEPS: tuple[ProgressStep, ...] = (
    ProgressStep("apply_theme", 18, "正在切换主题...", "应用主题设置"),
    ProgressStep("key_page", 38, "正在切换主题...", "刷新 Key 配额页面"),
    ProgressStep("credits_page", 52, "正在切换主题...", "刷新账户余额页面"),
    ProgressStep("settings_page", 70, "正在切换主题...", "刷新配置页面"),
    ProgressStep("about_page", 84, "正在切换主题...", "刷新关于页面"),
    ProgressStep("shell", 96, "正在切换主题...", "刷新窗口附属组件"),
    ProgressStep("done", 100, "主题切换完成", "准备刷新界面"),
)


def step_by_id(steps: tuple[ProgressStep, ...], step_id: str) -> ProgressStep:
    for step in steps:
        if step.id == step_id:
            return step
    raise KeyError(f"Unknown progress step: {step_id}")
