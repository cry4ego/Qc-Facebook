"""Đăng bài theo lịch: nhóm không đăng được vì lý do của nhóm (chưa tham gia, chỉ cho đăng tin bán, đầy bài chờ duyệt,
không xem được) không bị tính là 'hỏng' và được ghi nhớ để lần sau bỏ qua; lỗi thật thì dọn cửa sổ soạn bài."""
from types import SimpleNamespace

import pytest

from modules import fb_selectors as sel
from modules import poster as p
from modules.db import Database


class El:
    def __init__(self, text=""):
        self.text = text

    def is_displayed(self):
        return True


class PageDriver:
    """Trang nhóm giả: chữ trên trang + các nút đang hiện (theo XPath)"""

    def __init__(self, body="", buttons=()):
        self.body, self.buttons = body, set(buttons)

    def find_element(self, by, what):
        return El(self.body)

    def find_elements(self, by, xpath):
        return [El()] if xpath in self.buttons else []


CFG = SimpleNamespace(MIN_DELAY=0, MAX_DELAY=0, MAX_POSTS_PER_DAY=10, SCREENSHOT_DIR="")


@pytest.mark.parametrize("body, buttons, note", [
    ("Bạn hiện không xem được nội dung này", (), p.UNAVAILABLE_NOTE),
    ("Bạn đã đạt giới hạn nội dung đang chờ trong nhóm này.", (), p.PENDING_LIMIT_NOTE),
    ("Mua và bán", (sel.XP_SELL_ONLY_BUTTON,), p.SELL_ONLY_NOTE),
    ("Nhóm bình thường", (), None),
])
def test_group_problem_explains_missing_composer(body, buttons, note):
    assert p.FacebookPoster(PageDriver(body, buttons), CFG)._group_problem() == note


def batch(monkeypatch, outcomes):
    """Chạy post_batch với kết quả đăng giả cho từng nhóm; trả về (results, on_result calls, số lần dọn cửa sổ)"""
    monkeypatch.setattr(p.time, "sleep", lambda s: None)
    poster = p.FacebookPoster(PageDriver(), CFG)
    it = iter(outcomes)
    poster.post_to_group = lambda url, content, image=None: next(it)
    closed, calls = [], []
    poster.close_composer = lambda: closed.append(1)
    groups = [{"group_url": f"https://www.facebook.com/groups/g{i}/", "group_name": f"g{i}"} for i in range(len(outcomes))]
    results = poster.post_batch(groups, "nội dung", on_result=lambda g, ok, note: calls.append(note))
    return results, calls, len(closed)


def test_group_reasons_do_not_count_as_failures(monkeypatch):
    outcomes = [(False, p.NOT_JOINED_NOTE), (False, p.SELL_ONLY_NOTE), (False, p.PENDING_LIMIT_NOTE),
                (False, p.UNAVAILABLE_NOTE), (True, "")]
    results, calls, closed = batch(monkeypatch, outcomes)
    assert results == [{"group": "https://www.facebook.com/groups/g4/", "success": True}]  # vẫn đăng tới nhóm thứ 5
    assert len(calls) == 5 and closed == 0


def test_real_failures_stop_after_three_and_clean_up(monkeypatch):
    fail = (False, "bấm Đăng nhưng cửa sổ không đóng (chưa đăng được)")
    results, calls, closed = batch(monkeypatch, [fail, fail, fail, (True, "")])
    assert len(results) == 3 and not any(r["success"] for r in results)
    assert closed == 3                          # mỗi lần hỏng đều bỏ bản nháp còn mở


def test_posting_skips_expire(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    db.skip_posting("https://www.facebook.com/groups/a/", "a", p.SELL_ONLY_NOTE, hours=24)
    db.skip_posting("https://www.facebook.com/groups/b/", "b", p.PENDING_LIMIT_NOTE, hours=-1)  # đã hết hạn
    assert db.posting_skips() == {"https://www.facebook.com/groups/a/": p.SELL_ONLY_NOTE}
