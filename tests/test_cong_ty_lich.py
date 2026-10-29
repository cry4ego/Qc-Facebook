"""Lịch họp sáng: tới giờ mà hôm nay chưa họp thì họp; bạn bấm "Họp ngay" cũng họp; lỗi một lần không làm dừng vòng lặp."""
from datetime import datetime, timedelta

import pytest

from cong_ty import lich, luu_tru
from modules.db import Database

SANG_6_59 = datetime(2026, 10, 24, 6, 59)    # ngay trước giờ họp
SANG_7 = datetime(2026, 10, 24, 7, 0)
NGAY = "2026-10-24"


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "t.db"))
    luu_tru.ensure_schema(database)
    return database


def ghi_cuoc_hop(db, bat_dau, trang_thai):
    cuoc_id = luu_tru.tao_cuoc_hop(db, NGAY, bat_dau)
    if trang_thai != "dang_hop":
        luu_tru.ket_thuc_cuoc_hop(db, cuoc_id, trang_thai, "", 0, "", "", bat_dau)
    return cuoc_id


def test_waits_before_the_meeting_hour_then_meets(db):
    assert lich.can_hop(db, SANG_6_59, 7) is False
    assert lich.can_hop(db, SANG_7, 7) is True


def test_does_not_meet_twice_in_a_day(db):
    ghi_cuoc_hop(db, SANG_7, "xong")
    assert lich.can_hop(db, SANG_7 + timedelta(hours=5), 7) is False


def test_a_meeting_stuck_in_progress_blocks_only_for_a_while(db):
    ghi_cuoc_hop(db, SANG_7, "dang_hop")
    assert lich.can_hop(db, SANG_7 + timedelta(minutes=5), 7) is False       # vẫn đang họp
    assert lich.can_hop(db, SANG_7 + timedelta(hours=2), 7) is True          # kẹt do máy tắt giữa chừng: họp lại


def test_a_failed_meeting_is_retried_but_not_straight_away(db):
    ghi_cuoc_hop(db, SANG_7, "loi")
    assert lich.can_hop(db, SANG_7 + timedelta(minutes=10), 7) is False     # tránh gọi AI liên tục khi đang hỏng
    assert lich.can_hop(db, SANG_7 + timedelta(minutes=45), 7) is True


def test_after_three_failed_meetings_the_day_is_given_up(db):
    for _ in range(lich.LOI_TOI_DA_MOI_NGAY):
        ghi_cuoc_hop(db, SANG_7, "loi")
    assert lich.can_hop(db, SANG_7 + timedelta(hours=6), 7) is False


def test_owner_request_survives_a_failed_meeting_and_is_cleared_only_after_success(db):
    luu_tru.yeu_cau_hop(db)

    def hong(ep):
        raise RuntimeError("AI sập")
    with pytest.raises(RuntimeError):
        lich.buoc(db, SANG_7, 7, hong)
    assert luu_tru.dang_cho_hop(db) is True
    lich.buoc(db, SANG_7, 7, lambda ep: None)
    assert luu_tru.dang_cho_hop(db) is False


def test_step_meets_on_schedule_and_reports_what_it_did(db):
    lan_hop = []
    assert lich.buoc(db, SANG_6_59, 7, lan_hop.append) == "cho" and lan_hop == []
    assert lich.buoc(db, SANG_7, 7, lan_hop.append) == "hop_theo_lich" and lan_hop == [False]


def test_owner_request_meets_even_before_the_hour_and_is_consumed(db):
    luu_tru.yeu_cau_hop(db)
    assert luu_tru.dang_cho_hop(db) is True
    lan_hop = []
    assert lich.buoc(db, SANG_6_59, 7, lan_hop.append) == "hop_theo_yeu_cau" and lan_hop == [True]
    assert luu_tru.dang_cho_hop(db) is False
    assert lich.buoc(db, SANG_6_59, 7, lan_hop.append) == "cho"


def test_the_loop_survives_a_crashing_meeting_and_backs_off_instead_of_retrying_every_minute(db):
    luu_tru.yeu_cau_hop(db)
    so_lan, da_ngu = [], []

    def hop_hong(ep):
        so_lan.append(ep)
        raise RuntimeError("AI sập")

    lan_lap = iter([False, False, True])
    lich.vong_lap(db, 7, hop_hong, ngu=da_ngu.append, bay_gio=lambda: SANG_7, dung=lambda: next(lan_lap))
    assert so_lan == [True]                                  # vòng 2 nằm trong thời gian nghỉ sau lỗi nên không họp lại
    assert da_ngu == [lich.GIAY_NGHI, lich.GIAY_NGHI]
