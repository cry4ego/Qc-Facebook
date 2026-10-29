"""Mẫu bình luận do AI viết: bình luận chỉ là một THẺ NGẮN — mã màn, thông số, công nghệ (AI viết, tối đa 3 dòng) rồi MỘT dòng
liên hệ "Tên-SĐT-địa chỉ" (CODE ghép từ sổ sự thật, không ghi họ tên đầy đủ). Không lời chào, không giá, không bảo hành, không "đã qua sử dụng". Mọi chữ AI viết
phải qua rào chắn bằng code (không SĐT / link / emoji / giá / bảo hành, không bịa thông số, không văn xuôi, không trùng mẫu có)."""
import json
from datetime import datetime, timedelta

import pytest

from cong_ty import ai, hanh_dong, mau_ai, su_that
from modules import products
from modules.db import Database

BAY_GIO = datetime(2026, 10, 24, 7, 30)
SO_TEXT = ("## Thông tin cửa hàng\nTên shop: ASL Workshop\nĐịa chỉ: 64 Cầu Diễn, Hà Nội\nSố điện thoại: 0902 189 751\n"
           "Zalo: 0902 189 751\nNgười bán: Hoàng Văn Dũng\n\n## Chính sách\nBảo hành: Tháng đầu lỗi 1 đổi 1\n"
           "\n## Không được nói\n- miễn phí vận chuyển\n")
MA_MAN = "G2712F"
MAU_NGUOI_VIET = "MSI G2712F – 27 inch 2K · 180Hz · 1ms – Rapid IPS · Adaptive-Sync · HDR 400\nDũng-0902189751-64 Cầu Diễn"
MO_DAU_TOT = "Mã màn: MSI G2712F\nThông số: 27 inch 2K · 180Hz · 1ms\nCông nghệ: Rapid IPS · Adaptive-Sync"
MO_DAU_KHAC = "MSI G2712F | 27 inch 2K | 180Hz | 1ms | Rapid IPS | HDR 400"
MO_DAU_KHAC_2 = "MSI G2712F – 27 inch 2K, 180Hz, 1ms – Rapid IPS, Adaptive-Sync"
LIEN_HE = "Dũng-0902189751-64 Cầu Diễn"        # tên gọi - SĐT liền - số nhà + phố (26/10/2026: họ tên đầy đủ bị Facebook gợi ý gắn thẻ nhầm người)


@pytest.fixture
def so(tmp_path):
    duong_dan = tmp_path / "su-that.md"
    duong_dan.write_text(SO_TEXT, encoding="utf-8")
    return su_that.doc(str(duong_dan))


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "t.db"))
    hanh_dong.ensure_schema(database)
    return database


@pytest.fixture
def san_pham(db):
    pid = db.add_product(name="MSI G2712F 27 inch", price="2.500.000đ")
    db.add_variant(pid, MAU_NGUOI_VIET, "")
    return db.get_product(pid)


GIA = frozenset({2_500_000})


class AIGia:
    def __init__(self, tra_loi=None, het_luot=False):
        self.tra_loi, self.het_luot, self.prompts = tra_loi, het_luot, []

    def con_luot(self):
        return not self.het_luot

    def hoi(self, he_thong, nguoi_dung, nhan=""):
        self.prompts.append((he_thong, nguoi_dung, nhan))
        if self.het_luot or self.tra_loi is None:
            return None
        van_ban = self.tra_loi if isinstance(self.tra_loi, str) else json.dumps(self.tra_loi, ensure_ascii=False)
        return ai.KetQuaAI(van_ban, "gemini")


def ghi_nhat_ky_them_mau(db, ids, luc="2026-10-24 06:00:00", hoan_tac_luc=None):
    db.execute("INSERT INTO nhat_ky_hanh_dong (de_xuat_id, hanh_dong, doi_tuong, luc, hoan_tac_luc) VALUES (?, ?, ?, ?, ?)",
               (1, mau_ai.THEM_MAU, json.dumps({"variant_ids": ids}), luc, hoan_tac_luc))


# ---------- phần cuối do code ghép: MỘT dòng liên hệ "Tên-SĐT-địa chỉ" ----------
def test_the_fixed_part_is_one_contact_line_with_first_name_phone_digits_and_street(so):
    day_du = mau_ai.ghep_mau(MO_DAU_TOT, so)
    assert day_du == MO_DAU_TOT + "\n" + LIEN_HE
    assert mau_ai.khung_co_dinh(so) == LIEN_HE


def test_the_full_name_is_never_written_so_facebook_cannot_suggest_tagging_someone(so):
    day_du = mau_ai.ghep_mau(MO_DAU_TOT, so)
    for cam in ("Hoàng", "Văn", "Người bán", "Zalo", "Hotline", "Hà Nội"):
        assert cam not in day_du, cam


def test_nothing_wordy_is_added_even_when_the_fact_sheet_has_a_warranty(so):
    day_du = mau_ai.ghep_mau(MO_DAU_TOT, so)
    for thua in ("đã qua sử dụng", "Lưu ý", "Giá", "{", "Bảo hành", "Mã sản phẩm"):
        assert thua not in day_du, thua
    assert day_du.count("\n") <= 3 and len(day_du) <= 130            # thẻ ngắn: tối đa 3 dòng thông số + 1 dòng liên hệ


def test_the_safe_version_is_only_the_spec_card_because_the_contact_line_has_the_phone(so):
    an_toan = products.make_safe(mau_ai.ghep_mau(MO_DAU_TOT, so))
    assert an_toan == MO_DAU_TOT
    assert "0902" not in an_toan and "Cầu Diễn" not in an_toan and "Dũng" not in an_toan


@pytest.mark.parametrize("thieu", ["Địa chỉ", "Số điện thoại", "Người bán"])
def test_no_comment_is_built_when_the_fact_sheet_lacks_the_seller_phone_or_address(tmp_path, thieu):
    duong_dan = tmp_path / "thieu.md"
    duong_dan.write_text("\n".join(d for d in SO_TEXT.splitlines() if not d.startswith(thieu + ":")), encoding="utf-8")
    with pytest.raises(mau_ai.ThieuSoSuThat, match=thieu):
        mau_ai.ghep_mau(MO_DAU_TOT, su_that.doc(str(duong_dan)))


def test_the_opening_can_be_read_back_from_a_built_comment(so):
    assert mau_ai.mo_dau_cua(mau_ai.ghep_mau(MO_DAU_TOT, so)) == MO_DAU_TOT
    cu = "Bác nào cần màn thì xem.\nLưu ý: đây là màn cũ công ty thanh lý, đã qua sử dụng (không phải hàng mới).\nGiá công khai: {giá}"
    assert mau_ai.mo_dau_cua(cu) == "Bác nào cần màn thì xem."
    ban_truoc = MO_DAU_TOT + "\nNgười bán: Hoàng Văn Dũng\nSĐT/Zalo: 0902 189 751\nĐịa chỉ: 64 Cầu Diễn, Hà Nội"   # khuôn 3 dòng của sáng 28/10
    assert mau_ai.mo_dau_cua(ban_truoc) == MO_DAU_TOT
    assert mau_ai.mo_dau_cua(MO_DAU_TOT) == MO_DAU_TOT                       # không có dòng liên hệ thì giữ nguyên


# ---------- rào chắn cho dòng thông số do AI viết ----------
def kiem_tra(mo_dau, so, da_co=(), thong_so=None):
    thong_so = "MSI G2712F 27 inch\n" + MAU_NGUOI_VIET if thong_so is None else thong_so
    return mau_ai.kiem_tra_mo_dau(mo_dau, thong_so, list(da_co), so, GIA, MA_MAN)


def test_a_good_card_passes(so):
    assert kiem_tra(MO_DAU_TOT, so) == ()


def test_other_ways_to_lay_out_the_same_facts_pass(so):
    assert kiem_tra(MO_DAU_KHAC, so) == ()
    assert kiem_tra(MO_DAU_KHAC_2, so) == ()


