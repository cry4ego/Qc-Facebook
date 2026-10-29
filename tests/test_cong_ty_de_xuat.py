"""Đề xuất: chuẩn hóa dữ liệu, rào chắn của Kiểm soát rủi ro (luật cứng bằng code), đề xuất sinh theo luật."""
import json
from dataclasses import FrozenInstanceError

import pytest

from cong_ty import bao_cao, de_xuat, khach, luat, rao_chan, su_that
from cong_ty_seed import CFG, HOM_NAY, chuoi_giam, ngay, them_binh_luan
from modules.db import Database

SO = su_that.SuThat(thong_tin=(("Số điện thoại", "0902 189 751"), ("Bảo hành", "Tháng đầu lỗi 1 đổi 1")),
                    chua_dien=(), gia_them=(), cam=("miễn phí vận chuyển",), co_file=True)
GIA = frozenset({2_500_000})
VI_SAO_OK = "bot quét 900 lần mỗi ngày nhưng bài MUA giảm từ 60 xuống 25"


def mot(**kw):
    goc = dict(loai="uu_tien_nhom", tieu_de="Giảm ưu tiên nhóm A", noi_dung="Nhóm A", vi_sao="quét 624 lần, 0 bài đạt lọc",
               ky_vong="đỡ tốn lượt quét", rui_ro="có thể bỏ lỡ bài hiếm", ngay_do=7)
    vai = kw.pop("vai", "san_khach")
    return de_xuat.chuan_hoa(vai, {**goc, **kw}, HOM_NAY)


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "t.db"))
    khach.ensure_schema(database)
    return database


@pytest.fixture
def bc(db, tmp_path):
    chuoi_giam(db)
    return bao_cao.tao_bao_cao(db, CFG, str(tmp_path / "su-that.md"), HOM_NAY)


# ---------- chuẩn hóa đề xuất ----------
@pytest.mark.parametrize("ngay_do, mong_doi", [(7, "2026-10-31"), ("7", "2026-10-31"), ("2026-11-05", "2026-11-05"),
                                                (None, "2026-10-31"), ("", "2026-10-31")])
def test_measurement_day_accepts_days_ahead_or_a_date_and_defaults_to_a_week(ngay_do, mong_doi):
    assert mot(ngay_do=ngay_do).ngay_do == mong_doi


@pytest.mark.parametrize("kw", [
    {"loai": "xoa_csdl"}, {"tieu_de": ""}, {"tieu_de": "x" * 121}, {"noi_dung": "x" * 1501}, {"vi_sao": "  "},
    {"ngay_do": 0}, {"ngay_do": 90}, {"ngay_do": "hôm qua"}, {"ngay_do": "2026-10-01"}, {"noi_dung": ["a"]},
])
def test_invalid_proposals_are_rejected(kw):
    with pytest.raises(ValueError):
        mot(**kw)


def test_unknown_role_is_rejected_and_proposals_are_immutable():
    with pytest.raises(ValueError):
        mot(vai="ke_toan")
    with pytest.raises(FrozenInstanceError):
        mot().loai = "khac"


def test_text_fields_are_trimmed():
    assert mot(tieu_de="  Giảm ưu tiên nhóm A  ").tieu_de == "Giảm ưu tiên nhóm A"


# ---------- rào chắn ----------
def test_numbers_in_text_understand_vietnamese_formats():
    assert rao_chan.so_trong_chu("giảm 41%, từ 1.262 xuống 764 bài, mỗi bài 4,8 bình luận") >= {41.0, 1262.0, 764.0, 4.8}
    assert rao_chan.so_trong_chu("không có số nào") == set()


def test_clean_proposal_citing_numbers_from_the_report_passes(bc):
    assert rao_chan.kiem_tra(mot(vi_sao=VI_SAO_OK), bc, SO, GIA) == ()


def test_proposal_without_numbers_from_the_report_is_blocked(bc):
    for vi_sao in ("nhóm này có vẻ không tốt", "giảm 777% so với tuần trước", "chỉ có 0 hoặc 1 thôi"):
        assert any("số liệu" in v for v in rao_chan.kiem_tra(mot(vi_sao=vi_sao), bc, SO, GIA)), vi_sao


