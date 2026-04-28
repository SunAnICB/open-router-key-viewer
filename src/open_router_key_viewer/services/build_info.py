from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from open_router_key_viewer._build_info import BUILD_COMMIT, BUILD_DIRTY


@dataclass(slots=True)
class BuildInfo:
    commit_sha: str
    dirty: bool
    source: str


def get_build_info() -> BuildInfo:
    commit_sha = BUILD_COMMIT.strip()
    if commit_sha and commit_sha != "unknown":
        return BuildInfo(commit_sha=commit_sha, dirty=bool(BUILD_DIRTY), source="embedded")

    repo_root = _detect_repo_root()
    if repo_root is not None:
        git_info = _read_git_info(repo_root)
        if git_info is not None:
            return git_info

    return BuildInfo(commit_sha="unknown", dirty=bool(BUILD_DIRTY), source="embedded")


def _detect_repo_root() -> Path | None:
    candidates = [
        Path(__file__).resolve().parents[3],
        Path.cwd(),
    ]
    for candidate in candidates:
        if (candidate / ".git").exists():
            return candidate
    return None


def _read_git_info(repo_root: Path) -> BuildInfo | None:
    try:
        commit = _run_git(repo_root, "rev-parse", "HEAD")
        status = _run_git(repo_root, "status", "--porcelain")
    except OSError:
        return None
    except subprocess.CalledProcessError:
        return None

    return BuildInfo(
        commit_sha=commit.strip() or "unknown",
        dirty=bool(status.strip()),
        source="git",
    )


def _run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout
