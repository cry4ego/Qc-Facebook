"""Báo cáo sáng bằng code: chuỗi số liệu theo ngày, chẩn đoán số bài giảm, xếp hạng nhóm, mẫu bình luận, rủi ro."""
import json
from datetime import date, datetime

import pytest

from cong_ty import bao_cao, khach, so_lieu
from cong_ty_seed import (CFG, HOM_NAY, chuoi_giam, ngay, ngay_binh_thuong, ngay_it_bai, them_bai_thay, them_binh_luan,
                          them_quet)
from modules.db import Database


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "t.db"))
    khach.ensure_schema(database)
    return database


# ---------- chuỗi số liệu theo ngày ----------
def test_series_has_one_row_per_day_and_marks_today(db):
    chuoi = so_lieu.chuoi_ngay(db, 7, HOM_NAY)
    assert [d["ngay"] for d in chuoi] == [ngay(i) for i in range(6, -1, -1)]
    assert chuoi[-1]["chua_het"] and not chuoi[0]["chua_het"]
    assert all(d["bai_thay"] == 0 and d["quet"] == 0 for d in chuoi)


def test_series_counts_every_stage_of_a_day(db):
    day = ngay(2)
    them_quet(db, day, 10, 4)
    them_bai_thay(db, day, 20, 6, 3)
    them_binh_luan(db, day, 3, 7)
    khach.them(db, khach.chuan_hoa(day, "Gọi", 2, hom_nay=HOM_NAY))
    khach.them(db, khach.chuan_hoa(day, "Mua", 1, so_tien=2_500_000, hom_nay=HOM_NAY))
    d = next(x for x in so_lieu.chuoi_ngay(db, 7, HOM_NAY) if x["ngay"] == day)
    assert (d["quet"], d["nhom_quet"], d["bai_thay"], d["bai_mua"], d["dat_loc"]) == (10, 4, 20, 6, 3)
    assert (d["bai_binh_luan"], d["binh_luan_gui"]) == (3, 7)
    assert (d["goi"], d["nhan"], d["mua"], d["so_tien"]) == (2, 0, 1, 2_500_000)


# ---------- chẩn đoán số bài giảm ----------
def test_diagnosis_blames_fewer_buyer_posts_when_the_bot_scans_as_before(db):
    cd = bao_cao.chan_doan(chuoi_giam(db))
    assert cd["trang_thai"] == "giam" and 50 <= cd["giam_pct"] <= 60
    assert cd["goc"] == "bai_thay" and "quet" not in cd["giam"]
    assert {"bai_thay", "bai_mua"} <= set(cd["giam"])
    assert any("900" in cau for cau in cd["cau"])


def test_diagnosis_blames_the_bot_when_scans_collapse(db):
    for truoc in range(10, 3, -1):
        ngay_binh_thuong(db, truoc)
    for truoc in (3, 2, 1):
        day = ngay(truoc)
        them_quet(db, day, 100, 10)
        them_bai_thay(db, day, 160, 6, 4)
        them_binh_luan(db, day, 4, 8)
    cd = bao_cao.chan_doan(so_lieu.chuoi_ngay(db, 14, HOM_NAY))
    assert cd["trang_thai"] == "giam" and cd["goc"] == "quet"


def test_diagnosis_blames_the_filters_when_buyers_are_there_but_fewer_pass(db):
    for truoc in range(10, 3, -1):
        ngay_binh_thuong(db, truoc)
    for truoc in (3, 2, 1):
        day = ngay(truoc)
        them_quet(db, day, 900, 57)
        them_bai_thay(db, day, 1500, 60, 12)
        them_binh_luan(db, day, 11, 22)
    cd = bao_cao.chan_doan(so_lieu.chuoi_ngay(db, 14, HOM_NAY))
    assert cd["trang_thai"] == "giam" and cd["goc"] == "ty_le_dat" and "bai_thay" not in cd["giam"]


def test_diagnosis_is_stable_when_volume_holds(db):
    for truoc in range(10, 0, -1):
        ngay_binh_thuong(db, truoc)
    cd = bao_cao.chan_doan(so_lieu.chuoi_ngay(db, 14, HOM_NAY))
    assert cd["trang_thai"] == "on_dinh" and cd["goc"] is None


def test_diagnosis_needs_enough_history(db):
    ngay_binh_thuong(db, 1)
    assert bao_cao.chan_doan(so_lieu.chuoi_ngay(db, 14, HOM_NAY))["trang_thai"] == "thieu_so_lieu"