CAM_CUNG = [
    ("Giảm giá G274QPF xuống 2.000.000đ để thu hút khách", "giá"),
    ("Chạy chương trình khuyến mãi cuối tuần", "giá"),
    ("Chủ động nhắn riêng cho người đăng bài cần mua", "nhắn"),
    ("Tăng trần bình luận lên 80 bài mỗi ngày", "trần"),
    ("Tăng số bình luận mỗi bài lên 8", "trần"),
    ("Chạy quảng cáo trả phí cho shop", "quảng cáo"),
    ("Dùng thêm nick phụ để bình luận", "tài khoản"),
    ("Đổi mật khẩu Facebook", "tài khoản"),
    ("Xóa dữ liệu nhật ký cũ", "xóa"),
]


@pytest.mark.parametrize("noi_dung, tu_khoa", CAM_CUNG)
def test_hard_banned_actions_are_blocked_whatever_the_numbers(bc, noi_dung, tu_khoa):
    van_de = rao_chan.kiem_tra(mot(loai="khac", noi_dung=noi_dung, vi_sao=VI_SAO_OK), bc, SO, GIA)
    assert any(tu_khoa in v for v in van_de)


@pytest.mark.parametrize("noi_dung", [
    "Giảm ưu tiên nhóm Chợ PC", "Giảm số bình luận mỗi bài từ 5 xuống 3", "Tăng ưu tiên nhóm MÀN HÌNH Hà Nội",
    "Tăng giá trị của bình luận bằng cách nêu rõ thông số"])
def test_reducing_activity_and_harmless_wording_is_not_blocked(bc, noi_dung):
    assert rao_chan.kiem_tra(mot(loai="khac", noi_dung=noi_dung, vi_sao=VI_SAO_OK), bc, SO, GIA) == ()


def test_warranty_promise_outside_the_fact_sheet_is_blocked(bc):
    sai = mot(loai="mau_moi", noi_dung="Màn MSI {giá}, bảo hành 12 tháng", vi_sao=VI_SAO_OK)
    dung = mot(loai="mau_moi", noi_dung="Màn MSI {giá}, tháng đầu lỗi 1 đổi 1", vi_sao=VI_SAO_OK)
    assert any("bảo hành" in v for v in rao_chan.kiem_tra(sai, bc, SO, GIA))
    assert rao_chan.kiem_tra(dung, bc, SO, GIA) == ()


def test_new_content_goes_through_the_fact_sheet_check(bc):
    dx = mot(loai="mau_moi", noi_dung="Màn G274QPF giá sốc 1.999.000đ, gọi 0912 345 678 👍", vi_sao=VI_SAO_OK)
    van_de = " ".join(rao_chan.kiem_tra(dx, bc, SO, GIA))
    assert "1.999.000" in van_de and "0912345678" in van_de and "emoji" in van_de


def test_placeholders_in_templates_are_fine(bc):
    dx = mot(loai="mau_moi", noi_dung="Màn MSI G274QPF chỉ {giá}, xem tại 64 Cầu Diễn", vi_sao=VI_SAO_OK)
    assert rao_chan.kiem_tra(dx, bc, SO, GIA) == ()


KHONG_DAU = ("Giam uu tien 3 nhom khong co bai dat loc. Tam dung hoac giam tan suat quet cua 3 nhom nay vi khong co bai "
             "nao duoc chon")


def test_vietnamese_written_without_diacritics_is_blocked(bc):
    dx = mot(loai="khac", tieu_de="Giam uu tien nhom", noi_dung=KHONG_DAU, vi_sao=VI_SAO_OK)
    assert any("dấu" in v for v in rao_chan.kiem_tra(dx, bc, SO, GIA))


