"""Giới hạn số bài bình luận mỗi ngày (MAX_COMMENTED_POSTS_PER_DAY) và thời gian nghỉ tới ngày mai."""
from datetime import datetime
from types import SimpleNamespace

from modules.db import Database
from modules.watcher import daily_cap_reached, minutes_to_tomorrow


def db_with_posts(tmp_path, statuses):
    db = Database(str(tmp_path / "t.db"))
    for i, status in enumerate(statuses):
        post_id = db.add_post(f"https://www.facebook.com/groups/g/posts/{i}/", "Nhóm", "g", "Cần mua màn 24 inch", 5)
        db.update_post(post_id, status=status)
    return db


def test_cap_counts_only_commented_posts(tmp_path):
    db = db_with_posts(tmp_path, ["Hoàn tất", "Một phần", "Bị chặn", "Đang bình luận"])
    assert not daily_cap_reached(db, SimpleNamespace(MAX_COMMENTED_POSTS_PER_DAY=3))
    assert daily_cap_reached(db, SimpleNamespace(MAX_COMMENTED_POSTS_PER_DAY=2))


def test_zero_cap_means_unlimited(tmp_path):
    db = db_with_posts(tmp_path, ["Hoàn tất"] * 5)
    assert not daily_cap_reached(db, SimpleNamespace(MAX_COMMENTED_POSTS_PER_DAY=0))


def test_minutes_to_tomorrow_waits_until_after_midnight():
    assert minutes_to_tomorrow(datetime(2026, 10, 6, 23, 0)) == 61
    assert minutes_to_tomorrow(datetime(2026, 10, 6, 0, 0, 30)) == 24 * 60 + 0.5
    assert minutes_to_tomorrow(datetime(2026, 12, 31, 12, 0)) == 12 * 60 + 1
