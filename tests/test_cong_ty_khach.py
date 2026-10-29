"""Sổ ghi khách: kiểm tra dữ liệu nhập, cộng theo ngày và theo nguồn."""
from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from cong_ty import khach
from modules.db import Database

HOM_NAY = date(2026, 10, 24)


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "t.db"))
    khach.ensure_schema(database)
    return database


def nhap(**kw):
    return khach.chuan_hoa(**{"ngay": "2026-10-24", "loai": "Gọi", "hom_nay": HOM_NAY, **kw})


def test_valid_entry_is_normalised():
    k = nhap(so_luong="2", nguon="  Chợ màn hình HN  ", so_tien="2500000", ghi_chu=" khách gọi tối ")
    assert (k.so_luong, k.nguon, k.so_tien, k.ghi_chu) == (2, "Chợ màn hình HN", 2_500_000, "khách gọi tối")


def test_defaults_are_one_customer_and_no_money():
    k = nhap(so_tien="")
    assert (k.so_luong, k.so_tien, k.nguon, k.san_pham) == (1, None, "", "")


@pytest.mark.parametrize("kw, loi", [
    ({"loai": "Hỏi giá"}, "loại"),
    ({"so_luong": 0}, "số lượng"),
    ({"so_luong": "abc"}, "số lượng"),
    ({"so_luong": 501}, "số lượng"),
    ({"ngay": "24/10/2026"}, "ngày"),
    ({"ngay": "2026-10-25"}, "tương lai"),
    ({"so_tien": -1}, "số tiền"),
    ({"so_tien": "abc"}, "số tiền"),
    ({"nguon": "x" * 201}, "nguồn"),
    ({"ghi_chu": "x" * 501}, "ghi chú"),
])
def test_invalid_entries_are_rejected_with_a_vietnamese_reason(kw, loi):
    with pytest.raises(ValueError, match=f"(?i){loi}"):
        nhap(**kw)


def test_entry_cannot_be_changed_after_validation():
    with pytest.raises(FrozenInstanceError):
        nhap().loai = "Mua"


def test_totals_by_day_sum_quantities_and_money(db):
    khach.them(db, nhap(ngay="2026-10-23", loai="Gọi", so_luong=2))
    khach.them(db, nhap(ngay="2026-10-23", loai="Mua", so_tien=2_500_000))
    khach.them(db, nhap(ngay="2026-10-24", loai="Nhắn", so_luong=3))
    tong = khach.tong_theo_ngay(db, "2026-10-01")
    assert tong["2026-10-23"] == {"Gọi": 2, "Nhắn": 0, "Mua": 1, "so_tien": 2_500_000}
    assert tong["2026-10-24"] == {"Gọi": 0, "Nhắn": 3, "Mua": 0, "so_tien": 0}


def test_totals_ignore_days_before_the_start(db):
    khach.them(db, nhap(ngay="2026-09-01"))
    assert khach.tong_theo_ngay(db, "2026-10-01") == {}


def test_totals_by_source_group_blank_source_as_unknown(db):
    khach.them(db, nhap(nguon="Nhóm A", loai="Gọi"))
    khach.them(db, nhap(nguon="Nhóm A", loai="Mua"))
    khach.them(db, nhap(nguon="", loai="Nhắn", so_luong=4))
    tong = khach.tong_theo_nguon(db, "2026-10-01")
    assert tong["Nhóm A"] == {"Gọi": 1, "Nhắn": 0, "Mua": 1, "so_tien": 0}
    assert tong["Không rõ"]["Nhắn"] == 4


def test_list_newest_first_and_delete(db):
    cu = khach.them(db, nhap(ngay="2026-10-22"))
    moi = khach.them(db, nhap(ngay="2026-10-24"))
    assert [r["id"] for r in khach.liet_ke(db, "2026-10-01")] == [moi, cu]
    assert khach.xoa(db, cu) is True
    assert khach.xoa(db, cu) is False


def test_totals_can_stop_before_a_given_day(db):
    khach.them(db, nhap(ngay="2026-10-23"))
    khach.them(db, nhap(ngay="2026-10-24"))
    assert list(khach.tong_theo_ngay(db, "2026-10-01", "2026-10-24")) == ["2026-10-23"]
    assert list(khach.tong_theo_nguon(db, "2026-10-01", "2026-10-24")) == ["Không rõ"]


def test_deleting_an_impossible_id_is_just_not_found(db):
    assert khach.xoa(db, 10 ** 30) is False
    assert khach.xoa(db, 0) is False


def test_schema_can_be_created_twice(db):
    khach.ensure_schema(db)
    assert khach.liet_ke(db, "2026-10-01") == []