def test_accented_text_and_technical_names_are_not_mistaken_for_missing_diacritics(bc):
    ok = mot(loai="khac", tieu_de="Giảm ưu tiên nhóm", noi_dung="Giảm tần suất quét 3 nhóm không ra bài", vi_sao=VI_SAO_OK)
    ky_thuat = mot(loai="khac", tieu_de="Xem lai MSI G274QPF", noi_dung="MSI G274QPF 2K 240Hz", vi_sao=VI_SAO_OK)
    assert rao_chan.kiem_tra(ok, bc, SO, GIA) == () and rao_chan.kiem_tra(ky_thuat, bc, SO, GIA) == ()


@pytest.mark.parametrize("noi_dung", ["Màn MSI chỉ {gia}", "Màn MSI chỉ {price}, xem tại shop", "Giá {giá_cu}"])
def test_unknown_placeholders_in_templates_are_blocked(bc, noi_dung):
    dx = mot(loai="mau_moi", noi_dung=noi_dung, vi_sao=VI_SAO_OK)
    assert any("chỗ trống" in v for v in rao_chan.kiem_tra(dx, bc, SO, GIA))


def test_the_three_real_placeholders_are_fine(bc):
    dx = mot(loai="mau_moi", noi_dung="Màn MSI chỉ {giá}, mua mới {giá_mới}, tiết kiệm {tiết_kiệm}", vi_sao=VI_SAO_OK)
    assert rao_chan.kiem_tra(dx, bc, SO, GIA) == ()


CAM_LACH = [   # cách viết khác của các việc bị cấm: phải vẫn bị chặn
    "Giá giảm còn 2tr", "Bớt giá để chốt nhanh", "Cho khách chiết khấu thêm", "Tặng voucher cho khách", "Giao hàng miễn phí",
    "Giảm​ giá cuối tuần", "Dùng nick​ phụ để bình luận", "giam gia sốc", "Xoá dữ liệu cũ", "Xóa lịch sử bình luận",
    "Dọn nhật kí", "Reset database", "Inbox trực tiếp người đăng bài", "Nhắn tin cho người đăng bài",
    "Chạy ads cho shop", "Dùng bài sponsored", "Mở tài khoản thứ hai", "Đặt MAX_COMMENTED_POSTS_PER_DAY = 80",
    "Đặt COMMENT_PRODUCTS_PER_POST = 8", "Đặt BLOCK_COOLDOWN_HOURS = 1", "Giảm giá", "GIẢM  GIÁ",
    "Tặng chuột kèm màn", "Khuyến mại cuối tuần", "Dùng tài khoản khác để bình luận", "Mở thêm tài khoản",
    "Inbox cho người đăng bài mua", "Tăng bình luận lên 6 mỗi bài", "Giam gia 500k đ", "Giảm 10% giá cho khách",
]


@pytest.mark.parametrize("noi_dung", CAM_LACH)
def test_banned_actions_are_blocked_however_they_are_written(bc, noi_dung):
    assert rao_chan.kiem_tra(mot(loai="khac", noi_dung=noi_dung, vi_sao=VI_SAO_OK), bc, SO, GIA)


@pytest.mark.parametrize("truong", ["vi_sao", "rui_ro", "ky_vong", "tieu_de"])
def test_every_text_field_is_scanned_not_only_the_content(bc, truong):
    kw = {"vi_sao": VI_SAO_OK, "tieu_de": "Giảm ưu tiên nhóm A", "loai": "khac"}
    kw[truong] = f"{kw.get(truong, '')} rồi giảm giá thêm 10%"
    assert rao_chan.kiem_tra(mot(**kw), bc, SO, GIA)


@pytest.mark.parametrize("noi_dung", ["Đặt MAX_COMMENTED_POSTS_PER_DAY = 30", "Đặt COMMENT_PRODUCTS_PER_POST = 3"])
def test_lowering_the_volume_settings_is_allowed(bc, noi_dung):
    assert bc["rui_ro"]["tran"] == 40
    assert rao_chan.kiem_tra(mot(loai="doi_cau_hinh", noi_dung=noi_dung, vi_sao=VI_SAO_OK), bc, SO, GIA) == ()


def test_evidence_made_only_of_scaffolding_numbers_does_not_count(bc):
    for vi_sao in ("chiến lược ổn trong 7 ngày", "trần 40 bài mỗi ngày", "ổn định cả năm 2026"):
        assert any("số liệu" in v for v in rao_chan.kiem_tra(mot(vi_sao=vi_sao), bc, SO, GIA)), vi_sao


