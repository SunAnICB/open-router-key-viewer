from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GITHUB_API_BASE = "https://api.github.com"
UPDATE_CACHE_RETENTION_HOURS = 24


@dataclass(slots=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int | None = None
    download_count: int | None = None


@dataclass(slots=True)
class ReleaseInfo:
    tag_name: str
    version: str
    html_url: str
    published_at: str
    body: str
    commit_sha: str | None = None
    asset: ReleaseAsset | None = None


@dataclass(slots=True)
class UpdateCheckResult:
    current_version: str
    latest_release: ReleaseInfo
    version_comparison: int
    update_available: bool


class UpdateCheckError(Exception):
    """Raised when a release check fails."""


class UpdateInstallError(Exception):
    """Raised when a binary update install fails."""


class GitHubReleaseChecker:
    def __init__(
        self,
        owner: str,
        repo: str,
        *,
        asset_name: str,
        current_version: str,
        timeout: float = 10.0,
    ) -> None:
        self.owner = owner
        self.repo = repo
        self.asset_name = asset_name
        self.current_version = current_version
        self.timeout = timeout

    def check_latest_release(self) -> UpdateCheckResult:
        payload = self._request_json(f"{GITHUB_API_BASE}/repos/{self.owner}/{self.repo}/releases/latest")
        if not isinstance(payload, dict):
            raise UpdateCheckError("检查更新失败：GitHub 返回的数据结构不符合预期")

        tag_name = _to_str(payload.get("tag_name"))
        html_url = _to_str(payload.get("html_url"))
        if not tag_name or not html_url:
            raise UpdateCheckError("检查更新失败：缺少版本标签或发布链接")

        version = _normalize_version(tag_name)
        asset = self._pick_asset(payload.get("assets"))
        commit_sha = self._resolve_release_commit(tag_name)
        release = ReleaseInfo(
            tag_name=tag_name,
            version=version,
            html_url=html_url,
            published_at=_to_str(payload.get("published_at")) or "-",
            body=_to_str(payload.get("body")) or "",
            commit_sha=commit_sha,
            asset=asset,
        )
        version_comparison = _compare_versions(version, self.current_version)
        return UpdateCheckResult(
            current_version=_normalize_version(self.current_version),
            latest_release=release,
            version_comparison=version_comparison,
            update_available=version_comparison > 0,
        )

    def _resolve_release_commit(self, tag_name: str) -> str | None:
        payload = self._request_json(
            f"{GITHUB_API_BASE}/repos/{self.owner}/{self.repo}/git/ref/tags/{tag_name}"
        )
        if not isinstance(payload, dict):
            return None

        obj = payload.get("object")
        if not isinstance(obj, dict):
            return None
        object_type = _to_str(obj.get("type"))
        object_sha = _to_str(obj.get("sha"))
        if not object_type or not object_sha:
            return None
        if object_type == "commit":
            return object_sha
        if object_type != "tag":
            return None

        tag_payload = self._request_json(
            f"{GITHUB_API_BASE}/repos/{self.owner}/{self.repo}/git/tags/{object_sha}"
        )
        if not isinstance(tag_payload, dict):
            return None
        nested = tag_payload.get("object")
        if not isinstance(nested, dict):
            return None
        if _to_str(nested.get("type")) != "commit":
            return None
        return _to_str(nested.get("sha"))

    def _request_json(self, url: str) -> object:
        request = Request(
            url=url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"open-router-key-viewer/{self.current_version}",
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            if exc.code == 403:
                raise UpdateCheckError("检查更新失败：GitHub API 速率限制已触发，请稍后重试") from exc
            raise UpdateCheckError(f"检查更新失败：HTTP {exc.code}") from exc
        except URLError as exc:
            raise UpdateCheckError(f"检查更新失败：{exc.reason}") from exc

        try:
            return json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise UpdateCheckError("检查更新失败：GitHub 返回了无效 JSON") from exc

    def _pick_asset(self, assets_obj: object) -> ReleaseAsset | None:
        if not isinstance(assets_obj, list):
            return None

        preferred: ReleaseAsset | None = None
        fallback: ReleaseAsset | None = None
        for entry in assets_obj:
            if not isinstance(entry, dict):
                continue
            name = _to_str(entry.get("name"))
            download_url = _to_str(entry.get("browser_download_url"))
            if not name or not download_url:
                continue

            asset = ReleaseAsset(
                name=name,
                download_url=download_url,
                size=_to_int(entry.get("size")),
                download_count=_to_int(entry.get("download_count")),
            )
            if fallback is None:
                fallback = asset
            if name == self.asset_name:
                preferred = asset
                break

        return preferred or fallback


class BinaryUpdater:
    def __init__(
        self,
        current_binary: Path,
        *,
        cache_root: Path | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.current_binary = current_binary
        self.cache_root = cache_root or (Path.home() / ".cache" / "open-router-key-viewer" / "updates")
        self.timeout = timeout

    def can_replace_current_binary(self) -> tuple[bool, str]:
        if not self.current_binary.exists():
            return False, "当前二进制文件不存在。"
        if not os.access(self.current_binary, os.W_OK):
            return False, "当前二进制文件不可写，无法直接替换。"

        parent_dir = self.current_binary.parent
        if not os.access(parent_dir, os.W_OK):
            return False, "当前目录不可写，无法写入新版本。"
        return True, ""

    def cleanup_stale_updates(self) -> None:
        if not self.cache_root.exists():
            return

        cutoff = datetime.now() - timedelta(hours=UPDATE_CACHE_RETENTION_HOURS)
        for path in self.cache_root.iterdir():
            if not path.is_dir():
                continue
            if path.name.startswith("pending-"):
                continue
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError:
                continue
            if modified < cutoff:
                _safe_rmtree(path)

    def install_from_asset(
        self,
        asset: ReleaseAsset,
        *,
        current_pid: int,
        progress_callback: Callable[[int, int | None], None] | None = None,
    ) -> None:
        ok, reason = self.can_replace_current_binary()
        if not ok:
            raise UpdateInstallError(reason)

        temp_dir = self._prepare_update_dir()
        downloaded_path = temp_dir / asset.name
        script_path = temp_dir / "apply-update.sh"

        self._download_asset(asset.download_url, downloaded_path, progress_callback=progress_callback)
        downloaded_path.chmod(0o755)
        script_path.write_text(
            self._replacement_script(downloaded_path, self.current_binary, temp_dir),
            encoding="utf-8",
        )
        script_path.chmod(0o755)

        try:
            subprocess.Popen(  # noqa: S603
                ["/bin/sh", str(script_path), str(current_pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise UpdateInstallError(f"无法启动更新替换脚本：{exc}") from exc

    def _prepare_update_dir(self) -> Path:
        self.cache_root.mkdir(parents=True, exist_ok=True)
        update_dir = self.cache_root / f"pending-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        suffix = 0
        while update_dir.exists():
            suffix += 1
            update_dir = self.cache_root / f"pending-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{suffix}"
        update_dir.mkdir(parents=True, exist_ok=False)
        return update_dir

    def _download_asset(
        self,
        url: str,
        destination: Path,
        *,
        progress_callback: Callable[[int, int | None], None] | None = None,
    ) -> None:
        request = Request(
            url=url,
            headers={"Accept": "application/octet-stream"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                total = response.headers.get("Content-Length")
                total_bytes = int(total) if total and total.isdigit() else None
                received = 0
                with destination.open("wb") as file:
                    while True:
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        file.write(chunk)
                        received += len(chunk)
                        if progress_callback is not None:
                            progress_callback(received, total_bytes)
        except HTTPError as exc:
            raise UpdateInstallError(f"下载更新失败：HTTP {exc.code}") from exc
        except URLError as exc:
            raise UpdateInstallError(f"下载更新失败：{exc.reason}") from exc
        except OSError as exc:
            raise UpdateInstallError(f"写入更新文件失败：{exc}") from exc

    def _replacement_script(self, downloaded_path: Path, target_path: Path, update_dir: Path) -> str:
        escaped_downloaded = _shell_quote(str(downloaded_path))
        escaped_target = _shell_quote(str(target_path))
        escaped_target_dir = _shell_quote(str(target_path.parent))
        escaped_update_dir = _shell_quote(str(update_dir))
        escaped_script_log = _shell_quote(str(update_dir / "apply-update.log"))
        escaped_app_log = _shell_quote(str(update_dir / "relaunch.log"))
        return f"""#!/bin/sh
set -eu
PID="$1"
SCRIPT_LOG={escaped_script_log}
APP_LOG={escaped_app_log}
TARGET={escaped_target}
TARGET_DIR={escaped_target_dir}
DOWNLOADED={escaped_downloaded}
UPDATE_DIR={escaped_update_dir}

log() {{
  printf '%s %s\\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >>"$SCRIPT_LOG"
}}

mkdir -p "$UPDATE_DIR"
touch "$SCRIPT_LOG" "$APP_LOG"
log "Waiting for process $PID to exit"
while kill -0 "$PID" 2>/dev/null; do
  sleep 1
done
log "Replacing binary"
chmod +x "$DOWNLOADED"
mv "$DOWNLOADED" "$TARGET"
chmod +x "$TARGET"
cd "$TARGET_DIR"

log "Launching updated application"
nohup "$TARGET" >>"$APP_LOG" 2>&1 &
NEW_PID=$!

sleep 2
if kill -0 "$NEW_PID" 2>/dev/null; then
  log "Relaunch succeeded with pid $NEW_PID"
  exit 0
fi

log "Relaunch failed; see $APP_LOG"
exit 1
"""


def _normalize_version(value: str) -> str:
    stripped = value.strip()
    if stripped.lower().startswith("v"):
        return stripped[1:]
    return stripped


def _compare_versions(left: str, right: str) -> int:
    left_parts = _version_parts(_normalize_version(left))
    right_parts = _version_parts(_normalize_version(right))
    if left_parts > right_parts:
        return 1
    if left_parts < right_parts:
        return -1
    return 0


def _version_parts(value: str) -> tuple[int, int, int]:
    raw_parts = value.split(".")
    parts: list[int] = []
    for part in raw_parts[:3]:
        digits = []
        for char in part:
            if char.isdigit():
                digits.append(char)
            else:
                break
        parts.append(int("".join(digits) or "0"))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])  # type: ignore[return-value]


def _to_str(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _to_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _safe_rmtree(path: Path) -> None:
    try:
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        path.rmdir()
    except OSError:
        return
