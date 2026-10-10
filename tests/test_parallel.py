"""Chạy song song: cửa sổ QUÉT đưa bài vào hàng chờ, cửa sổ BÌNH LUẬN lấy bài MỚI NHẤT ra bình luận ngay.
Trình duyệt giả + đồng hồ giả: không mở Chrome, không chờ thật."""
from types import SimpleNamespace

import pytest

from modules import group_checker as gc
from modules.db import Q_DONE, Q_EXPIRED, Q_RUNNING, Q_SKIPPED, Q_WAITING, Database
from modules.queue_runner import QueueRunner
from modules.scanner import Scanner

LOG = SimpleNamespace(info=lambda *a: None, warning=lambda *a: None, error=lambda *a: None)
GROUP = "https://www.facebook.com/groups/manhinh/"


def cfg(tmp_path, **over):
    base = dict(MAX_POST_AGE_MINUTES=360, MIN_DELAY=0, MAX_DELAY=0, QUEUE_IDLE_SECONDS=15, QUEUE_HOUSEKEEP_MINUTES=30,
                QUEUE_HOUSEKEEP_VERIFY=5, QUEUE_HOUSEKEEP_JOINS=2, AUTO_JOIN=True, JOIN_RETRY_DAYS=1,
                MAX_COMMENTED_POSTS_PER_DAY=40, COMMENT_LOG_FILE=str(tmp_path / "nhat_ky.xlsx"), YIELD_DAYS=7,
                GROUP_RESCAN_MINUTES=60, LOW_YIELD_MIN_SCANS=3, LOW_YIELD_RESCAN_HOURS=24, LOW_YIELD_OBSERVE_HOURS=24,
                HOT_RESCAN_MINUTES=3, SCAN_ACTIVE_MINUTES=10, SCAN_ACTIVE_POSTS_PER_DAY=100, SCAN_OVERLAP_MINUTES=10,
                SCAN_PAUSE_SECONDS=(0, 0))
    return SimpleNamespace(**{**base, **over})


class Clock:
    def __init__(self):
        self.t, self.slept = 0.0, []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


class FakeWatcher:
    def __init__(self, result="Hoàn tất"):
        self.result, self.commented, self.joined, self.verified = result, [], [], []

    def comment_post(self, commenter, pool, group, post):
        self.commented.append(post["url"])
        return self.result

    def _join(self, g):
        self.joined.append(g["group_url"])

    def verify(self, commenter, limit=None):
        self.verified.append(limit)


def post(n, age):
    return {"url": f"https://www.facebook.com/groups/manhinh/posts/{n}/", "text": f"Cần tìm màn {n}", "age": age,
            "topic": "Màn hình"}