def test_diagnosis_lists_days_the_bot_did_not_scan_but_not_days_before_it_started(db):
    for truoc in (10, 9, 8, 3, 2, 1):
        ngay_binh_thuong(db, truoc)
    cd = bao_cao.chan_doan(so_lieu.chuoi_ngay(db, 14, HOM_NAY))
    assert cd["ngung"] == [ngay(7), ngay(6), ngay(5), ngay(4)]
    assert cd["trang_thai"] == "on_dinh"


# ---------- nhóm ----------
def test_groups_are_ranked_by_customers_then_buyer_posts(db):
    day = ngay(1)
    them_quet(db, day, 3, 3)
    them_bai_thay(db, day, 5, 3, 2, nhom=0)
    them_bai_thay(db, day, 5, 4, 4, nhom=1)
    them_bai_thay(db, day, 5, 1, 0, nhom=2)
    khach.them(db, khach.chuan_hoa(day, "Gọi", 1, nguon="Nhóm 2", hom_nay=HOM_NAY))
    rows = so_lieu.xep_hang_nhom(db, 7, HOM_NAY)
    assert [r["ten"] for r in rows] == ["Nhóm 2", "Nhóm 1", "Nhóm 0"]
    assert rows[0]["khach"] == 1 and rows[1]["dat_loc"] == 4 and rows[2]["quet"] == 1


def test_wasteful_groups_are_scanned_often_without_a_single_qualified_post():
    rows = [{"ten": "A", "quet": 50, "dat_loc": 0}, {"ten": "B", "quet": 50, "dat_loc": 2},
            {"ten": "C", "quet": 5, "dat_loc": 0}]
    assert [r["ten"] for r in bao_cao.nhom_vo_ich(rows, 30)] == ["A"]


def test_skip_reasons_of_buyer_posts_are_grouped_and_ignore_other_posts(db):
    day = ngay(1)
    them_bai_thay(db, day, 4, 4, 0, ly_do="khách ở xa (HCM) — chỉ bình luận khách Hà Nội")
    them_bai_thay(db, day, 2, 2, 0, ly_do="khách ở xa (hà tĩnh) — chỉ bình luận khách Hà Nội")
    them_bai_thay(db, day, 3, 1, 0, ly_do="không lấy được link bài viết")
    assert so_lieu.ly_do_bo_qua_bai_mua(db, 7, HOM_NAY) == [
        {"ly_do": "khách ở xa", "so_bai": 6}, {"ly_do": "không lấy được link bài viết", "so_bai": 1}]


# ---------- mẫu bình luận ----------
def test_variant_stats_count_sent_rejected_and_lost_posts(db):
    pid = db.add_product(name="MSI G274QPF", price="2.500.000đ")
    vid = db.add_variant(pid, "Màn MSI giá 2.500.000đ", "")
    day = ngay(1)
    them_binh_luan(db, day, 3, 3, variant_id=vid)
    them_binh_luan(db, day, 1, 1, variant_id=vid, tt_binh_luan="Bị từ chối · đã xóa")
    them_binh_luan(db, day, 1, 1, variant_id=vid, tt_binh_luan="Bị chặn")
    them_binh_luan(db, day, 1, 2, variant_id=vid, verify="Không thấy bình luận")
    r = next(x for x in so_lieu.mau_binh_luan(db, 7, HOM_NAY) if x["id"] == vid)
    assert (r["san_pham"], r["da_gui"], r["bi_tu_choi"], r["bai_mat"]) == ("MSI G274QPF", 5, 2, 1)


# ---------- rủi ro ----------
def test_risk_signals(db):
    db.set_setting("safe_all", "1")
    db.set_setting("safe_all_reason", "2026-10-05 19:15:31 — Facebook báo bị chặn bình luận")
    db.set_setting("blocked_until", "2026-10-25 01:00:00")
    them_binh_luan(db, ngay(0), 3, 3)
    them_binh_luan(db, ngay(2), 1, 1, tt_binh_luan="Bị chặn")
    rui = so_lieu.rui_ro(db, 40, HOM_NAY, 7)
    assert rui["safe_all"] and "chặn" in rui["safe_all_ly_do"]
    assert (rui["bi_chan"], rui["bai_hom_nay"], rui["tran"]) == (1, 3, 40)
    assert rui["chan_den"] == "2026-10-25 01:00:00"


def test_old_block_and_default_settings_are_not_a_risk(db):
    db.set_setting("blocked_until", "2026-10-06 01:15:32")
    rui = so_lieu.rui_ro(db, 40, HOM_NAY, 7)
    assert rui["chan_den"] is None and rui["safe_all"] is False and rui["bi_chan"] == 0


