from __future__ import annotations

from dataclasses import dataclass

import pytest

import open_router_key_viewer.core.update_coordinator as update_coordinator_module
import open_router_key_viewer.ui.controllers.update_controller as update_controller_module
from open_router_key_viewer.services.update_checker import ReleaseAsset, ReleaseInfo, UpdateCheckResult
from open_router_key_viewer.ui.controllers.update_controller import AboutUpdateController


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def disconnect(self) -> None:
        self._callbacks.clear()


class _FakeButton:
    def __init__(self) -> None:
        self.clicked = _FakeSignal()
        self.enabled = True

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        self.enabled = enabled


class _FakeUpdateCard:
    def __init__(self) -> None:
        self.check_button = _FakeButton()
        self.release_button = _FakeButton()
        self.replace_button = _FakeButton()
        self.states: list[dict[str, object]] = []
        self.retranslated = 0

    def set_state(self, title: str, note: str, meta: str = "", *, can_open_release: bool = False, can_replace: bool = False) -> None:
        self.states.append(
            {
                "title": title,
                "note": note,
                "meta": meta,
                "can_open_release": can_open_release,
                "can_replace": can_replace,
            }
        )

    def retranslate_ui(self) -> None:
        self.retranslated += 1


class _FakeHost:
    def __init__(self) -> None:
        self.quit_calls = 0

    def window(self):
        return self

    def quit_application(self) -> None:
        self.quit_calls += 1


@dataclass
class _FakeBuildInfo:
    commit_sha: str = "abcdef1234567890"
    dirty: bool = False


class _FakeReleaseChecker:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs


@dataclass
class _FakeInstallInfo:
    is_binary_runtime: bool = True
    is_installed: bool = False
    current_is_installed: bool = False
    install_root: str | None = None
    binary_path: str | None = None
    launcher_path: str = "/tmp/open-router-key-viewer-launcher"
    desktop_path: str = "/tmp/open-router-key-viewer.desktop"


class _FakeInstaller:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    def inspect(self) -> _FakeInstallInfo:
        return _FakeInstallInfo()


class _FakeUpdateWorker:
    def __init__(self, checker, parent) -> None:
        self.checker = checker
        self.parent = parent
        self.succeeded = _FakeSignal()
        self.failed = _FakeSignal()
        self.finished = _FakeSignal()
        self.started = False
        self.running = False

    def isRunning(self) -> bool:  # noqa: N802
        return self.running

    def start(self) -> None:
        self.started = True
        self.running = True


class _FakeBinaryUpdater:
    def __init__(self, *args, **kwargs) -> None:
        self.cleaned = False
        self.args = args
        self.kwargs = kwargs

    def cleanup_stale_updates(self) -> None:
        self.cleaned = True

    def can_replace_current_binary(self) -> tuple[bool, str]:
        return True, ""


