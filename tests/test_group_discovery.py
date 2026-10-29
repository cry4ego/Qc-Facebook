"""Lịch tìm nhóm mới + cửa sổ KHÁM PHÁ chạy ngầm: tìm đúng giờ; tìm hỏng (phiên Facebook hết hạn → mọi từ khóa trả rỗng, hoặc lỗi) thì
nghỉ 1 giờ rồi thử lại chứ không đập liên tục vào Facebook; nhịp tim chỉ báo "còn sống" khi việc tìm thật sự chạy."""
import logging
from datetime import datetime, timedelta

import pytest

from modules import group_discovery as gd
from modules.db import Database

BAY_GIO = datetime(2026, 10, 25, 9, 0)
LOG = logging.getLogger("test")
TOT = {"truy_van": 3, "loi": 0, "co_ket_qua": 3}


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


class Tim:
    """find giả: ghi lại lời gọi, điền stats như find_groups thật"""

    def __init__(self, them=2, stats=TOT, loi=None):
        self.them, self.stats, self.loi, self.goi = them, stats, loi, []

    def __call__(self, driver, known, extra, stats, on_query):
        self.goi.append((driver, known, extra, on_query))
        if self.loi:
            raise self.loi
        stats.update(self.stats)
        return self.them


def chay(db, tim, bay_gio=BAY_GIO, **kw):
    kw.setdefault("known_fn", lambda: ["u1"])
    kw.setdefault("extra_fn", lambda: ["tu khoa them"])
    return gd.chay_tim(db, LOG, "driver", tim, every_hours=6, bay_gio=bay_gio, **kw)


def test_the_first_run_searches_and_remembers_when(db):
    tim = Tim()
    assert chay(db, tim) is True
    assert tim.goi == [("driver", ["u1"], ["tu khoa them"], None)]
    assert db.get_setting("groups_searched_at") == "2026-10-25 09:00:00"


def test_it_waits_for_the_next_slot_and_force_overrides_the_schedule(db):
    tim = Tim()
    chay(db, tim)
    assert chay(db, tim, BAY_GIO + timedelta(hours=5, minutes=59)) is None and len(tim.goi) == 1
    assert chay(db, tim, BAY_GIO + timedelta(hours=6)) is True and len(tim.goi) == 2
    assert chay(db, tim, BAY_GIO + timedelta(hours=6, minutes=5), force=True) is True and len(tim.goi) == 3


@pytest.mark.parametrize("hong", [
    Tim(stats={"truy_van": 3, "loi": 0, "co_ket_qua": 0}),                  # phiên Facebook hết hạn: mọi từ khóa trả rỗng
    Tim(stats={"truy_van": 3, "loi": 3, "co_ket_qua": 0}),                  # mọi từ khóa đều lỗi
    Tim(loi=RuntimeError("Chrome đã đóng")),                               # lỗi bất ngờ
])
def test_a_failed_search_retries_after_an_hour_not_at_once_and_not_after_a_full_day(db, hong):
    assert chay(db, hong) is False
    assert chay(db, hong, BAY_GIO + timedelta(minutes=30)) is None and len(hong.goi) == 1
    assert chay(db, hong, BAY_GIO + timedelta(minutes=61)) is False and len(hong.goi) == 2      # thử lại sau ~1 giờ


def test_some_failing_queries_are_fine_as_long_as_others_returned_results(db):
    tim = Tim(stats={"truy_van": 4, "loi": 2, "co_ket_qua": 2})
    assert chay(db, tim) is True and db.get_setting("groups_searched_at") == "2026-10-25 09:00:00"


def test_a_find_function_that_reports_nothing_counts_as_fine(db):
    assert chay(db, Tim(stats={})) is True


def test_extra_keywords_that_cannot_be_read_do_not_stop_the_search(db):
    def hong():
        raise RuntimeError("công ty AI hỏng")

    tim = Tim()
    assert chay(db, tim, extra_fn=hong) is True and tim.goi[0][2] == []


def test_a_failing_known_urls_reader_is_a_failed_search_not_a_crash(db):
    def hong():
        raise OSError("file Excel đang mở")

    tim = Tim()
    assert chay(db, tim, known_fn=hong) is False and tim.goi == []


def test_progress_and_on_query_are_passed_through(db):
    tien_trinh, nhip = [], lambda: None
    tim = Tim()
    chay(db, tim, progress=lambda **f: tien_trinh.append(f), on_query=nhip)
    assert tien_trinh and "phase" in tien_trinh[0] and tim.goi[0][3] is nhip


def test_a_damaged_timestamp_means_it_is_due(db):
    db.set_setting("groups_searched_at", "không phải ngày")
    assert chay(db, Tim()) is True


# ---------- nhịp tim của cửa sổ khám phá ----------
def test_the_heartbeat_says_alive_only_while_it_is_fresh(db):
    assert gd.con_song(db, BAY_GIO) is False
    gd.nhip(db, BAY_GIO)
    assert gd.con_song(db, BAY_GIO + timedelta(minutes=29)) is True
    assert gd.con_song(db, BAY_GIO + timedelta(minutes=31)) is False


@pytest.mark.parametrize("hong", ["", "không phải ngày", "2026-13-45 99:99:99"])
def test_a_damaged_heartbeat_means_not_alive(db, hong):
    db.set_setting(gd.NHIP_SETTING, hong)
    assert gd.con_song(db, BAY_GIO) is False
