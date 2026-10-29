"""Hành động đầu tiên của công ty: tắt mẫu bình luận hay bị chặn — chỉ việc do luật đề xuất, có giới hạn cứng, nhật ký, hoàn tác."""
import json
from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from cong_ty import de_xuat, hanh_dong, luu_tru, mau_ai, nhom_ai
from modules.db import Database

BAY_GIO = datetime(2026, 10, 24, 7, 30)


def them_de_xuat(db, tham_so_chu, nguon="luat", trang_thai=luu_tru.CHO_DUYET):
    """Tạo một đề xuất (kèm tham số hành động) trong CSDL thử; trả về id"""
    luu_tru.ensure_schema(db)
    dx = replace(de_xuat.chuan_hoa("noi_dung", {"loai": "bat_tat_mau", "tieu_de": "Tắt mẫu hay bị chặn", "noi_dung": "Tắt vài mẫu",
                                               "vi_sao": "3 mẫu bị chặn 25 lần"}, date(2026, 10, 24)), tham_so=tham_so_chu)
    cuoc = luu_tru.tao_cuoc_hop(db, "2026-10-24", BAY_GIO)
    return luu_tru.them_de_xuat(db, cuoc, dx, nguon, trang_thai, "", BAY_GIO)


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "t.db"))
    hanh_dong.ensure_schema(database)
    return database


def them_mau(db, so_mau, so_san_pham=1):
    """Tạo `so_mau` mẫu đang bật chia đều cho `so_san_pham` sản phẩm; trả về (id sản phẩm, id mẫu)"""
    san_pham = [db.add_product(name=f"MSI {i}", price="2.500.000đ") for i in range(so_san_pham)]
    return san_pham, [db.add_variant(san_pham[i % so_san_pham], f"Mẫu {i}", "") for i in range(so_mau)]


def tham_so(*ids, ten="tat_mau"):
    return json.dumps({"hanh_dong": ten, "variant_ids": list(ids)})


def dang_bat(db):
    return {v["id"] for v in db.variants(active_only=True)}


def test_turning_off_variants_changes_only_those_and_writes_a_log_entry(db):
    _, ids = them_mau(db, 20, 2)
    nhat_ky_id = hanh_dong.thuc_hien(db, 7, tham_so(ids[0], ids[1]), "luat", BAY_GIO)
    assert dang_bat(db) == set(ids) - {ids[0], ids[1]}
    dong = hanh_dong.liet_ke(db)[0]
    assert (dong["id"], dong["hanh_dong"], dong["de_xuat_id"], dong["hoan_tac_luc"]) == (nhat_ky_id, "tat_mau", 7, None)
    assert json.loads(dong["doi_tuong"])["variant_ids"] == [ids[0], ids[1]] and dong["luc"] == "2026-10-24 07:30:00"


def test_undo_turns_the_variants_back_on_once(db):
    _, ids = them_mau(db, 20)
    nhat_ky_id = hanh_dong.thuc_hien(db, 7, tham_so(ids[0]), "luat", BAY_GIO)
    hanh_dong.hoan_tac(db, nhat_ky_id, BAY_GIO)
    assert dang_bat(db) == set(ids) and hanh_dong.liet_ke(db)[0]["hoan_tac_luc"] == "2026-10-24 07:30:00"
    with pytest.raises(ValueError):
        hanh_dong.hoan_tac(db, nhat_ky_id, BAY_GIO)
    with pytest.raises(LookupError):
        hanh_dong.hoan_tac(db, 999_999, BAY_GIO)
    with pytest.raises(LookupError):
        hanh_dong.hoan_tac(db, 10 ** 30, BAY_GIO)


def test_only_proposals_written_by_rules_may_be_carried_out(db):
    _, ids = them_mau(db, 20)
    with pytest.raises(hanh_dong.KhongLamDuoc, match="luật"):
        hanh_dong.thuc_hien(db, 7, tham_so(ids[0]), "ai", BAY_GIO)
    assert dang_bat(db) == set(ids)