# ---------- báo cáo đầy đủ ----------
def tao(db, tmp_path, noi_dung_su_that=None, hom_nay=HOM_NAY, bay_gio=None):
    path = tmp_path / "su-that.md"
    if noi_dung_su_that is not None:
        path.write_text(noi_dung_su_that, encoding="utf-8")
    return bao_cao.tao_bao_cao(db, CFG, str(path), hom_nay, bay_gio=bay_gio)


def nhan_xet(bc, muc=None):
    return [n["noi_dung"] for n in bc["nhan_xet"] if muc in (None, n["muc"])]


def test_report_on_an_empty_database_does_not_crash(db, tmp_path):
    bc = tao(db, tmp_path)
    assert bc["chan_doan"]["trang_thai"] == "thieu_so_lieu" and bc["van_ban"]


def test_report_has_every_section_and_is_json_serialisable(db, tmp_path):
    chuoi_giam(db)
    bc = tao(db, tmp_path)
    assert set(bc) >= {"hom_nay", "chuoi", "pheu", "chan_doan", "nhom", "vo_ich", "ly_do_bo_qua", "mau", "rui_ro",
                       "khach", "su_that", "nhan_xet", "van_ban"}
    assert bc["hom_nay"] == "2026-10-24" and "PHỄU" in bc["van_ban"]
    json.dumps(bc)


def test_report_tells_the_owner_when_there_is_no_customer_data(db, tmp_path):
    assert any("khách" in n for n in nhan_xet(tao(db, tmp_path), "chu_y"))
    khach.them(db, khach.chuan_hoa(ngay(1), "Gọi", 1, hom_nay=HOM_NAY))
    assert not any("chưa có số liệu khách" in n.lower() for n in nhan_xet(tao(db, tmp_path)))


def test_report_flags_the_no_phone_mode(db, tmp_path):
    db.set_setting("safe_all", "1")
    db.set_setting("safe_all_reason", "2026-10-05 19:15:31 — Facebook báo bị chặn bình luận")
    assert any("SĐT" in n for n in nhan_xet(tao(db, tmp_path), "chu_y"))


def test_report_flags_more_comments_per_post(db, tmp_path):
    for truoc in range(10, 3, -1):
        ngay_binh_thuong(db, truoc)
    for truoc in (3, 2, 1):
        day = ngay(truoc)
        them_quet(db, day, 900, 57)
        them_bai_thay(db, day, 1500, 60, 35)
        them_binh_luan(db, day, 15, 75)
    assert any("mỗi bài" in n for n in nhan_xet(tao(db, tmp_path), "chu_y"))


def test_report_lists_prices_missing_from_products_and_the_fact_sheet(db, tmp_path):
    pid = db.add_product(name="MSI G274QPX", price="2.750.000đ")
    db.add_variant(pid, "Giá 2.750.000đ không chân, 2.900.000đ có chân. Gọi 0902 189 751", "")
    so_that_md = "## Thông tin cửa hàng\nSố điện thoại: 0902 189 751\n"
    mau = tao(db, tmp_path, so_that_md)["mau"]
    assert mau["gia_la"] == [{"gia": 2_900_000, "so_mau": 1}] and mau["so_mau_lech"] == 1
    mau = tao(db, tmp_path, so_that_md + "## Giá được phép nhắc thêm\n- 2.900.000đ\n")["mau"]
    assert mau["so_mau_lech"] == 0 and mau["gia_la"] == []


def test_report_lists_unfilled_fact_sheet_fields(db, tmp_path):
    bc = tao(db, tmp_path, "## Thông tin cửa hàng\nĐịa chỉ: 64 Cầu Diễn, Hà Nội\n")
    assert "Địa chỉ" not in bc["su_that"]["chua_dien"] and "Bảo hành" in bc["su_that"]["chua_dien"]
    assert any("Sổ sự thật" in n for n in nhan_xet(bc))


def test_report_does_not_change_the_database(db, tmp_path):
    chuoi_giam(db)
    truoc = db.query("SELECT (SELECT COUNT(*) FROM posts) p, (SELECT COUNT(*) FROM comments) c, "
                     "(SELECT COUNT(*) FROM post_decisions) d")
    tao(db, tmp_path)
    assert db.query("SELECT (SELECT COUNT(*) FROM posts) p, (SELECT COUNT(*) FROM comments) c, "
                    "(SELECT COUNT(*) FROM post_decisions) d") == truoc


def test_save_writes_one_dated_file_per_day(db, tmp_path):
    bc = tao(db, tmp_path)
    path = bao_cao.luu(bc, str(tmp_path / "bao_cao"))
    assert path.endswith("2026-10-24.md")
    with open(path, encoding="utf-8") as f:
        assert f.read() == bc["van_ban"]


