from __future__ import annotations

from pathlib import Path

import open_router_key_viewer.services.build_info as build_info_module
from open_router_key_viewer.services.build_info import BuildInfo, get_build_info


def test_get_build_info_prefers_embedded_metadata(monkeypatch) -> None:
    monkeypatch.setattr(build_info_module, "BUILD_COMMIT", "abcdef1234567890")
    monkeypatch.setattr(build_info_module, "BUILD_DIRTY", False)
    monkeypatch.setattr(build_info_module, "_detect_repo_root", lambda: Path("/tmp/dirty-repo"))

    def fail_if_git_is_read(_repo_root: Path) -> BuildInfo:
        raise AssertionError("release build metadata must not be overwritten by runtime git state")

    monkeypatch.setattr(build_info_module, "_read_git_info", fail_if_git_is_read)

    info = get_build_info()

    assert info == BuildInfo(commit_sha="abcdef1234567890", dirty=False, source="embedded")


def test_get_build_info_uses_git_when_embedded_metadata_is_unknown(monkeypatch) -> None:
    git_info = BuildInfo(commit_sha="1234567890abcdef", dirty=True, source="git")

    monkeypatch.setattr(build_info_module, "BUILD_COMMIT", "unknown")
    monkeypatch.setattr(build_info_module, "BUILD_DIRTY", False)
    monkeypatch.setattr(build_info_module, "_detect_repo_root", lambda: Path("/tmp/source-repo"))
    monkeypatch.setattr(build_info_module, "_read_git_info", lambda _repo_root: git_info)

    assert get_build_info() == git_info