@pytest.mark.parametrize("mo_dau, tu_khoa", [
    ("Màn đẹp.", "ngắn"),
    ("Bác ơi " + "màn này rất mượt khi chơi game. " * 20, "dài"),
    (MO_DAU_TOT + "\nMột dòng\nHai dòng", "dòng"),
    (MO_DAU_TOT + " Gọi 0912 345 678 nhé.", "điện thoại"),
    (MO_DAU_TOT + " Xem thêm tại https://shop.example.com", "link"),
    (MO_DAU_TOT + " 🔥🔥", "emoji"),
    (MO_DAU_TOT + " Giá chỉ 2.000.000đ thôi bác.", "giá"),
    (MO_DAU_TOT + " Giá 2 triệu rưỡi.", "giá"),
    (MO_DAU_TOT + " Có bảo hành 12 tháng.", "bảo hành"),
    (MO_DAU_TOT + " Bác inbox mình nhé.", "liên hệ"),
    (MO_DAU_TOT + " Liên hệ qua Zalo nha.", "liên hệ"),
    (MO_DAU_TOT + " Hàng chính hãng, uy tín nhất Hà Nội.", "cam kết"),
    (MO_DAU_TOT + " Chỉ còn 2 máy, nhanh tay bác ơi.", "cam kết"),
    (MO_DAU_TOT + " Giá {giá} rất tốt.", "chỗ trống"),
    (MO_DAU_TOT + " Hỗ trợ miễn phí vận chuyển luôn.", "cấm"),
    (MO_DAU_TOT + " Mua là thích ngay!", "chấm than"),
    (MO_DAU_TOT + "\nNgười bán: Hoàng Văn Dũng", "người bán"),
    ("MSI G2712F – 27 inch 2K · 180Hz · 1ms · Hoàng Văn Dũng", "người bán"),
    ("MSI G2712F – 27 inch 2K · 180Hz · 1ms · Dũng", "người bán"),
    (MO_DAU_TOT + "\nDũng-0902189751-64 Cầu Diễn", "điện thoại"),
])
def test_dangerous_cards_are_refused(so, mo_dau, tu_khoa):
    van_de = kiem_tra(mo_dau, so)
    assert van_de and any(tu_khoa in v for v in van_de), (mo_dau, van_de)


@pytest.mark.parametrize("mo_dau, tu_khoa", [
    ("Thông số: 27 inch 2K · 180Hz · 1ms\nCông nghệ: Rapid IPS", "mã màn"),
    ("MSI G2712F\nCông nghệ: Rapid IPS · Adaptive-Sync", "thông số"),
    ("MSI G2712F – 27 inch", "thông số"),
    ("Màn mượt cho game thủ, rất đáng mua với MSI G2712F 27 inch 2K 180Hz", "mô tả thật"),
    ("Bác nào hay chơi Valorant thì nên thử MSI G2712F 27 inch 2K 180Hz", "mô tả thật"),
])
def test_it_must_be_a_card_with_the_model_code_and_specs_not_a_sentence(so, mo_dau, tu_khoa):
    van_de = kiem_tra(mo_dau, so)
    assert van_de and any(tu_khoa in v for v in van_de), (mo_dau, van_de)


@pytest.mark.parametrize("bia", ["Tần số quét 240Hz cho game thủ.", "Tấm nền OLED cho màu cực đẹp.",
                                 "Màn này hợp card RTX 4090 luôn bác."])
def test_specs_that_are_not_in_the_real_product_text_are_refused(so, bia):
    van_de = kiem_tra(MO_DAU_TOT + " " + bia, so)
    assert any("thông số" in v for v in van_de), van_de


def test_a_spec_that_is_only_in_a_variant_the_owner_switched_off_is_not_a_real_spec(db, so, san_pham):
    cu = db.add_variant(san_pham["id"], "MSI G2712F có USB-C sạc 65W và loa 2x2W, bảo hành dài", "", active=0)
    sach = mau_ai.thong_so_san_pham(db, san_pham)
    assert "USB-C" not in sach and "Rapid IPS" in sach
    assert any("thông số" in v for v in kiem_tra(MO_DAU_TOT + " USB-C", so, thong_so=sach))
    db.update_variant(cu, active=1)
    assert "USB-C" in mau_ai.thong_so_san_pham(db, san_pham)


def test_an_opening_too_close_to_an_existing_comment_is_refused(so):
    dong_dau = MAU_NGUOI_VIET.splitlines()[0]
    assert any("giống" in v for v in kiem_tra(dong_dau, so, da_co=[MAU_NGUOI_VIET]))
    assert any("giống" in v for v in kiem_tra(MO_DAU_TOT, so, da_co=[MO_DAU_TOT]))
    assert kiem_tra(MO_DAU_TOT, so, da_co=[MAU_NGUOI_VIET]) == ()        # cùng thông số nhưng cách trình bày khác thì được


def test_hidden_characters_do_not_hide_a_phone_number(so):
    assert kiem_tra(MO_DAU_TOT + " 0902​189​751", so)


# ---------- chữ được lưu phải ĐÚNG là chữ đã kiểm tra ----------
@pytest.mark.parametrize("an", ["‮", "\U000e0041", "​", "⁠", "﻿", "­", "‏"])
def test_invisible_format_characters_are_removed_from_what_is_stored(db, so, san_pham, an):
    kq = mau_ai.soan_mau(db, so, GIA, AIGia({"mo_dau": [MO_DAU_TOT.replace("màn", "m" + an + "àn", 1)]}), BAY_GIO)
    assert kq.mo_dau == (MO_DAU_TOT,)


@pytest.mark.parametrize("dieu_khien", ["\r", "\x0b", "\x07", "\x1b", "\x85", " ", " ", "\t"])
def test_control_characters_are_refused(so, dieu_khien):
    van_de = kiem_tra(MO_DAU_TOT + dieu_khien + "Rapid IPS", so)
    assert any("điều khiển" in v for v in van_de), van_de


def test_compatibility_characters_are_normalised_and_windows_line_breaks_become_newlines():
    assert mau_ai.lam_sach_mo_dau("  ﬁne ① ㎏\r\nHai dòng  ") == "fine 1 kg\nHai dòng"


def test_what_is_stored_is_exactly_what_was_validated(db, so, san_pham):
    kq = mau_ai.soan_mau(db, so, GIA, AIGia({"mo_dau": ["​" + MO_DAU_TOT + "‮"]}), BAY_GIO)
    assert len(kq.mo_dau) == 1
    for mo_dau in kq.mo_dau:
        assert mo_dau == mau_ai.lam_sach_mo_dau(mo_dau) and kiem_tra(mo_dau, so) == ()
    assert mau_ai.ghep_mau("​" + kq.mo_dau[0], so).startswith(kq.mo_dau[0] + "\n")
    assert json.loads(mau_ai.de_xuat_tu_ket_qua(kq, BAY_GIO.date()).tham_so)["mo_dau"] == [MO_DAU_TOT]


# ---------- những chỗ hở rào chắn mà bản rà soát tìm ra ----------
@pytest.mark.parametrize("them, tu_khoa", [
    (" BH 3 tháng nhé.", "bảo hành"),
    (" Lỗi đổi 1-1 trong 7 ngày.", "bảo hành"),
    (" Không ưng thì hoàn tiền.", "bảo hành"),
    (" Freeship nội thành luôn.", "bảo hành"),
    (" Giá chưa tới ba triệu.", "số"),
    (" Chỉ còn hai máy thôi.", "cam kết"),
    (" Số lượng có hạn, kẻo lỡ nhé.", "cam kết"),
    (" Tốt hơn hẳn màn Dell và LG.", "thông số"),
    (" Màn có 2K Full HD.", "thông số"),
    (" Đáp ứng chỉ 5ms thôi.", "thông số"),
    (" Có loa tích hợp luôn.", "thông số"),
    (" Xem thêm tại goo.gl/abc12", "link"),
    (" Gọi em nhé.", "liên hệ"),
    (" Nhắn mình nhé.", "liên hệ"),
    (" Add Zаlo nha.", "Latin"),
    (" Đến mua 3 tháng sau cũng được.", "số"),
])
def test_gaps_found_by_the_independent_review_are_closed(so, them, tu_khoa):
    mo_dau = MO_DAU_TOT + them
    van_de = kiem_tra(mo_dau, so)
    assert van_de and any(tu_khoa in v for v in van_de), (mo_dau, van_de)


def test_english_prose_is_refused(so):
    mo_dau = "Great monitor for gaming, very smooth and sharp image, MSI G2712F 27 inch 2K 180Hz."
    assert any("mô tả thật" in v for v in kiem_tra(mo_dau, so))


def test_only_the_safe_first_line_of_existing_comments_is_sent_to_the_ai(db, so, san_pham):
    db.add_variant(san_pham["id"], "Liên hệ ngay 0912 345 678 để biết giá.\nMàn đẹp.", "")
    bo_ai = AIGia({"mo_dau": [MO_DAU_TOT]})
    mau_ai.soan_mau(db, so, GIA, bo_ai, BAY_GIO)
    assert "0912" not in " ".join(" ".join(p[:2]) for p in bo_ai.prompts)


# ---------- thông số thật của sản phẩm + dữ liệu gửi AI ----------
def test_product_facts_come_only_from_human_written_variants(db, san_pham):
    ai_viet = db.add_variant(san_pham["id"], "Mẫu do AI viết có chữ OLED 999Hz", "")
    ghi_nhat_ky_them_mau(db, [ai_viet])
    sach = mau_ai.thong_so_san_pham(db, san_pham)
    assert "Rapid IPS" in sach and "OLED" not in sach and "999Hz" not in sach