# ---------- báo cáo của ngày đã qua ----------
def test_past_date_report_ignores_data_from_later_days(db, tmp_path):
    day = ngay(0)
    them_quet(db, day, 10, 4)
    them_bai_thay(db, day, 20, 6, 3, ly_do="khách ở xa")
    them_binh_luan(db, day, 3, 3, tt_binh_luan="Bị chặn")
    khach.them(db, khach.chuan_hoa(day, "Gọi", 5, nguon="Nhóm 0", hom_nay=HOM_NAY))
    bc = tao(db, tmp_path, hom_nay=date(2026, 10, 20), bay_gio=datetime(2026, 10, 24, 9, 0))
    assert bc["khach"]["tong"] == {"goi": 0, "nhan": 0, "mua": 0, "so_tien": 0}
    assert (bc["pheu"]["bai_thay"], bc["pheu"]["bai_binh_luan"]) == (0, 0)
    assert bc["nhom"] == [] and bc["ly_do_bo_qua"] == [] and bc["rui_ro"]["bi_chan"] == 0
    assert bc["chuoi"][-1]["ngay"] == "2026-10-20" and not bc["chuoi"][-1]["chua_het"]


def test_day_counts_as_complete_once_real_time_has_passed_it(db):
    sang_24 = datetime(2026, 10, 24, 9, 0)
    assert so_lieu.chuoi_ngay(db, 7, date(2026, 10, 20), bay_gio=sang_24)[-1]["chua_het"] is False
    assert so_lieu.chuoi_ngay(db, 7, HOM_NAY, bay_gio=sang_24)[-1]["chua_het"] is True


def test_block_warning_ends_when_the_cooldown_ends(db):
    db.set_setting("blocked_until", "2026-10-24 06:00:00")
    assert so_lieu.rui_ro(db, 40, HOM_NAY, 7, bay_gio=datetime(2026, 10, 24, 5, 0))["chan_den"] == "2026-10-24 06:00:00"
    assert so_lieu.rui_ro(db, 40, HOM_NAY, 7, bay_gio=datetime(2026, 10, 24, 9, 0))["chan_den"] is None


def test_current_state_is_not_reported_for_days_before_it_began(db):
    db.set_setting("safe_all", "1")
    db.set_setting("safe_all_reason", "2026-10-05 19:15:31 — Facebook báo bị chặn bình luận")
    assert so_lieu.rui_ro(db, 40, date(2026, 10, 1), 7)["safe_all"] is False
    assert so_lieu.rui_ro(db, 40, HOM_NAY, 7)["safe_all"] is True
    db.set_setting("blocked_until", "2026-10-25 01:00:00")
    hom_qua = so_lieu.rui_ro(db, 40, date(2026, 10, 20), 7, bay_gio=datetime(2026, 10, 24, 9, 0))
    assert hom_qua["chan_den"] is None


def test_report_refuses_dates_before_the_year_2000(db, tmp_path):
    with pytest.raises(ValueError, match="(?i)ngày"):
        tao(db, tmp_path, hom_nay=date(1999, 12, 31))


# ---------- sửa lỗi sau khi soát code ----------
def test_templates_mostly_rejected_are_flagged_even_with_few_accepted(db, tmp_path):
    pid = db.add_product(name="MSI G274QPF", price="2.500.000đ")
    nhieu_loi = db.add_variant(pid, "Mẫu A", "")
    toan_loi = db.add_variant(pid, "Mẫu B", "")
    day = ngay(1)
    them_binh_luan(db, day, 5, 5, variant_id=nhieu_loi)
    them_binh_luan(db, day, 40, 40, variant_id=nhieu_loi, tt_binh_luan="Bị từ chối · đã xóa")
    them_binh_luan(db, day, 25, 25, variant_id=toan_loi, tt_binh_luan="Bị chặn")
    ghi = " ".join(nhan_xet(tao(db, tmp_path), "chu_y"))
    assert "hay bị chặn" in ghi and f"#{nhieu_loi}" in ghi and f"#{toan_loi}" in ghi


def test_two_groups_with_the_same_name_do_not_double_count_customers(db):
    day = ngay(1)
    them_quet(db, day, 2, 2)
    them_bai_thay(db, day, 5, 3, 2, nhom=0)
    them_bai_thay(db, day, 5, 4, 4, nhom=1)
    db.execute("UPDATE post_decisions SET group_name = 'Trùng tên'")
    khach.them(db, khach.chuan_hoa(day, "Gọi", 1, nguon="Trùng tên", hom_nay=HOM_NAY))
    rows = so_lieu.xep_hang_nhom(db, 7, HOM_NAY)
    assert [r["khach"] for r in rows] == [1, 0] and rows[0]["dat_loc"] == 4