def _make_controller(
    monkeypatch: pytest.MonkeyPatch, *, frozen: bool = False
) -> tuple[AboutUpdateController, _FakeUpdateCard, _FakeHost]:
    monkeypatch.setattr(update_controller_module, "get_build_info", lambda: _FakeBuildInfo())
    monkeypatch.setattr(update_controller_module, "GitHubReleaseChecker", _FakeReleaseChecker)
    monkeypatch.setattr(update_controller_module, "UpdateCheckWorker", _FakeUpdateWorker)
    monkeypatch.setattr(update_controller_module, "BinaryUpdater", _FakeBinaryUpdater)
    monkeypatch.setattr(update_controller_module, "AppInstaller", _FakeInstaller)
    monkeypatch.setattr(update_controller_module.sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(update_controller_module.sys, "executable", "/tmp/open-router-key-viewer", raising=False)
    host = _FakeHost()
    card = _FakeUpdateCard()
    controller = AboutUpdateController(host, card, quit_application=host.quit_application)
    return controller, card, host


def test_show_intro_state_for_source_run(monkeypatch: pytest.MonkeyPatch) -> None:
    controller, card, _ = _make_controller(monkeypatch, frozen=False)

    assert controller.binary_update_supported is False
    assert card.states[-1]["title"] == "可检查更新"
    assert card.states[-1]["can_open_release"] is True


def test_start_update_check_disables_buttons_and_starts_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    controller, card, _ = _make_controller(monkeypatch, frozen=False)

    controller.check_updates()

    assert card.check_button.enabled is False
    assert card.release_button.enabled is False
    assert card.replace_button.enabled is False
    assert card.states[-1]["title"] == "正在检查更新"
    assert isinstance(controller._update_worker, _FakeUpdateWorker)
    assert controller._update_worker.started is True


def test_handle_update_success_for_available_release_notifies_when_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    info_calls: list[dict[str, object]] = []
    monkeypatch.setattr(update_controller_module.InfoBar, "info", lambda **kwargs: info_calls.append(kwargs))
    controller, card, _ = _make_controller(monkeypatch, frozen=False)
    controller._startup_silent_check = True
    release = ReleaseInfo(
        tag_name="v0.3.1",
        version="0.3.1",
        html_url="https://example.com/release",
        published_at="2026-04-14T12:00:00Z",
        body="",
        commit_sha="abcdef1234567890",
        asset=ReleaseAsset(name="open-router-key-viewer", download_url="https://example.com/bin"),
    )
    result = UpdateCheckResult(
        current_version="0.3.0",
        latest_release=release,
        version_comparison=1,
        update_available=True,
    )

    controller._handle_update_success(result)

    assert card.states[-1]["title"] == "发现新版本 v0.3.1"
    assert card.states[-1]["can_open_release"] is True
    assert card.states[-1]["can_replace"] is False
    assert info_calls and info_calls[-1]["title"] == "发现新版本"


def test_handle_update_success_marks_latest_release(monkeypatch: pytest.MonkeyPatch) -> None:
    controller, card, _ = _make_controller(monkeypatch, frozen=False)
    release = ReleaseInfo(
        tag_name="v0.3.0",
        version="0.3.0",
        html_url="https://example.com/release",
        published_at="2026-04-14T12:00:00Z",
        body="",
        commit_sha="abcdef1234567890",
        asset=None,
    )
    result = UpdateCheckResult(
        current_version="0.3.0",
        latest_release=release,
        version_comparison=0,
        update_available=False,
    )

    controller._handle_update_success(result)

    assert card.states[-1]["title"] == "当前已是最新版本"
    assert card.states[-1]["can_replace"] is False


def test_handle_update_failure_uses_error_bar_when_not_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    errors: list[tuple[object, str, str]] = []
    monkeypatch.setattr(update_controller_module, "show_error_bar", lambda parent, title, message: errors.append((parent, title, message)))
    controller, card, host = _make_controller(monkeypatch, frozen=False)

    controller._handle_update_failure("boom")

    assert card.states[-1]["title"] == "检查更新失败"
    assert errors == [(host, "检查更新失败", "boom")]


def test_binary_updater_uses_launcher_when_running_installed_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    class _InstalledFakeInstaller(_FakeInstaller):
        def inspect(self) -> _FakeInstallInfo:
            return _FakeInstallInfo(current_is_installed=True, is_installed=True)

    monkeypatch.setattr(update_controller_module, "get_build_info", lambda: _FakeBuildInfo())
    monkeypatch.setattr(update_controller_module, "GitHubReleaseChecker", _FakeReleaseChecker)
    monkeypatch.setattr(update_controller_module, "UpdateCheckWorker", _FakeUpdateWorker)
    monkeypatch.setattr(update_controller_module, "BinaryUpdater", _FakeBinaryUpdater)
    monkeypatch.setattr(update_controller_module, "AppInstaller", _InstalledFakeInstaller)
    monkeypatch.setattr(update_controller_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(update_controller_module.sys, "executable", "/tmp/open-router-key-viewer", raising=False)

    host = _FakeHost()
    card = _FakeUpdateCard()
    controller = AboutUpdateController(host, card)

    assert isinstance(controller._binary_updater, _FakeBinaryUpdater)
    assert controller._binary_updater.kwargs["relaunch_command"] == ["/tmp/open-router-key-viewer-launcher"]


def test_install_success_uses_controlled_quit_path(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduled: list[tuple[int, object]] = []
    monkeypatch.setattr(update_coordinator_module.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    controller, card, host = _make_controller(monkeypatch, frozen=True)

    controller._update_coordinator._handle_install_succeeded()

    assert card.states[-1]["title"] == "更新已下载完成"
    assert scheduled and scheduled[-1][0] == 300
    scheduled[-1][1]()
    assert host.quit_calls == 1


def test_stop_disconnects_worker_signals_before_stopping(monkeypatch: pytest.MonkeyPatch) -> None:
    stopped: list[object] = []
    monkeypatch.setattr(update_controller_module, "stop_thread", lambda worker: stopped.append(worker))
    controller, _, _ = _make_controller(monkeypatch, frozen=True)
    controller.check_updates()
    update_worker = controller._update_worker

    class _FakeInstallWorker:
        def __init__(self) -> None:
            self.progress_changed = _FakeSignal()
            self.succeeded = _FakeSignal()
            self.failed = _FakeSignal()
            self.finished = _FakeSignal()

    controller._install_worker = _FakeInstallWorker()
    install_worker = controller._install_worker
    controller.stop()

    assert update_worker in stopped
    assert install_worker in stopped
    assert install_worker.progress_changed._callbacks == []
    assert install_worker.succeeded._callbacks == []
    assert install_worker.failed._callbacks == []
    assert install_worker.finished._callbacks == []
    assert controller._update_worker is None
    assert controller._install_worker is None