@pytest.fixture
def env(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    clock, watcher, between = Clock(), FakeWatcher(), []
    runner = QueueRunner(watcher, None, lambda g: [{"name": "sp"}], cfg(tmp_path), LOG, db,
                         between=lambda: between.append(clock.t), sleep=clock.sleep, clock=clock)
    return SimpleNamespace(db=db, clock=clock, watcher=watcher, runner=runner, between=between, tmp=tmp_path)


def status(db, n):
    return db.query("SELECT status FROM post_queue WHERE post_url LIKE ?", (f"%/posts/{n}/",))[0]["status"]


def test_newest_post_is_commented_first(env):
    for n, age in ((1, 50), (2, 2), (3, 20)):
        env.db.enqueue_post(GROUP, "Màn hình", post(n, age), 1.0)
    for _ in range(3):
        env.runner.comment_next()
    assert [u.split("/")[-2] for u in env.watcher.commented] == ["2", "3", "1"]
    assert status(env.db, 2) == Q_DONE


def test_same_post_is_queued_once(env):
    assert env.db.enqueue_post(GROUP, "Màn hình", post(1, 5), 1.0)
    assert not env.db.enqueue_post(GROUP, "Màn hình", post(1, 9), 1.0)


def test_too_old_posts_expire_instead_of_being_commented(env):
    env.db.enqueue_post(GROUP, "Màn hình", post(1, 400), 1.0)
    assert env.runner.comment_next() is None
    assert status(env.db, 1) == Q_EXPIRED


def test_post_commented_meanwhile_is_skipped(env):
    env.db.enqueue_post(GROUP, "Màn hình", post(1, 5), 1.0)
    env.db.add_post(post(1, 5)["url"], "Màn hình", GROUP, "", 5)
    assert env.runner.comment_next() == "skip"
    assert status(env.db, 1) == Q_SKIPPED and env.watcher.commented == []


def test_no_products_keeps_post_waiting(env):
    env.runner.pick_comments = lambda g: []
    env.db.enqueue_post(GROUP, "Màn hình", post(1, 5), 1.0)
    assert env.runner.comment_next() == "no_products"
    assert status(env.db, 1) == Q_WAITING


def test_failed_post_without_any_comment_is_retried_once(env):
    env.watcher.result = "Thất bại"        # vd mạng chập chờn lúc mở bài
    env.db.enqueue_post(GROUP, "Màn hình", post(1, 5), 1.0)
    env.runner.comment_next()
    assert status(env.db, 1) == Q_WAITING   # trả lại hàng chờ
    env.runner.comment_next()
    assert status(env.db, 1) == Q_SKIPPED and len(env.watcher.commented) == 2   # thất bại lần 2: thôi


def test_failed_post_with_a_comment_sent_is_not_retried(env):
    url = post(1, 5)["url"]
    pid = env.db.add_post(url, "Màn hình", GROUP, "", 5)
    env.db.add_comment(pid, 1, "x", "", "Đã đăng")
    assert not env.db.forget_failed_post(url)        # đã có bình luận hiện trên bài: không gửi lại (tránh trùng)
    assert env.db.has_post(url)
    pid2 = env.db.add_post(post(2, 5)["url"], "Màn hình", GROUP, "", 5)
    env.db.add_comment(pid2, 1, "x", "", "Lỗi")
    assert env.db.forget_failed_post(post(2, 5)["url"]) and not env.db.has_post(post(2, 5)["url"])


def test_interrupted_post_goes_back_to_queue(env):
    env.db.enqueue_post(GROUP, "Màn hình", post(1, 5), 1.0)
    env.db.execute("UPDATE post_queue SET status = ?", (Q_RUNNING,))
    assert env.db.requeue_interrupted() == 1
    assert status(env.db, 1) == Q_WAITING


def test_step_comments_then_rests_and_still_posts_schedule(env):
    env.runner.config.MIN_DELAY = env.runner.config.MAX_DELAY = 130
    env.db.enqueue_post(GROUP, "Màn hình", post(1, 5), 1.0)
    result = env.runner.step(lambda: False, lambda: None, lambda: 600)
    assert result == "Hoàn tất"
    assert sum(env.clock.slept) == pytest.approx(130)
    assert len(env.between) == 3   # ngay sau bài + 2 lần trong 130 giây nghỉ (đăng bài theo lịch nếu đến giờ)


def test_idle_queue_joins_a_few_groups_and_verifies_a_few_posts(env):
    for i in range(3):
        env.db.set_join(f"https://www.facebook.com/groups/g{i}/", f"g{i}", gc.NOT_JOINED, "phát hiện khi quét")
    env.runner.step(lambda: False, lambda: None, lambda: 600)
    assert len(env.watcher.joined) == 2 and env.watcher.verified == [5]
    env.runner.step(lambda: False, lambda: None, lambda: 600)     # vừa dọn xong: 30 phút sau mới dọn lại
    assert len(env.watcher.joined) == 2 and env.watcher.verified == [5]


def test_daily_cap_housekeeps_fully_then_rests_until_tomorrow(env):
    env.db.enqueue_post(GROUP, "Màn hình", post(1, 5), 1.0)
    assert env.runner.step(lambda: True, lambda: None, lambda: 600) == "daily_full"
    assert env.watcher.commented == [] and env.watcher.verified == [None]
    assert sum(env.clock.slept) == pytest.approx(600 * 60)


def test_pause_button_interrupts_long_rest(env):
    env.runner.config.MIN_DELAY = env.runner.config.MAX_DELAY = 3600
    env.db.enqueue_post(GROUP, "Màn hình", post(1, 5), 1.0)
    env.runner.sleep = lambda s: (env.clock.sleep(s), env.db.set_setting("paused", "1"))
    env.runner.step(lambda: False, lambda: None, lambda: 600)
    assert env.clock.t < 60    # bấm Tạm dừng trên web: thôi chờ ngay


# ---------- cửa sổ QUÉT ----------
class FakeScanWatcher:
    def __init__(self, results):
        self.results, self.windows, self.scanned = list(results), [], []

    def check_and_scan(self, g, window):
        self.windows.append(window)
        self.scanned.append(g["group_url"])
        return self.results.pop(0) if self.results else ("ok", [])


def scanner(tmp_path, db, results, groups=None, scanner_id=1, **flags):
    logs, sleeps = [], []
    log = SimpleNamespace(info=logs.append, warning=logs.append, error=logs.append)
    s = Scanner(FakeScanWatcher(results), cfg(tmp_path), log, db,
                lambda: groups or [{"group_url": GROUP, "group_name": "Màn hình", "hot": True}],
                daily_full=lambda: flags.get("daily_full", False), blocked_until=lambda: None, sleep=sleeps.append,
                scanner_id=scanner_id)
    return s, logs, sleeps


OTHER = "https://www.facebook.com/groups/chomanhinhhanoi/"
TWO_GROUPS = [{"group_url": GROUP, "group_name": "Màn hình", "hot": True},
              {"group_url": OTHER, "group_name": "Chợ màn hình Hà Nội"}]


def test_two_scan_windows_never_scan_the_same_group(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    assert db.claim_group(GROUP, 1, 3)                     # cửa sổ quét 1 đang quét nhóm hot
    s2, _, _ = scanner(tmp_path, db, [], groups=TWO_GROUPS, scanner_id=2)
    s2.step()
    assert s2.watcher.scanned == [OTHER]                  # cửa sổ 2 quét nhóm khác
    assert not db.claim_group(GROUP, 2, 3)                # nhóm cửa sổ 1 đang quét: cửa sổ 2 không giữ chỗ được
    db.finish_claim(GROUP, 1)
    s2.step()
    assert s2.watcher.scanned == [OTHER]                  # cửa sổ 1 vừa quét xong: chưa tới lượt quét lại


def test_claim_of_a_crashed_scan_window_expires(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    assert db.claim_group(GROUP, 1, 3)
    db.execute("UPDATE scan_claims SET claimed_at = '2026-01-01 00:00:00'")   # cửa sổ 1 bị tắt giữa chừng từ lâu
    assert db.claim_group(GROUP, 2, 3)
    assert db.busy_groups(1, 3) == {GROUP}                # với cửa sổ 1: nhóm này cửa sổ 2 đang quét


def test_each_scan_window_has_its_own_progress(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    db.set_scan_progress(1, phase="Quét nhóm", group_name="A")
    db.set_scan_progress(2, phase="Chờ nhóm tới lượt quét")
    assert db.scan_progress(1)["group_name"] == "A" and db.scan_progress(2)["phase"] == "Chờ nhóm tới lượt quét"


def test_scanner_puts_new_posts_in_queue(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    s, logs, _ = scanner(tmp_path, db, [("ok", [post(1, 3), post(2, 8)])])
    assert s.step() == 2
    assert s.watcher.windows == [360]                         # nhóm chưa quét lần nào: xét bài trong 6 giờ
    assert db.next_queued(360)["post_url"].endswith("/posts/1/")
    assert any("2 bài mới vào hàng chờ" in m for m in logs)


def test_scanner_waits_for_next_turn_after_skipping_a_group(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    s, logs, sleeps = scanner(tmp_path, db, [("chưa tham gia nhóm", [])])
    assert s.step() == 0
    assert s.step() == 0 and len(s.watcher.windows) == 1     # nhóm bị bỏ qua cũng chờ tới lượt sau
    assert sum("chưa tham gia nhóm" in m for m in logs) == 1


def test_scanner_rests_when_paused_or_daily_cap_reached(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    s, _, sleeps = scanner(tmp_path, db, [], daily_full=True)
    assert s.step() == 0 and sleeps == [30] and s.watcher.windows == []
    db.set_setting("paused", "1")
    s2, _, sleeps2 = scanner(tmp_path, db, [])
    assert s2.step() == 0 and sleeps2 == [30]