def test_when_every_human_variant_is_switched_off_their_facts_are_still_used(db, san_pham):
    for v in db.variants(san_pham["id"]):
        db.update_variant(v["id"], active=0)
    assert "Rapid IPS" in mau_ai.thong_so_san_pham(db, san_pham)


def test_what_is_sent_to_the_ai_has_no_phone_address_seller_or_customer_data(db, so, san_pham):
    bo_ai = AIGia({"mo_dau": [MO_DAU_TOT]})
    mau_ai.soan_mau(db, so, GIA, bo_ai, BAY_GIO)
    gui = " ".join(" ".join(p[:2]) for p in bo_ai.prompts)
    assert "0902" not in gui and "189 751" not in gui and "Cầu Diễn" not in gui
    assert "Dũng" not in gui and "Hoàng" not in gui
    assert "Rapid IPS" in gui and "MSI G2712F" in gui


def test_the_ai_is_told_the_model_code_and_which_layout_to_use(db, so, san_pham):
    bo_ai = AIGia({"mo_dau": [MO_DAU_TOT]})
    mau_ai.soan_mau(db, so, GIA, bo_ai, BAY_GIO)
    he_thong, nguoi_dung, nhan = bo_ai.prompts[0]
    gui = json.loads(nguoi_dung)
    assert nhan == "viet_mau" and gui["san_pham"] == {"ten": "MSI G2712F 27 inch", "ma_man": MA_MAN}
    assert len(gui["kieu_trinh_bay"]) == gui["so_luong"] and "goc_nhin" not in gui


def test_the_prompt_asks_for_a_short_card_and_forbids_everything_wordy():
    p = mau_ai.HE_THONG
    for can in ("mã màn", "thông số", "công nghệ", "dòng liên hệ"):
        assert can in p
    for cam in ("lời chào", "giá", "bảo hành", "tình trạng", "số điện thoại", "địa chỉ", "tên người bán", "lời cam kết"):
        assert cam in p, cam
    assert "Lưu ý: đây" not in p and "chào mời tự nhiên" not in p


# ---------- soạn mẫu ----------
def test_composing_keeps_the_valid_cards_and_explains_the_refused_ones(db, so, san_pham):
    bo_ai = AIGia({"mo_dau": [MO_DAU_TOT, MO_DAU_TOT + " Gọi 0912 345 678.", "Màn đẹp."]})
    kq = mau_ai.soan_mau(db, so, GIA, bo_ai, BAY_GIO)
    assert kq.san_pham["id"] == san_pham["id"] and kq.mo_dau == (MO_DAU_TOT,) and kq.nguon == "gemini"
    assert len(kq.bi_loai) == 2 and all(ly_do for _, ly_do in kq.bi_loai)
    assert "1" in kq.ghi_chu and "loại 2" in kq.ghi_chu


def test_two_cards_that_are_alike_do_not_both_get_through(db, so, san_pham):
    kq = mau_ai.soan_mau(db, so, GIA, AIGia({"mo_dau": [MO_DAU_TOT, MO_DAU_TOT + "."]}), BAY_GIO)
    assert len(kq.mo_dau) == 1


@pytest.mark.parametrize("tra_loi", [None, "không phải json", {"mo_dau": "một chuỗi"}, {"mo_dau": [1, None, {"a": 1}]}, {}])
def test_a_bad_or_missing_ai_reply_gives_nothing_and_a_reason(db, so, san_pham, tra_loi):
    kq = mau_ai.soan_mau(db, so, GIA, AIGia(tra_loi), BAY_GIO)
    assert kq.mo_dau == () and kq.ghi_chu


def test_no_ai_calls_are_wasted_when_nothing_can_be_added(db, so, san_pham):
    bo_ai = AIGia({"mo_dau": [MO_DAU_TOT]}, het_luot=True)
    assert mau_ai.soan_mau(db, so, GIA, bo_ai, BAY_GIO).mo_dau == () and bo_ai.prompts == []
    db.update_product(san_pham["id"], active=0)
    bo_ai = AIGia({"mo_dau": [MO_DAU_TOT]})
    assert mau_ai.soan_mau(db, so, GIA, bo_ai, BAY_GIO).mo_dau == () and bo_ai.prompts == []