@pytest.mark.parametrize("tho", [
    "", "không phải json", "[1, 2]", json.dumps({"hanh_dong": "xoa_csdl", "variant_ids": [1]}),
    json.dumps({"hanh_dong": "tat_mau"}), json.dumps({"hanh_dong": "tat_mau", "variant_ids": []}),
    json.dumps({"hanh_dong": "tat_mau", "variant_ids": ["a"]}), json.dumps({"hanh_dong": "tat_mau", "variant_ids": [1.5]}),
    json.dumps({"hanh_dong": "tat_mau", "variant_ids": [True]}), json.dumps({"hanh_dong": "tat_mau", "variant_ids": [0]}),
    json.dumps({"hanh_dong": "tat_mau", "variant_ids": [10 ** 30]}),
    json.dumps({"hanh_dong": "tat_mau", "variant_ids": [1, 2, 3, 4, 5, 6]}),
])
def test_malformed_or_unknown_actions_are_refused(db, tho):
    them_mau(db, 20)
    with pytest.raises(hanh_dong.KhongLamDuoc):
        hanh_dong.thuc_hien(db, 7, tho, "luat", BAY_GIO)
    assert len(dang_bat(db)) == 20


def test_unknown_variant_cancels_the_whole_action(db):
    _, ids = them_mau(db, 20)
    with pytest.raises(hanh_dong.KhongLamDuoc, match="99999"):
        hanh_dong.thuc_hien(db, 7, tham_so(ids[0], 99999), "luat", BAY_GIO)
    assert dang_bat(db) == set(ids)


def test_variants_already_off_are_not_turned_off_twice(db):
    _, ids = them_mau(db, 20)
    hanh_dong.thuc_hien(db, 7, tham_so(ids[0]), "luat", BAY_GIO)
    with pytest.raises(hanh_dong.KhongLamDuoc, match="đã tắt"):
        hanh_dong.thuc_hien(db, 8, tham_so(ids[0]), "luat", BAY_GIO)


def test_at_most_five_variants_are_turned_off_per_day_and_undo_frees_the_quota(db):
    _, ids = them_mau(db, 30)
    nhat_ky = [hanh_dong.thuc_hien(db, 7, tham_so(i), "luat", BAY_GIO) for i in ids[:5]]
    with pytest.raises(hanh_dong.KhongLamDuoc, match="(?i)hôm nay"):
        hanh_dong.thuc_hien(db, 7, tham_so(ids[5]), "luat", BAY_GIO)
    hanh_dong.thuc_hien(db, 7, tham_so(ids[5]), "luat", BAY_GIO + timedelta(days=1))     # sang ngày mới
    hanh_dong.hoan_tac(db, nhat_ky[0], BAY_GIO)
    hanh_dong.thuc_hien(db, 7, tham_so(ids[6]), "luat", BAY_GIO)                          # hoàn tác trả lại 1 suất


def test_the_shop_always_keeps_at_least_ten_variants_on(db):
    _, ids = them_mau(db, 11)
    with pytest.raises(hanh_dong.KhongLamDuoc, match="10"):
        hanh_dong.thuc_hien(db, 7, tham_so(ids[0], ids[1]), "luat", BAY_GIO)
    hanh_dong.thuc_hien(db, 7, tham_so(ids[0]), "luat", BAY_GIO)
    assert len(dang_bat(db)) == 10


def test_every_product_keeps_at_least_one_variant_on(db):
    mot_mau = db.add_product(name="MSI A", price="2.500.000đ")
    lon = db.add_product(name="MSI B", price="2.500.000đ")
    mau_duy_nhat = db.add_variant(mot_mau, "Mẫu duy nhất", "")
    for i in range(15):
        db.add_variant(lon, f"Mẫu {i}", "")
    with pytest.raises(hanh_dong.KhongLamDuoc, match="sản phẩm"):
        hanh_dong.thuc_hien(db, 7, tham_so(mau_duy_nhat), "luat", BAY_GIO)
    assert mau_duy_nhat in dang_bat(db)


def test_do_it_now_approves_then_carries_out_and_marks_the_proposal_done(db):
    _, ids = them_mau(db, 20)
    de_xuat_id = them_de_xuat(db, tham_so(ids[0], ids[1]))
    kq = hanh_dong.lam_luon(db, de_xuat_id, "ok", BAY_GIO)
    assert kq["da_lam"] is True and dang_bat(db) == set(ids) - {ids[0], ids[1]}
    dong = luu_tru.liet_ke_de_xuat(db)[0]
    assert dong["trang_thai"] == "da_lam" and f"#{kq['nhat_ky_id']}" in dong["ghi_chu_chu_shop"]
    assert "ok" in dong["ghi_chu_chu_shop"]


def test_do_it_now_also_works_on_a_proposal_the_owner_already_approved(db):
    _, ids = them_mau(db, 20)
    de_xuat_id = them_de_xuat(db, tham_so(ids[0]))
    luu_tru.quyet_dinh(db, de_xuat_id, "da_duyet", "", BAY_GIO)
    assert hanh_dong.lam_luon(db, de_xuat_id, "", BAY_GIO)["da_lam"] is True
    assert luu_tru.liet_ke_de_xuat(db)[0]["trang_thai"] == "da_lam"


def test_do_it_now_refuses_without_changing_anything_when_a_limit_would_be_broken(db):
    _, ids = them_mau(db, 11)
    de_xuat_id = them_de_xuat(db, tham_so(ids[0], ids[1]))
    with pytest.raises(hanh_dong.KhongLamDuoc):
        hanh_dong.lam_luon(db, de_xuat_id, "", BAY_GIO)
    assert len(dang_bat(db)) == 11 and luu_tru.liet_ke_de_xuat(db)[0]["trang_thai"] == "cho_duyet"
    assert hanh_dong.liet_ke(db) == []


def test_do_it_now_needs_a_structured_action_written_by_rules(db):
    _, ids = them_mau(db, 20)
    with pytest.raises(hanh_dong.KhongLamDuoc, match="tay"):
        hanh_dong.lam_luon(db, them_de_xuat(db, ""), "", BAY_GIO)
    with pytest.raises(hanh_dong.KhongLamDuoc, match="luật"):
        hanh_dong.lam_luon(db, them_de_xuat(db, tham_so(ids[0]), nguon="ai"), "", BAY_GIO)
    assert dang_bat(db) == set(ids)


def test_do_it_now_only_works_on_open_proposals(db):
    _, ids = them_mau(db, 20)
    with pytest.raises(ValueError):
        hanh_dong.lam_luon(db, them_de_xuat(db, tham_so(ids[0]), trang_thai=luu_tru.BI_CHAN), "", BAY_GIO)
    with pytest.raises(LookupError):
        hanh_dong.lam_luon(db, 999_999, "", BAY_GIO)
    xong = them_de_xuat(db, tham_so(ids[1]))
    hanh_dong.lam_luon(db, xong, "", BAY_GIO)
    with pytest.raises(ValueError):
        hanh_dong.lam_luon(db, xong, "", BAY_GIO)


def test_on_its_own_the_company_leaves_variants_the_owner_recently_undid_to_the_owner(db):
    _, ids = them_mau(db, 20)
    hanh_dong.hoan_tac(db, hanh_dong.thuc_hien(db, 7, tham_so(ids[0]), "luat", BAY_GIO), BAY_GIO)
    moi = them_de_xuat(db, tham_so(ids[0]))
    sau_10_ngay = BAY_GIO + timedelta(days=10)
    with pytest.raises(hanh_dong.KhongLamDuoc, match="hoàn tác"):
        hanh_dong.lam_luon(db, moi, "", sau_10_ngay, tu_dong=True)
    assert dang_bat(db) == set(ids) and luu_tru.liet_ke_de_xuat(db)[0]["trang_thai"] == "cho_duyet"
    hanh_dong.lam_luon(db, moi, "", sau_10_ngay)                       # chủ shop tự bấm "làm luôn" thì vẫn được
    assert ids[0] not in dang_bat(db)


def test_on_its_own_the_company_may_act_again_after_the_cooling_off_period(db):
    _, ids = them_mau(db, 20)
    hanh_dong.hoan_tac(db, hanh_dong.thuc_hien(db, 7, tham_so(ids[0]), "luat", BAY_GIO), BAY_GIO)
    het_nghi = BAY_GIO + timedelta(days=hanh_dong.NGAY_NGHI_SAU_HOAN_TAC + 1)
    assert hanh_dong.lam_luon(db, them_de_xuat(db, tham_so(ids[0])), "", het_nghi, tu_dong=True)["da_lam"] is True