def test_a_made_up_number_blocks_the_proposal_even_next_to_a_real_one(bc):
    dx = mot(vi_sao="bài MUA giảm từ 60 xuống 25 và có 777 khách hỏi mua")
    assert any("777" in v for v in rao_chan.kiem_tra(dx, bc, SO, GIA))


def test_dates_in_the_reason_are_not_treated_as_claims(bc):
    dx = mot(vi_sao="tính đến ngày 24/10/2026 và 2026-10-24, bài MUA giảm từ 60 xuống 25")
    assert rao_chan.kiem_tra(dx, bc, SO, GIA) == ()


SO_6_THANG = su_that.SuThat(thong_tin=(("Bảo hành", "6 tháng"),), co_file=True)


@pytest.mark.parametrize("noi_dung", [
    "Màn MSI {giá}, bảo hành đến 12 tháng", "Màn MSI {giá}, bảo hành: 12 tháng", "Màn MSI {giá}, bảo hành vĩnh viễn",
    "Màn MSI {giá}, bảo hành một năm", "MÀN MSI {giá}, BẢO HÀNH 24 THÁNG"])
def test_warranty_promises_are_caught_in_every_phrasing(bc, noi_dung):
    dx = mot(loai="mau_moi", noi_dung=noi_dung, vi_sao=VI_SAO_OK)
    assert any("bảo hành" in v for v in rao_chan.kiem_tra(dx, bc, SO_6_THANG, GIA))


def test_the_warranty_written_in_the_fact_sheet_is_allowed_in_the_same_words(bc):
    dx = mot(loai="mau_moi", noi_dung="Màn MSI {giá}, bảo hành 6 tháng", vi_sao=VI_SAO_OK)
    assert rao_chan.kiem_tra(dx, bc, SO_6_THANG, GIA) == ()


def test_rule_written_proposals_do_not_need_to_cite_report_numbers(bc):
    dx = mot(vi_sao="chưa có lượt khách nào trong 7 ngày")
    assert any("số liệu" in v for v in rao_chan.kiem_tra(dx, bc, SO, GIA))
    assert rao_chan.kiem_tra(dx, bc, SO, GIA, nguon="luat") == ()


SO_KHONG_SDT = su_that.SuThat(co_file=True, cam=("miễn phí vận chuyển",))


@pytest.mark.parametrize("noi_dung", [
    "Màn MSI {giá}, gọi 0987654321 nhé", "Màn MSI {giá}, gọi +84 987 654 321", "Màn MSI {giá}, xem http://evil.example/x",
    "Màn MSI {giá}, vào www.shop-gia.vn", "Màn MSI {giá}, xem shop-gia.com"])
def test_llm_written_content_may_never_carry_a_phone_number_or_a_link(bc, noi_dung):
    dx = mot(loai="mau_moi", noi_dung=noi_dung, vi_sao=VI_SAO_OK)
    van_de = rao_chan.kiem_tra(dx, bc, SO_KHONG_SDT, GIA)          # sổ sự thật chưa điền SĐT cũng vẫn chặn
    assert any("số điện thoại" in v or "đường link" in v for v in van_de)


def test_the_normal_system_phone_in_the_fact_sheet_is_not_a_reason_to_allow_it_in_llm_text(bc):
    dx = mot(loai="mau_moi", noi_dung="Màn MSI {giá}, gọi 0902 189 751", vi_sao=VI_SAO_OK)
    assert any("số điện thoại" in v for v in rao_chan.kiem_tra(dx, bc, SO, GIA))


