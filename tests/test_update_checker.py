from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from open_router_key_viewer.services.update_checker import BinaryUpdater, _compare_versions


def test_compare_versions_handles_v_prefix_and_missing_parts() -> None:
    assert _compare_versions("v0.3.1", "0.3.0") == 1
    assert _compare_versions("0.3", "0.3.0") == 0
    assert _compare_versions("0.3.0", "0.3.1") == -1


def test_cleanup_stale_updates_removes_old_non_pending_dirs(tmp_path: Path) -> None:
    current_binary = tmp_path / "app"
    current_binary.write_text("bin", encoding="utf-8")
    cache_root = tmp_path / "updates"
    old_dir = cache_root / "20240101"
    pending_dir = cache_root / "pending-20240101"
    recent_dir = cache_root / "20240102"

    old_dir.mkdir(parents=True)
    pending_dir.mkdir(parents=True)
    recent_dir.mkdir(parents=True)
    (old_dir / "old.txt").write_text("x", encoding="utf-8")
    (pending_dir / "pending.txt").write_text("x", encoding="utf-8")
    (recent_dir / "recent.txt").write_text("x", encoding="utf-8")

    stale_time = (datetime.now() - timedelta(hours=25)).timestamp()
    fresh_time = datetime.now().timestamp()
    import os

    os.utime(old_dir, (stale_time, stale_time))
    os.utime(old_dir / "old.txt", (stale_time, stale_time))
    os.utime(recent_dir, (fresh_time, fresh_time))
    os.utime(recent_dir / "recent.txt", (fresh_time, fresh_time))
    os.utime(pending_dir, (stale_time, stale_time))
    os.utime(pending_dir / "pending.txt", (stale_time, stale_time))

    updater = BinaryUpdater(current_binary, cache_root=cache_root)
    updater.cleanup_stale_updates()

    assert not old_dir.exists()
    assert pending_dir.exists()
    assert recent_dir.exists()