def test_the_log_entry_is_written_before_any_variant_is_changed(db, monkeypatch):
    _, ids = them_mau(db, 20)
    tat = db.update_variant

    def hong_giua_chung(variant_id, **kw):
        tat(variant_id, **kw)
        if variant_id == ids[1]:
            raise OSError("máy tắt giữa chừng")

    monkeypatch.setattr(db, "update_variant", hong_giua_chung)
    with pytest.raises(OSError):
        hanh_dong.thuc_hien(db, 7, tham_so(ids[0], ids[1], ids[2]), "luat", BAY_GIO)
    nhat_ky = hanh_dong.liet_ke(db)
    assert len(nhat_ky) == 1 and ids[0] not in dang_bat(db)            # mẫu nào đã tắt thì đã có dòng nhật ký để hoàn tác
    monkeypatch.undo()
    hanh_dong.hoan_tac(db, nhat_ky[0]["id"], BAY_GIO)
    assert dang_bat(db) == set(ids)


# ---------- thêm mẫu bình luận do AI viết (thẻ thông số do AI, phần người bán / SĐT / địa chỉ do code ghép) ----------
SO_TEXT = ("## Thông tin cửa hàng\nĐịa chỉ: 64 Cầu Diễn, Hà Nội\nSố điện thoại: 0902 189 751\nNgười bán: Hoàng Văn Dũng\n\n## Chính sách\n"
           "Bảo hành: Tháng đầu lỗi 1 đổi 1\n")
MAU_VIET_TAY = "MSI G2712F – 27 inch 2K · 180Hz · 1ms – Rapid IPS · Adaptive-Sync · HDR 400\nDũng-0902189751-64 Cầu Diễn"
MO_DAU = "Mã màn: MSI G2712F\nThông số: 27 inch 2K · 180Hz · 1ms\nCông nghệ: Rapid IPS · Adaptive-Sync"
MO_DAU_2 = "MSI G2712F | 27 inch 2K | 180Hz | 1ms | Rapid IPS | HDR 400"
MO_DAU_3 = "MSI G2712F – 27 inch 2K, 180Hz, 1ms – Rapid IPS, Adaptive-Sync"
LIEN_HE = "Dũng-0902189751-64 Cầu Diễn"        # một dòng liên hệ, không ghi họ tên đầy đủ (kẻo bị gắn thẻ nhầm người)


@pytest.fixture
def so_file(tmp_path):
    duong_dan = tmp_path / "su-that.md"
    duong_dan.write_text(SO_TEXT, encoding="utf-8")
    return str(duong_dan)


@pytest.fixture
def san_pham(db):
    pid = db.add_product(name="MSI G2712F 27 inch", price="2.500.000đ")
    db.add_variant(pid, MAU_VIET_TAY, "")
    return pid


def tham_so_them(san_pham_id, *mo_dau):
    return json.dumps({"hanh_dong": "them_mau", "san_pham_id": san_pham_id, "mo_dau": list(mo_dau)}, ensure_ascii=False)


def mau_ai_dang_co(db, san_pham_id):
    return [v for v in db.variants(san_pham_id) if v["text"] != MAU_VIET_TAY]


def test_adding_ai_comments_makes_active_variants_with_the_fixed_part_and_a_log_entry(db, san_pham, so_file):
    nhat_ky_id = hanh_dong.thuc_hien(db, 7, tham_so_them(san_pham, MO_DAU, MO_DAU_2), "mau_ai", BAY_GIO, su_that_file=so_file)
    moi = mau_ai_dang_co(db, san_pham)
    assert len(moi) == 2 and all(v["active"] == 1 for v in moi)
    assert moi[0]["text"] == MO_DAU + "\n" + LIEN_HE and moi[0]["safe_text"] == ""
    assert "{giá}" not in moi[0]["text"] and "đã qua sử dụng" not in moi[0]["text"] and "Hoàng" not in moi[0]["text"]
    dong = hanh_dong.liet_ke(db)[0]
    assert (dong["id"], dong["hanh_dong"], dong["de_xuat_id"]) == (nhat_ky_id, "them_mau", 7)
    assert json.loads(dong["doi_tuong"])["variant_ids"] == [v["id"] for v in moi]


def test_undoing_added_comments_turns_them_off_and_frees_the_quota(db, san_pham, so_file):
    nhat_ky_id = hanh_dong.thuc_hien(db, 7, tham_so_them(san_pham, MO_DAU), "mau_ai", BAY_GIO, su_that_file=so_file)
    assert mau_ai.da_them_trong_ngay(db, "2026-10-24") == 1
    hanh_dong.hoan_tac(db, nhat_ky_id, BAY_GIO)
    assert all(v["active"] == 0 for v in mau_ai_dang_co(db, san_pham)) and len(mau_ai_dang_co(db, san_pham)) == 1
    assert hanh_dong.liet_ke(db)[0]["hoan_tac_luc"] == "2026-10-24 07:30:00"
    assert mau_ai.da_them_trong_ngay(db, "2026-10-24") == 0