def test_new_groups_must_be_monitor_groups_in_hanoi(bc):
    dung = mot(loai="nhom_moi", noi_dung="Tìm nhóm mua bán màn hình máy tính cũ Hà Nội", vi_sao=VI_SAO_OK)
    assert rao_chan.kiem_tra(dung, bc, SO, GIA) == ()
    for sai in ("Tham gia nhóm mua bán linh kiện PC toàn quốc", "Tìm nhóm màn hình ở Sài Gòn",
                "Tìm nhóm laptop Hà Nội, không phải màn hình", "Tìm nhóm PC gaming và màn hình Hà Nội"):
        dx = mot(loai="nhom_moi", noi_dung=sai, vi_sao=VI_SAO_OK)
        assert any("nhóm" in v for v in rao_chan.kiem_tra(dx, bc, SO, GIA)), sai


# ---------- đề xuất theo luật (chạy được khi không có AI) ----------
@pytest.fixture
def bc_that(db, tmp_path):
    """Nguồn khách giảm, chưa ghi khách nào, một mẫu bình luận bị từ chối gần hết, bản không SĐT đang bật"""
    chuoi_giam(db)
    pid = db.add_product(name="MSI G274QPF", price="2.500.000đ")
    vid = db.add_variant(pid, "Màn MSI {giá}", "")
    them_binh_luan(db, ngay(5), 25, 25, variant_id=vid, tt_binh_luan="Bị từ chối · đã xóa")
    db.set_setting("safe_all", "1")
    db.set_setting("safe_all_reason", "2026-10-05 19:15:31 — Facebook báo bị chặn bình luận")
    return bao_cao.tao_bao_cao(db, CFG, str(tmp_path / "su-that.md"), HOM_NAY)


def test_rules_propose_what_the_report_shows(bc_that):
    dxs = luat.de_xuat_theo_luat(bc_that, HOM_NAY)
    assert {"uu_tien_nhom", "bat_tat_mau", "thu_thap_so_lieu", "nhom_moi", "doi_cau_hinh"} <= {d.loai for d in dxs}
    assert any(d.loai == "khac" and "SĐT" in d.tieu_de for d in dxs)
    assert all(d.vai in de_xuat.VAI for d in dxs)


def test_action_parameters_are_never_taken_from_what_the_ai_wrote():
    tho = {"loai": "bat_tat_mau", "tieu_de": "Tắt mẫu", "noi_dung": "Tắt vài mẫu", "vi_sao": "bị chặn 25 lần",
           "tham_so": '{"hanh_dong": "tat_mau", "variant_ids": [1]}'}
    assert de_xuat.chuan_hoa("noi_dung", tho, HOM_NAY).tham_so == ""


def test_rules_attach_a_structured_action_to_the_turn_off_proposal(bc_that):
    tat_mau = next(d for d in luat.de_xuat_theo_luat(bc_that, HOM_NAY) if d.loai == "bat_tat_mau")
    tham_so = json.loads(tat_mau.tham_so)
    assert tham_so["hanh_dong"] == "tat_mau" and tham_so["variant_ids"]
    assert all(f"#{i}" in tat_mau.noi_dung for i in tham_so["variant_ids"])      # việc ghi trong chữ = việc sẽ làm


def test_every_rule_proposal_passes_the_guard(bc_that):
    for d in luat.de_xuat_theo_luat(bc_that, HOM_NAY):
        assert rao_chan.kiem_tra(d, bc_that, SO, GIA, nguon="luat") == (), d.tieu_de


def test_rules_do_not_ask_for_customer_data_when_it_exists(db, tmp_path):
    chuoi_giam(db)
    khach.them(db, khach.chuan_hoa(ngay(1), "Gọi", 1, hom_nay=HOM_NAY))
    bc = bao_cao.tao_bao_cao(db, CFG, str(tmp_path / "su-that.md"), HOM_NAY)
    assert not any(d.loai == "thu_thap_so_lieu" for d in luat.de_xuat_theo_luat(bc, HOM_NAY))


def test_rules_stay_quiet_on_an_empty_database(db, tmp_path):
    bc = bao_cao.tao_bao_cao(db, CFG, str(tmp_path / "su-that.md"), HOM_NAY)
    dxs = luat.de_xuat_theo_luat(bc, HOM_NAY)
    assert [d.loai for d in dxs] == ["thu_thap_so_lieu"]
    assert rao_chan.kiem_tra(dxs[0], bc, SO, GIA, nguon="luat") == ()
