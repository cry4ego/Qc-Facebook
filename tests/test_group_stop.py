"""Ngừng nhóm khi nhóm từ chối bình luận. Trước 25/10 MỘT bình luận bản không SĐT bị từ chối là bot NGỪNG VĨNH VIỄN cả nhóm: nhóm tốt
nhất của shop (102 bài khách cần mua / 14 ngày) bị ngừng từ 23/10 vì 1/194 bình luận bị từ chối, kéo theo 26 bài khách bị bỏ. Nay chỉ
ngừng khi từ chối DÀY (≥ GROUP_STOP_MIN_REJECTS lần trong GROUP_STOP_WINDOW_HOURS giờ và ≥ GROUP_STOP_MIN_RATE số bình luận), ngừng
có thời hạn (gấp đôi mỗi lần tái diễn, có trần) rồi tự mở lại."""
import itertools
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from config import Config
from modules import watcher as w
from modules.db import FULL, REJECTED, REJECTED_DELETED, SAFE, SENT, Database

NOW = datetime(2026, 10, 25, 20, 0)
FMT = "%Y-%m-%d %H:%M:%S"
GROUP_URL = "https://www.facebook.com/groups/111/"
KHAC = "https://www.facebook.com/groups/222/"
CS = dict(min_rejects=3, window_hours=72, min_rate=0.2, base_hours=12, max_hours=96)
_dem = itertools.count(1)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def binh_luan(db, status=SENT, variant=SAFE, luc=NOW, group=GROUP_URL):
    """Ghi 1 bình luận (kèm bài) vào nhóm `group` lúc `luc`; trả về id bài"""
    post_id = db.add_post(f"{group}posts/{next(_dem)}", "Nhóm", group, "x", 5)
    comment_id = db.add_comment(post_id, 1, "Bình luận", "", status, "", variant)
    db.execute("UPDATE comments SET sent_at = ? WHERE id = ?", (luc.strftime(FMT), comment_id))
    return post_id


def nhieu(db, so, **kw):
    for _ in range(so):
        binh_luan(db, **kw)


def tu_choi(db, so, **kw):
    nhieu(db, so, status=REJECTED_DELETED, **kw)


# ---------- quy tắc ngừng ----------
def test_one_rejection_among_many_comments_never_stops_the_group(db):
    nhieu(db, 193)
    tu_choi(db, 1)                                            # đúng tình huống thật: 1 / 194
    assert db.note_safe_rejection(GROUP_URL, "Nhóm", "bị từ chối", now=NOW, **CS) is None
    assert db.is_stopped(GROUP_URL, NOW) is False


def test_dense_rejections_stop_the_group_for_a_while_not_forever(db):
    nhieu(db, 5)
    tu_choi(db, 3)
    ket_qua = db.note_safe_rejection(GROUP_URL, "Nhóm", "bị từ chối", now=NOW, **CS)
    assert ket_qua == {"gio": 12, "bi_tu_choi": 3, "tong": 8, "lan": 1}
    assert db.is_stopped(GROUP_URL, NOW + timedelta(hours=11, minutes=59)) is True
    assert db.is_stopped(GROUP_URL, NOW + timedelta(hours=12, minutes=1)) is False        # tự mở lại


def test_a_big_group_with_proportionally_few_rejections_is_not_stopped(db):
    nhieu(db, 97)
    tu_choi(db, 3)                                            # 3% < 20%
    assert db.note_safe_rejection(GROUP_URL, "Nhóm", "x", now=NOW, **CS) is None


def test_a_group_that_rejects_everything_is_stopped_after_three(db):
    tu_choi(db, 2)
    assert db.note_safe_rejection(GROUP_URL, "Nhóm", "x", now=NOW, **CS) is None          # mới 2 lần: chờ thêm
    tu_choi(db, 1)
    assert db.note_safe_rejection(GROUP_URL, "Nhóm", "x", now=NOW, **CS)["gio"] == 12


def test_old_rejections_outside_the_window_do_not_count(db):
    tu_choi(db, 3, luc=NOW - timedelta(hours=73))
    tu_choi(db, 1)
    assert db.note_safe_rejection(GROUP_URL, "Nhóm", "x", now=NOW, **CS) is None


def test_rejections_of_the_full_version_do_not_count_as_safe_rejections(db):
    tu_choi(db, 3, variant=FULL)
    assert db.note_safe_rejection(GROUP_URL, "Nhóm", "x", now=NOW, **CS) is None


def test_a_rejected_but_not_deleted_comment_counts_too(db):
    nhieu(db, 3, status=REJECTED)
    assert db.note_safe_rejection(GROUP_URL, "Nhóm", "x", now=NOW, **CS) is not None


def test_other_groups_are_not_affected(db):
    tu_choi(db, 3)
    nhieu(db, 10, group=KHAC)
    db.note_safe_rejection(GROUP_URL, "Nhóm", "x", now=NOW, **CS)
    assert db.is_stopped(GROUP_URL, NOW) is True and db.is_stopped(KHAC, NOW) is False


def test_repeated_stops_last_longer_each_time_up_to_the_cap(db):
    tu_choi(db, 3)
    gio = []
    for lan in range(5):
        gio.append(db.note_safe_rejection(GROUP_URL, "Nhóm", "x", now=NOW + timedelta(minutes=lan), **CS)["gio"])
    assert gio == [12, 24, 48, 96, 96]


def test_the_count_starts_over_after_a_quiet_week(db):
    tu_choi(db, 3)
    assert db.note_safe_rejection(GROUP_URL, "Nhóm", "x", now=NOW, **CS)["gio"] == 12
    sau = NOW + timedelta(days=8)
    tu_choi(db, 3, luc=sau)
    assert db.note_safe_rejection(GROUP_URL, "Nhóm", "x", now=sau, **CS)["gio"] == 12