def test_only_comments_written_through_the_ai_writer_may_be_added(db, san_pham, so_file):
    for nguon in ("luat", "ai"):
        with pytest.raises(hanh_dong.KhongLamDuoc, match="AI"):
            hanh_dong.thuc_hien(db, 7, tham_so_them(san_pham, MO_DAU), nguon, BAY_GIO, su_that_file=so_file)
    _, ids = them_mau(db, 20)
    with pytest.raises(hanh_dong.KhongLamDuoc, match="luật"):
        hanh_dong.thuc_hien(db, 7, tham_so(ids[0]), "mau_ai", BAY_GIO)           # nguồn mau_ai không được tắt mẫu
    assert mau_ai_dang_co(db, san_pham) == [] and set(ids) <= dang_bat(db)


@pytest.mark.parametrize("mo_dau", [
    MO_DAU + " Gọi 0912 345 678 nhé.", MO_DAU + " Giá chỉ 2.000.000đ.", MO_DAU + " Màn OLED 999Hz.", "Màn đẹp.",
    MO_DAU + " 🔥", MAU_VIET_TAY.splitlines()[0],
    "Bác nào hay chơi Valorant thì nên thử MSI G2712F 27 inch 2K 180Hz"])
def test_the_text_is_checked_again_when_carried_out_and_nothing_is_added_if_it_fails(db, san_pham, so_file, mo_dau):
    with pytest.raises(hanh_dong.KhongLamDuoc, match="kiểm tra"):
        hanh_dong.thuc_hien(db, 7, tham_so_them(san_pham, MO_DAU_2, mo_dau), "mau_ai", BAY_GIO, su_that_file=so_file)
    assert mau_ai_dang_co(db, san_pham) == [] and hanh_dong.liet_ke(db) == []


def test_it_cannot_run_without_a_fact_sheet_that_has_the_seller_phone_and_address(db, san_pham, tmp_path):
    with pytest.raises(hanh_dong.KhongLamDuoc, match="sổ sự thật"):
        hanh_dong.thuc_hien(db, 7, tham_so_them(san_pham, MO_DAU), "mau_ai", BAY_GIO)
    thieu = tmp_path / "thieu.md"
    thieu.write_text("## Thông tin cửa hàng\nĐịa chỉ: 64 Cầu Diễn, Hà Nội\n", encoding="utf-8")
    with pytest.raises(hanh_dong.KhongLamDuoc, match="Số điện thoại") as loi:
        hanh_dong.thuc_hien(db, 7, tham_so_them(san_pham, MO_DAU), "mau_ai", BAY_GIO, su_that_file=str(thieu))
    assert "Người bán" in str(loi.value)
    assert mau_ai_dang_co(db, san_pham) == []


@pytest.mark.parametrize("tho", [
    {"san_pham_id": "1"}, {"san_pham_id": True}, {"san_pham_id": 0}, {"san_pham_id": 10 ** 30}, {"san_pham_id": 999},
    {"mo_dau": []}, {"mo_dau": "một chuỗi"}, {"mo_dau": [1]}, {"mo_dau": [MO_DAU] * 4}])
def test_malformed_add_actions_are_refused(db, san_pham, so_file, tho):
    du_lieu = {"hanh_dong": "them_mau", "san_pham_id": san_pham, "mo_dau": [MO_DAU], **tho}
    with pytest.raises(hanh_dong.KhongLamDuoc):
        hanh_dong.thuc_hien(db, 7, json.dumps(du_lieu), "mau_ai", BAY_GIO, su_that_file=so_file)
    assert mau_ai_dang_co(db, san_pham) == []


def test_an_inactive_product_gets_no_new_comments(db, san_pham, so_file):
    db.update_product(san_pham, active=0)
    with pytest.raises(hanh_dong.KhongLamDuoc, match="không còn"):
        hanh_dong.thuc_hien(db, 7, tham_so_them(san_pham, MO_DAU), "mau_ai", BAY_GIO, su_that_file=so_file)