def test_it_picks_the_product_with_the_fewest_ai_comments(db, so, san_pham):
    khac = db.add_product(name="MSI G274QPF 27 inch", price="2.650.000đ")
    db.add_variant(khac, MAU_NGUOI_VIET.replace("G2712F", "G274QPF"), "")
    ai_viet = db.add_variant(san_pham["id"], "Mẫu AI đã thêm trước đó", "")
    ghi_nhat_ky_them_mau(db, [ai_viet])
    assert mau_ai.chon_san_pham(db)["id"] == khac


def test_ai_comments_are_capped_per_product_and_overall(db, so, san_pham):
    ids = [db.add_variant(san_pham["id"], f"AI {i}", "") for i in range(mau_ai.MAX_MAU_AI_MOI_SAN_PHAM)]
    ghi_nhat_ky_them_mau(db, ids)
    assert mau_ai.chon_san_pham(db) is None
    khac = db.add_product(name="MSI G274QPF", price="2.650.000đ")
    db.add_variant(khac, MAU_NGUOI_VIET, "")
    assert mau_ai.chon_san_pham(db)["id"] == khac
    nhieu = [db.add_variant(khac, f"AI khác {i}", "") for i in range(mau_ai.MAX_MAU_AI_DANG_BAT - len(ids))]
    ghi_nhat_ky_them_mau(db, nhieu)
    assert mau_ai.chon_san_pham(db) is None


def test_switched_off_ai_comments_do_not_count_against_the_cap(db, san_pham):
    ids = [db.add_variant(san_pham["id"], f"AI {i}", "") for i in range(mau_ai.MAX_MAU_AI_MOI_SAN_PHAM)]
    ghi_nhat_ky_them_mau(db, ids)
    for i in ids:
        db.update_variant(i, active=0)
    assert mau_ai.chon_san_pham(db)["id"] == san_pham["id"]


def test_the_daily_quota_limits_how_many_cards_are_asked_for(db, so, san_pham):
    ghi_nhat_ky_them_mau(db, [901, 902], luc="2026-10-24 06:00:00")
    bo_ai = AIGia({"mo_dau": [MO_DAU_TOT, MO_DAU_KHAC, MO_DAU_KHAC_2]})
    kq = mau_ai.soan_mau(db, so, GIA, bo_ai, BAY_GIO)
    assert len(kq.mo_dau) == 1                          # hôm nay đã thêm 2 trong tối đa MAX_MAU_AI_MOI_NGAY = 3
    ghi_nhat_ky_them_mau(db, [903], luc="2026-10-24 06:30:00")
    bo_ai = AIGia({"mo_dau": [MO_DAU_TOT]})
    assert mau_ai.soan_mau(db, so, GIA, bo_ai, BAY_GIO).mo_dau == () and bo_ai.prompts == []


def test_it_pauses_for_a_week_after_the_owner_undoes_ai_comments(db, so, san_pham):
    ghi_nhat_ky_them_mau(db, [901], luc="2026-10-23 06:00:00", hoan_tac_luc="2026-10-23 09:00:00")
    bo_ai = AIGia({"mo_dau": [MO_DAU_TOT]})
    kq = mau_ai.soan_mau(db, so, GIA, bo_ai, BAY_GIO)
    assert kq.mo_dau == () and bo_ai.prompts == [] and "hoàn tác" in kq.ghi_chu
    het_nghi = BAY_GIO + timedelta(days=mau_ai.NGAY_NGHI_SAU_HOAN_TAC + 1)
    assert mau_ai.soan_mau(db, so, GIA, AIGia({"mo_dau": [MO_DAU_TOT]}), het_nghi).mo_dau == (MO_DAU_TOT,)


# ---------- đề xuất do code dựng từ phần AI viết ----------
def test_the_proposal_shows_only_the_cards_and_carries_a_code_built_action(db, so, san_pham):
    kq = mau_ai.soan_mau(db, so, GIA, AIGia({"mo_dau": [MO_DAU_TOT]}), BAY_GIO)
    dx = mau_ai.de_xuat_tu_ket_qua(kq, BAY_GIO.date())
    tham_so = json.loads(dx.tham_so)
    assert tham_so == {"hanh_dong": "them_mau", "san_pham_id": san_pham["id"], "mo_dau": [MO_DAU_TOT]}
    assert MO_DAU_TOT in dx.noi_dung and "0902" not in dx.noi_dung and dx.vai == "noi_dung" and dx.loai == "mau_moi"
    assert dx.vi_sao and dx.rui_ro
    assert "lưu ý màn cũ" not in dx.noi_dung and "bảo hành" not in dx.noi_dung