def test_resetting_a_group_from_the_web_lifts_the_stop(db):
    tu_choi(db, 3)
    db.note_safe_rejection(GROUP_URL, "Nhóm", "x", now=NOW, **CS)
    db.reset_safe(GROUP_URL)
    assert db.is_stopped(GROUP_URL, NOW) is False


def test_a_missing_group_url_is_ignored(db):
    assert db.note_safe_rejection("", "Nhóm", "x", now=NOW, **CS) is None


# ---------- bản ghi cũ (trước 25/10: ngừng vĩnh viễn) ----------
def test_a_permanent_stop_from_the_old_version_expires_when_the_database_is_upgraded(tmp_path):
    duong_dan = str(tmp_path / "cu.db")
    conn = sqlite3.connect(duong_dan)
    conn.execute("CREATE TABLE safe_groups (group_url TEXT PRIMARY KEY, group_name TEXT, since TEXT, reason TEXT, "
                 "stop INTEGER DEFAULT 0)")
    gan_day = (datetime.now() - timedelta(hours=1)).strftime(FMT)
    conn.executemany("INSERT INTO safe_groups VALUES (?, ?, ?, ?, ?)", [
        (GROUP_URL, "Nhóm tốt nhất", "2026-10-23 16:31:00", "Bản không SĐT/địa chỉ cũng bị từ chối (bình luận 3)", 1),
        (KHAC, "Nhóm vừa bị ngừng", gan_day, "vừa bị ngừng", 1)])
    conn.commit()
    conn.close()
    db = Database(duong_dan)
    assert db.is_stopped(GROUP_URL) is False                  # ngừng từ 2 ngày trước: đã hết hạn
    assert db.is_stopped(KHAC) is True                        # mới ngừng 1 giờ trước: vẫn đang ngừng
    Database(duong_dan)                                       # nâng cấp lần hai không làm hỏng gì


def test_a_stop_row_written_by_a_not_yet_restarted_old_process_still_expires(db):
    db.execute("INSERT INTO safe_groups (group_url, group_name, since, reason, stop) VALUES (?, ?, ?, ?, 1)",
               (GROUP_URL, "Nhóm", (NOW - timedelta(hours=13)).strftime(FMT), "cũ"))
    db.execute("INSERT INTO safe_groups (group_url, group_name, since, reason, stop) VALUES (?, ?, ?, ?, 1)",
               (KHAC, "Nhóm", (NOW - timedelta(hours=1)).strftime(FMT), "cũ"))
    assert db.is_stopped(GROUP_URL, NOW) is False and db.is_stopped(KHAC, NOW) is True


# ---------- watcher dùng đúng quy tắc ----------
@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(w.time, "sleep", lambda s: None)
    cfg = SimpleNamespace(**{k: getattr(Config, k) for k in dir(Config) if k.isupper()})
    cfg.DB_FILE = str(tmp_path / "w.db")
    cfg.INTENT_AI = False
    db = Database(cfg.DB_FILE)
    db.set_setting("safe_all", "1")                           # đúng như đang chạy thật: mọi bình luận là bản không SĐT
    log = SimpleNamespace(info=lambda *a: None, warning=lambda *a: None, error=lambda *a: None)
    return SimpleNamespace(db=db, cfg=cfg, watcher=w.GroupWatcher(None, cfg, log, db))


class NguoiBinhLuan:
    """Trình bình luận giả: gửi bình luận nào cũng trả kết quả định sẵn"""
    last_article = None

    def __init__(self, ket_qua):
        self.ket_qua, self.da_gui = ket_qua, []

    def open_post(self, url):
        pass

    def already_commented(self):
        return False

    def send_comment(self, c):
        self.da_gui.append(c)
        return self.ket_qua, ""

    def delete_comment(self, article):
        return False

    def screenshot(self, path):
        return ""


POOL = [{"text": "Đầy đủ", "safe_text": "An toàn", "image": None, "safe_image": None, "name": "A", "variant_id": 1}]
NHOM = {"group_url": GROUP_URL, "group_name": "Nhóm test"}


def binh_luan_bai(env, ket_qua, so):
    for _ in range(so):
        env.watcher.comment_post(NguoiBinhLuan(ket_qua), POOL, NHOM, {"url": f"{GROUP_URL}posts/{next(_dem)}", "text": "x", "age": 5})


def test_the_watcher_does_not_stop_a_group_for_a_single_rejected_comment(env):
    nhieu(env.db, 40, luc=datetime.now() - timedelta(hours=2))
    binh_luan_bai(env, REJECTED, 1)
    assert env.db.is_stopped(GROUP_URL) is False


def test_the_watcher_stops_a_group_that_keeps_rejecting_and_the_stop_ends_by_itself(env):
    binh_luan_bai(env, REJECTED, 3)
    assert env.db.is_stopped(GROUP_URL) is True
    assert env.db.is_stopped(GROUP_URL, datetime.now() + timedelta(hours=13)) is False


def test_a_late_rejection_found_when_reviewing_follows_the_same_rule(env):
    nhieu(env.db, 40, luc=datetime.now() - timedelta(hours=2))
    post_id = binh_luan(env.db, status=SENT, luc=datetime.now())

    class KiemTraLai:
        def review_post(self, url):
            return ["Bình luận"], 0

    post = env.db.query("SELECT * FROM posts WHERE id = ?", (post_id,))[0]
    env.watcher.review(KiemTraLai(), post)
    assert env.db.comments_of(post_id)[0]["status"] == REJECTED_DELETED
    assert env.db.is_stopped(GROUP_URL) is False              # 1 lần từ chối muộn / 41 bình luận: chưa ngừng