def test_ai_comments_are_limited_per_day_per_product_and_overall(db, san_pham, so_file):
    hanh_dong.thuc_hien(db, 7, tham_so_them(san_pham, MO_DAU, MO_DAU_2), "mau_ai", BAY_GIO, su_that_file=so_file)
    with pytest.raises(hanh_dong.KhongLamDuoc, match="(?i)hôm nay"):
        hanh_dong.thuc_hien(db, 7, tham_so_them(san_pham, MO_DAU_3, "MSI G2712F – Rapid IPS – 27 inch – 180Hz – 1ms"),
                            "mau_ai", BAY_GIO, su_that_file=so_file)
    hanh_dong.thuc_hien(db, 7, tham_so_them(san_pham, MO_DAU_3), "mau_ai", BAY_GIO, su_that_file=so_file)       # còn đúng 1
    sang_mai = BAY_GIO + timedelta(days=1)
    with pytest.raises(hanh_dong.KhongLamDuoc, match="hạn mức"):                                              # đã đủ 3 / sản phẩm
        hanh_dong.thuc_hien(db, 7, tham_so_them(san_pham, "MSI G2712F · 27 inch · 2K · 180Hz · 1ms · Rapid IPS"),
                            "mau_ai", sang_mai, su_that_file=so_file)


def test_do_it_now_works_for_added_comments_too_and_marks_the_proposal_done(db, san_pham, so_file):
    de_xuat_id = them_de_xuat(db, tham_so_them(san_pham, MO_DAU), nguon="mau_ai")
    kq = hanh_dong.lam_luon(db, de_xuat_id, "", BAY_GIO, su_that_file=so_file)
    assert kq["da_lam"] is True and len(mau_ai_dang_co(db, san_pham)) == 1
    assert luu_tru.liet_ke_de_xuat(db)[0]["trang_thai"] == "da_lam"


def test_do_it_now_for_added_comments_fails_cleanly_without_the_fact_sheet(db, san_pham):
    de_xuat_id = them_de_xuat(db, tham_so_them(san_pham, MO_DAU), nguon="mau_ai")
    with pytest.raises(hanh_dong.KhongLamDuoc):
        hanh_dong.lam_luon(db, de_xuat_id, "", BAY_GIO)
    assert mau_ai_dang_co(db, san_pham) == [] and luu_tru.liet_ke_de_xuat(db)[0]["trang_thai"] == "cho_duyet"


# ---------- nhận việc trước khi làm: hai bên không cùng làm một việc ----------
def test_a_second_click_on_a_proposal_that_is_being_done_is_refused(db):
    _, ids = them_mau(db, 20)
    de_xuat_id = them_de_xuat(db, tham_so(ids[0]))
    assert luu_tru.nhan_viec(db, de_xuat_id, BAY_GIO) == "cho_duyet"
    assert luu_tru.nhan_viec(db, de_xuat_id, BAY_GIO) is None                      # người thứ hai không nhận được
    with pytest.raises(ValueError, match="xử lý"):
        hanh_dong.lam_luon(db, de_xuat_id, "", BAY_GIO)
    assert dang_bat(db) == set(ids) and hanh_dong.liet_ke(db) == []
    with pytest.raises(ValueError):
        luu_tru.quyet_dinh(db, de_xuat_id, "da_duyet", "", BAY_GIO)               # chủ shop cũng không đổi được lúc đang làm


def test_a_proposal_whose_action_ran_but_was_never_marked_is_finished_not_repeated(db):
    _, ids = them_mau(db, 20)
    de_xuat_id = them_de_xuat(db, tham_so(ids[0]))
    luu_tru.nhan_viec(db, de_xuat_id, BAY_GIO)
    nhat_ky_id = hanh_dong.thuc_hien(db, de_xuat_id, tham_so(ids[0]), "luat", BAY_GIO)      # làm xong rồi máy tắt trước khi đánh dấu
    kq = hanh_dong.lam_luon(db, de_xuat_id, "", BAY_GIO)
    assert kq == {"da_lam": True, "nhat_ky_id": nhat_ky_id}
    assert luu_tru.liet_ke_de_xuat(db)[0]["trang_thai"] == "da_lam" and len(hanh_dong.liet_ke(db)) == 1


def test_a_claim_that_died_before_doing_anything_is_released_after_a_while(db):
    _, ids = them_mau(db, 20)
    de_xuat_id = them_de_xuat(db, tham_so(ids[0]))
    luu_tru.nhan_viec(db, de_xuat_id, BAY_GIO)
    with pytest.raises(ValueError, match="xử lý"):
        hanh_dong.lam_luon(db, de_xuat_id, "", BAY_GIO + timedelta(minutes=2))
    assert hanh_dong.lam_luon(db, de_xuat_id, "", BAY_GIO + timedelta(minutes=hanh_dong.PHUT_COI_LA_KET_VIEC + 1))["da_lam"]
    assert ids[0] not in dang_bat(db)


@pytest.mark.parametrize("truoc", ["cho_duyet", "da_duyet"])
def test_a_failing_action_gives_the_proposal_back_in_its_previous_state(db, truoc):
    _, ids = them_mau(db, 11)                                                       # tắt 2 mẫu thì còn 9 < 10
    de_xuat_id = them_de_xuat(db, tham_so(ids[0], ids[1]))
    if truoc == "da_duyet":
        luu_tru.quyet_dinh(db, de_xuat_id, "da_duyet", "", BAY_GIO)
    with pytest.raises(hanh_dong.KhongLamDuoc):
        hanh_dong.lam_luon(db, de_xuat_id, "", BAY_GIO)
    assert luu_tru.liet_ke_de_xuat(db)[0]["trang_thai"] == truoc


def test_an_unexpected_crash_also_gives_the_proposal_back(db, monkeypatch):
    _, ids = them_mau(db, 20)
    de_xuat_id = them_de_xuat(db, tham_so(ids[0]))

    def hong(*a, **kw):
        raise OSError("CSDL bị khóa")

    monkeypatch.setattr(hanh_dong, "thuc_hien", hong)
    with pytest.raises(OSError):
        hanh_dong.lam_luon(db, de_xuat_id, "", BAY_GIO)
    assert luu_tru.liet_ke_de_xuat(db)[0]["trang_thai"] == "cho_duyet"


def test_the_company_never_pauses_itself_because_of_a_failed_attempt(db, san_pham, so_file):
    de_xuat_id = them_de_xuat(db, tham_so_them(san_pham, MO_DAU + " Gọi 0912 345 678."), nguon="mau_ai")
    with pytest.raises(hanh_dong.KhongLamDuoc):
        hanh_dong.lam_luon(db, de_xuat_id, "", BAY_GIO, su_that_file=so_file)
    assert mau_ai.dang_nghi(db, BAY_GIO) == "" and db.query("SELECT 1 FROM nhat_ky_hanh_dong WHERE hoan_tac_luc IS NOT NULL") == []


# ---------- thêm từ khóa tìm nhóm do AI đề xuất ----------
GOC = ("màn hình máy tính Hà Nội", "mua bán màn hình Hà Nội", "màn hình cũ Hà Nội")
TU_KHOA = "thanh lý màn hình cũ Cầu Giấy Hà Nội"


def tham_so_tu_khoa(*tu_khoa):
    return json.dumps({"hanh_dong": "them_tu_khoa", "tu_khoa": list(tu_khoa)}, ensure_ascii=False)


def test_adding_keywords_saves_them_for_the_bot_and_writes_a_log_entry(db):
    nhat_ky_id = hanh_dong.thuc_hien(db, 7, tham_so_tu_khoa(TU_KHOA), "tu_khoa_ai", BAY_GIO, truy_van_goc=GOC)
    assert nhom_ai.tu_khoa_dang_dung(db) == [TU_KHOA]
    dong = hanh_dong.liet_ke(db)[0]
    assert (dong["id"], dong["hanh_dong"], dong["de_xuat_id"]) == (nhat_ky_id, "them_tu_khoa", 7)
    assert json.loads(dong["doi_tuong"]) == {"tu_khoa": [TU_KHOA]}


def test_undoing_keywords_removes_only_those_keywords_and_frees_the_quota(db):
    nhom_ai.them_vao_setting(db, ["dân văn phòng cần màn hình cũ Hà Nội"])
    nhat_ky_id = hanh_dong.thuc_hien(db, 7, tham_so_tu_khoa(TU_KHOA), "tu_khoa_ai", BAY_GIO, truy_van_goc=GOC)
    hanh_dong.hoan_tac(db, nhat_ky_id, BAY_GIO)
    assert nhom_ai.tu_khoa_dang_dung(db) == ["dân văn phòng cần màn hình cũ Hà Nội"]
    assert nhom_ai.da_them_trong_ngay(db, "2026-10-24") == 0 and hanh_dong.liet_ke(db)[0]["hoan_tac_luc"]


def test_each_action_only_accepts_its_own_source(db):
    for nguon in ("luat", "ai", "mau_ai"):
        with pytest.raises(hanh_dong.KhongLamDuoc, match="AI"):
            hanh_dong.thuc_hien(db, 7, tham_so_tu_khoa(TU_KHOA), nguon, BAY_GIO, truy_van_goc=GOC)
    _, ids = them_mau(db, 20)
    with pytest.raises(hanh_dong.KhongLamDuoc, match="luật"):
        hanh_dong.thuc_hien(db, 7, tham_so(ids[0]), "tu_khoa_ai", BAY_GIO)
    assert nhom_ai.tu_khoa_dang_dung(db) == [] and len(dang_bat(db)) == 20


@pytest.mark.parametrize("tu_khoa", ["mua bán màn hình HCM", "màn hình cũ Hà Nội", "màn hình", "linh kiện PC Hà Nội"])
def test_keywords_are_checked_again_when_carried_out(db, tu_khoa):
    with pytest.raises(hanh_dong.KhongLamDuoc, match="kiểm tra|trùng"):
        hanh_dong.thuc_hien(db, 7, tham_so_tu_khoa(TU_KHOA, tu_khoa), "tu_khoa_ai", BAY_GIO, truy_van_goc=GOC)
    assert nhom_ai.tu_khoa_dang_dung(db) == [] and hanh_dong.liet_ke(db) == []


def test_keyword_limits_per_day_and_in_total(db):
    nhieu = [f"mua bán màn hình quận {ten} Hà Nội" for ten in ("Cầu Giấy", "Đống Đa", "Thanh Xuân", "Hà Đông")]
    with pytest.raises(hanh_dong.KhongLamDuoc):
        hanh_dong.thuc_hien(db, 7, tham_so_tu_khoa(*nhieu), "tu_khoa_ai", BAY_GIO, truy_van_goc=GOC)     # 4 > 3 mỗi lần
    hanh_dong.thuc_hien(db, 7, tham_so_tu_khoa(*nhieu[:3]), "tu_khoa_ai", BAY_GIO, truy_van_goc=GOC)
    with pytest.raises(hanh_dong.KhongLamDuoc, match="(?i)hôm nay"):
        hanh_dong.thuc_hien(db, 7, tham_so_tu_khoa(nhieu[3]), "tu_khoa_ai", BAY_GIO, truy_van_goc=GOC)
    nhom_ai.them_vao_setting(db, [f"khác {i}" for i in range(nhom_ai.MAX_TU_KHOA_DANG_DUNG)])
    with pytest.raises(hanh_dong.KhongLamDuoc, match="hạn mức"):
        hanh_dong.thuc_hien(db, 7, tham_so_tu_khoa(nhieu[3]), "tu_khoa_ai", BAY_GIO + timedelta(days=1), truy_van_goc=GOC)


def test_do_it_now_adds_keywords_and_marks_the_proposal_done(db):
    de_xuat_id = them_de_xuat(db, tham_so_tu_khoa(TU_KHOA), nguon="tu_khoa_ai")
    assert hanh_dong.lam_luon(db, de_xuat_id, "", BAY_GIO, truy_van_goc=GOC)["da_lam"] is True
    assert nhom_ai.tu_khoa_dang_dung(db) == [TU_KHOA] and luu_tru.liet_ke_de_xuat(db)[0]["trang_thai"] == "da_lam"


def test_the_nightly_log_view_copes_with_every_kind_of_action(db, san_pham, so_file):
    hanh_dong.thuc_hien(db, 7, tham_so_tu_khoa(TU_KHOA), "tu_khoa_ai", BAY_GIO, truy_van_goc=GOC)
    hanh_dong.thuc_hien(db, 7, tham_so_them(san_pham, MO_DAU), "mau_ai", BAY_GIO, su_that_file=so_file)
    assert {d["hanh_dong"] for d in hanh_dong.liet_ke(db)} == {"them_tu_khoa", "them_mau"}


def test_log_lists_newest_first_and_respects_the_limit(db):
    _, ids = them_mau(db, 30)
    for i in ids[:3]:
        hanh_dong.thuc_hien(db, 7, tham_so(i), "luat", BAY_GIO)
    dong = hanh_dong.liet_ke(db, limit=2)
    assert len(dong) == 2 and dong[0]["id"] > dong[1]["id"]
