"""Cuộc họp sáng: các vai họp, Kiểm soát rủi ro chặn đề xuất vi phạm, Giám đốc chốt, biên bản + đề xuất lưu CSDL."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from cong_ty import ai, hanh_dong, hop, khach, luu_tru, nhom_ai, su_that
from cong_ty import vai as vai_mod
from cong_ty.de_xuat import chuan_hoa
from cong_ty_seed import HOM_NAY, chuoi_giam, ngay, them_binh_luan
from modules.db import Database

CFG_HOP = SimpleNamespace(MAX_COMMENTED_POSTS_PER_DAY=40, CONG_TY_DE_XUAT_TOI_DA=3, CONG_TY_NGAY_QUAN_SAT=7)
SDT_SHOP, NGUOI_BAN = "0902 189 751", "Hoàng Văn Dũng"
VI_SAO = "bài MUA giảm từ 60 xuống 25 mỗi ngày"


def dx(loai, tieu_de, noi_dung, vi_sao=VI_SAO):
    return {"loai": loai, "tieu_de": tieu_de, "noi_dung": noi_dung, "vi_sao": vi_sao, "ky_vong": "nhiều khách hơn",
            "rui_ro": "ít", "ngay_do": 7}


DX_NHOM = dx("nhom_moi", "Tìm thêm nhóm màn hình Hà Nội", "Tìm nhóm mua bán màn hình cũ ở Hà Nội")
DX_MAU_OK = dx("mau_moi", "Mẫu nhấn mạnh 2K 240Hz", "Màn MSI G274QPX 2K 240Hz chỉ {giá}, xem tại 64 Cầu Diễn")
DX_GIAM_GIA = dx("mau_moi", "Mẫu giảm giá sốc", "Giảm giá G274QPF còn 2.000.000đ")
DX_KHONG_SO = dx("khac", "Nghĩ thêm", "Suy nghĩ thêm về nội dung", vi_sao="cảm thấy chưa ổn")
DX_GIA_SAI = dx("mau_moi", "Mẫu giá cụ thể", "Màn MSI G274QPF chỉ 1.999.000đ")
DX_GIA_DA_SUA = {**DX_GIA_SAI, "noi_dung": "Màn MSI G274QPF chỉ {giá}"}


def vai(*de_xuat, nhan_xet="Nhận xét ngắn"):
    return {"nhan_xet": nhan_xet, "de_xuat": list(de_xuat)}


def giam_doc(tom_tat="Họp sáng xong"):
    return {"tom_tat": tom_tat, "quyet_dinh": [{"so_de_xuat": i, "quyet_dinh": "chap_nhan", "ly_do": "ổn"}
                                               for i in range(1, 40)]}


class AIGia:
    """Bộ AI giả: trả lời theo nhãn vai bằng JSON dựng sẵn; nhãn không có trong kịch bản = hết lượt / lỗi (None)"""

    def __init__(self, tra_loi=None, het_luot=False):
        self.tra_loi, self.het_luot, self.da_hoi, self.prompts = tra_loi or {}, het_luot, [], []

    def con_luot(self):
        return not self.het_luot

    def hoi(self, he_thong, nguoi_dung, nhan=""):
        self.da_hoi.append(nhan)
        self.prompts.append((he_thong, nguoi_dung))
        tra_loi = self.tra_loi.get(nhan)
        if self.het_luot or tra_loi is None:
            return None
        return ai.KetQuaAI(tra_loi if isinstance(tra_loi, str) else json.dumps(tra_loi, ensure_ascii=False), "gemini")

    def trang_thai(self):
        return []


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "t.db"))
    khach.ensure_schema(database)
    chuoi_giam(database)
    return database


def hop_sang(db, tmp_path, bo_ai, hom_nay=HOM_NAY, co_dia_chi=True, **kw):
    dia_chi = "Địa chỉ: 64 Cầu Diễn, Hà Nội\n" if co_dia_chi else ""
    (tmp_path / "su-that.md").write_text(
        f"## Thông tin cửa hàng\n{dia_chi}Số điện thoại: {SDT_SHOP}\nNgười bán: {NGUOI_BAN}\nBảo hành: Tháng đầu lỗi 1 đổi 1\n",
        encoding="utf-8")
    return hop.hop(db, CFG_HOP, str(tmp_path / "su-that.md"), hom_nay, bo_ai, thu_muc_bao_cao=str(tmp_path / "bc"), **kw)


def de_xuat_cua(db, cuoc_id, trang_thai=None):
    return luu_tru.liet_ke_de_xuat(db, trang_thai=trang_thai, cuoc_hop_id=cuoc_id)


# ---------- họp không có AI ----------
def test_meeting_without_ai_still_completes_with_rule_based_proposals(db, tmp_path):
    kq = hop_sang(db, tmp_path, AIGia(het_luot=True))
    cuoc = luu_tru.cuoc_hop_gan_nhat(db)
    assert kq["trang_thai"] == "xong" and cuoc["nguon_ai"] == "" and cuoc["so_luot_ai"] == 0
    assert "không có AI" in cuoc["tom_tat"] and "PHỄU" in cuoc["bao_cao"]
    cho = de_xuat_cua(db, cuoc["id"], "cho_duyet")
    assert 1 <= len(cho) <= 3 and all(d["nguon"] == "luat" for d in cho)
    assert (tmp_path / "bc" / "2026-10-24.md").exists()          # báo cáo sáng tự lưu theo từng cuộc họp


# ---------- họp có AI ----------
def test_meeting_with_ai_records_every_role_and_applies_the_cap(db, tmp_path):
    bo_ai = AIGia({"phan_tich": vai(), "san_khach": vai(DX_NHOM), "noi_dung": vai(DX_MAU_OK), "cham_soc_khach": vai(),
                   "giam_doc": giam_doc("Tóm tắt của Giám đốc")})
    hop_sang(db, tmp_path, bo_ai)
    assert bo_ai.da_hoi == ["phan_tich", "san_khach", "noi_dung", "cham_soc_khach", "giam_doc", "tim_nhom"]
    cuoc = luu_tru.cuoc_hop_gan_nhat(db)
    assert (cuoc["tom_tat"], cuoc["nguon_ai"], cuoc["so_luot_ai"], cuoc["trang_thai"]) == (
        "Tóm tắt của Giám đốc", "gemini", 5, "xong")
    assert {b["vai"] for b in luu_tru.ban_tin_cua(db, cuoc["id"])} >= {
        "phan_tich", "san_khach", "noi_dung", "cham_soc_khach", "rui_ro", "giam_doc"}
    assert len(de_xuat_cua(db, cuoc["id"], "cho_duyet")) == 3                  # trần số đề xuất chờ duyệt
    hoan = de_xuat_cua(db, cuoc["id"], "hoan")
    assert hoan and all(h["ly_do"] for h in hoan)


def test_risk_officer_blocks_violating_ai_proposals_with_a_reason(db, tmp_path):
    bo_ai = AIGia({"noi_dung": vai(DX_GIAM_GIA, DX_KHONG_SO, DX_MAU_OK), "giam_doc": giam_doc()})
    hop_sang(db, tmp_path, bo_ai)
    chan = {d["tieu_de"]: d for d in de_xuat_cua(db, luu_tru.cuoc_hop_gan_nhat(db)["id"], "bi_chan")}
    assert "giá" in chan["Mẫu giảm giá sốc"]["ly_do"] and "số liệu" in chan["Nghĩ thêm"]["ly_do"]
    assert "Mẫu nhấn mạnh 2K 240Hz" not in chan


def test_blocked_ai_proposal_can_be_fixed_in_round_two(db, tmp_path):
    bo_ai = AIGia({"noi_dung": vai(DX_GIA_SAI), "sua:noi_dung": vai(DX_GIA_DA_SUA), "giam_doc": giam_doc()})
    hop_sang(db, tmp_path, bo_ai)
    cuoc = luu_tru.cuoc_hop_gan_nhat(db)
    trang = [(d["tieu_de"], d["trang_thai"]) for d in de_xuat_cua(db, cuoc["id"])]
    assert ("Mẫu giá cụ thể", "bi_chan") in trang
    assert any(t == "Mẫu giá cụ thể" and s != "bi_chan" for t, s in trang)
    assert any(b["vong"] == 2 for b in luu_tru.ban_tin_cua(db, cuoc["id"]))


def test_a_proposal_that_stays_blocked_after_round_two_stays_blocked(db, tmp_path):
    bo_ai = AIGia({"noi_dung": vai(DX_GIA_SAI), "sua:noi_dung": vai(DX_GIA_SAI), "giam_doc": giam_doc()})
    hop_sang(db, tmp_path, bo_ai)
    trang = [d["trang_thai"] for d in de_xuat_cua(db, luu_tru.cuoc_hop_gan_nhat(db)["id"]) if d["tieu_de"] == "Mẫu giá cụ thể"]
    assert trang and set(trang) == {"bi_chan"}


def test_a_role_that_replies_garbage_does_not_stop_the_meeting(db, tmp_path):
    bo_ai = AIGia({"phan_tich": "không phải json", "san_khach": vai(DX_NHOM), "giam_doc": giam_doc()})
    kq = hop_sang(db, tmp_path, bo_ai)
    ban_tin = luu_tru.ban_tin_cua(db, kq["id"])
    assert kq["trang_thai"] == "xong"
    assert any(b["vai"] == "phan_tich" and "không đọc được" in b["noi_dung"] for b in ban_tin)
    assert any(d["nguon"] == "ai" for d in de_xuat_cua(db, kq["id"]))


def test_ai_running_out_mid_meeting_falls_back_to_the_rules(db, tmp_path):
    kq = hop_sang(db, tmp_path, AIGia({"phan_tich": vai(), "san_khach": vai(DX_NHOM)}))       # các vai sau + Giám đốc: hết lượt
    assert kq["trang_thai"] == "xong" and kq["so_cho_duyet"] >= 1
    assert luu_tru.cuoc_hop_gan_nhat(db)["so_luot_ai"] == 2


def test_prompts_never_contain_the_shop_phone_or_the_sellers_name(db, tmp_path):
    bo_ai = AIGia({"phan_tich": vai(), "san_khach": vai(), "noi_dung": vai(), "cham_soc_khach": vai(), "giam_doc": giam_doc()})
    hop_sang(db, tmp_path, bo_ai)
    dem_prompt = bo_ai.prompts
    assert dem_prompt
    for he_thong, nguoi_dung in dem_prompt:
        tat_ca = he_thong + nguoi_dung
        assert SDT_SHOP not in tat_ca and SDT_SHOP.replace(" ", "") not in tat_ca and NGUOI_BAN not in tat_ca


def test_roles_are_told_which_proposals_already_exist_and_to_write_with_diacritics(db, tmp_path):
    bo_ai = AIGia({"phan_tich": vai(), "san_khach": vai(), "noi_dung": vai(), "cham_soc_khach": vai(), "giam_doc": giam_doc()})
    hop_sang(db, tmp_path, bo_ai)
    he_thong, nguoi_dung = bo_ai.prompts[0]
    assert "Ghi khách gọi / nhắn / mua mỗi tối" in nguoi_dung and "de_xuat_da_co" in nguoi_dung
    assert "CÓ DẤU" in he_thong


# ---------- mỗi ngày một cuộc họp, không lặp đề xuất ----------
def test_one_meeting_per_day_unless_forced(db, tmp_path):
    a = hop_sang(db, tmp_path, AIGia(het_luot=True))
    b = hop_sang(db, tmp_path, AIGia(het_luot=True))
    c = hop_sang(db, tmp_path, AIGia(het_luot=True), ep=True)
    assert b["da_co"] is True and b["id"] == a["id"] and c["id"] != a["id"] and c["da_co"] is False


def test_pending_proposals_are_capped_overall_and_never_repeated(db, tmp_path):
    hop_sang(db, tmp_path, AIGia(het_luot=True))
    hop_sang(db, tmp_path, AIGia(het_luot=True), ep=True)
    cho = luu_tru.liet_ke_de_xuat(db, trang_thai="cho_duyet")
    assert len(cho) == 3 and len({(d["loai"], d["tieu_de"]) for d in cho}) == 3


def test_a_decided_proposal_makes_room_for_new_ones(db, tmp_path):
    hop_sang(db, tmp_path, AIGia(het_luot=True))
    dau = luu_tru.liet_ke_de_xuat(db, trang_thai="cho_duyet")
    luu_tru.quyet_dinh(db, dau[0]["id"], "tu_choi", "không cần", HOM_NAY)
    hop_sang(db, tmp_path, AIGia(het_luot=True), ep=True)
    sau = luu_tru.liet_ke_de_xuat(db, trang_thai="cho_duyet")
    assert len(sau) == 3 and dau[0]["id"] not in {d["id"] for d in sau}
    assert (dau[0]["loai"], dau[0]["tieu_de"]) not in {(d["loai"], d["tieu_de"]) for d in sau}   # bị từ chối thì không đề xuất lại ngay


def test_the_director_may_write_indices_as_text_or_floats(db, tmp_path):
    quyet = [{"so_de_xuat": "1", "quyet_dinh": "chap_nhan", "ly_do": "ổn"},
             {"so_de_xuat": 2.0, "quyet_dinh": "chap_nhan", "ly_do": "ổn"}]
    kq = hop_sang(db, tmp_path, AIGia({"giam_doc": {"tom_tat": "Tóm tắt", "quyet_dinh": quyet}}))
    assert kq["so_cho_duyet"] == 2


def test_an_empty_decision_list_falls_back_to_priority_order_but_keeps_the_summary(db, tmp_path):
    kq = hop_sang(db, tmp_path, AIGia({"giam_doc": {"tom_tat": "Tóm tắt của Giám đốc", "quyet_dinh": []}}))
    assert kq["so_cho_duyet"] == 3 and luu_tru.cuoc_hop(db, kq["id"])["tom_tat"] == "Tóm tắt của Giám đốc"


def test_round_two_does_not_save_the_same_revision_twice(db, tmp_path):
    bo_ai = AIGia({"noi_dung": vai(DX_GIA_SAI), "sua:noi_dung": vai(DX_GIA_DA_SUA, DX_GIA_DA_SUA), "giam_doc": giam_doc()})
    kq = hop_sang(db, tmp_path, bo_ai)
    sua = [d for d in de_xuat_cua(db, kq["id"]) if d["tieu_de"] == "Mẫu giá cụ thể" and d["trang_thai"] != "bi_chan"]
    assert len(sua) == 1


def test_a_setup_failure_is_recorded_as_a_failed_meeting_not_left_running(db, tmp_path, monkeypatch):
    def hong(*_, **__):
        raise RuntimeError("CSDL đang khóa")
    monkeypatch.setattr(luu_tru, "ghi_bat_dau_quan_sat", hong)
    with pytest.raises(RuntimeError):
        hop_sang(db, tmp_path, AIGia(het_luot=True))
    assert luu_tru.cuoc_hop_gan_nhat(db)["trang_thai"] == "loi"


def test_ctrl_c_during_a_meeting_is_recorded_too(db, tmp_path, monkeypatch):
    def ngat(*_, **__):
        raise KeyboardInterrupt
    monkeypatch.setattr(luu_tru, "ghi_bat_dau_quan_sat", ngat)
    with pytest.raises(KeyboardInterrupt):
        hop_sang(db, tmp_path, AIGia(het_luot=True))
    assert luu_tru.cuoc_hop_gan_nhat(db)["trang_thai"] == "loi"


def test_an_unwritable_report_folder_does_not_stop_the_meeting(db, tmp_path, monkeypatch):
    def day(*_, **__):
        raise OSError("đĩa đầy")
    monkeypatch.setattr(hop.bao_cao, "luu", day)
    assert hop_sang(db, tmp_path, AIGia(het_luot=True))["trang_thai"] == "xong"


def test_the_end_time_comes_from_the_real_clock(db, tmp_path):
    kq = hop_sang(db, tmp_path, AIGia(het_luot=True), dong_ho=lambda: datetime(2026, 10, 24, 7, 12))
    assert luu_tru.cuoc_hop(db, kq["id"])["ket_thuc"] == "2026-10-24 07:12:00"


def test_context_for_the_ai_keeps_only_whitelisted_fields_and_scrubs_numbers():
    so = su_that.SuThat(thong_tin=(("Địa chỉ", "64 Cầu Diễn, Hà Nội"), ("SĐT", "0902 189 751"), ("Hotline", "1900 1234"),
                                   ("Số điện thoại 2", "0912 345 678"), ("Người bán", NGUOI_BAN),
                                   ("Thanh toán", "Chuyển khoản STK 1234567890123 hoặc tiền mặt khi nhận")),
                        chua_dien=(), co_file=True)
    gui = vai_mod.su_that_cho_ai(so)["da_dien"]
    assert set(gui) == {"Địa chỉ", "Thanh toán"}
    assert "1234567890123" not in gui["Thanh toán"] and "tiền mặt" in gui["Thanh toán"]


class DBTranh(Database):
    """Giả lập hai yêu cầu cùng lúc: ngay sau khi hàm đọc trạng thái, yêu cầu kia đã từ chối đề xuất này"""

    def query(self, sql, params=()):
        rows = super().query(sql, params)
        if sql.startswith("SELECT trang_thai FROM de_xuat"):
            super().execute("UPDATE de_xuat SET trang_thai = 'tu_choi' WHERE id = ?", params)
        return rows


def test_a_stale_decision_does_not_overwrite_a_change_made_in_between(tmp_path):
    db = DBTranh(str(tmp_path / "t.db"))
    luu_tru.ensure_schema(db)
    cuoc = luu_tru.tao_cuoc_hop(db, "2026-10-24", datetime(2026, 10, 24, 7, 0))
    dx_id = luu_tru.them_de_xuat(db, cuoc, chuan_hoa("san_khach", dx("khac", "Việc A", "Làm việc A"), HOM_NAY), "luat",
                                 luu_tru.CHO_DUYET, "", datetime(2026, 10, 24, 7, 1))
    with pytest.raises(ValueError, match="nơi khác"):
        luu_tru.quyet_dinh(db, dx_id, "da_duyet", "", HOM_NAY)
    assert luu_tru.liet_ke_de_xuat(db)[0]["trang_thai"] == "tu_choi"


# ---------- bạn duyệt / từ chối ----------
def test_decisions_follow_the_allowed_transitions(db, tmp_path):
    hop_sang(db, tmp_path, AIGia({"noi_dung": vai(DX_GIAM_GIA), "giam_doc": giam_doc()}))
    chan = luu_tru.liet_ke_de_xuat(db, trang_thai="bi_chan")[0]
    cho = luu_tru.liet_ke_de_xuat(db, trang_thai="cho_duyet")[0]
    luu_tru.quyet_dinh(db, cho["id"], "da_duyet", "ok", HOM_NAY)
    assert luu_tru.liet_ke_de_xuat(db, trang_thai="da_duyet")[0]["ghi_chu_chu_shop"] == "ok"
    with pytest.raises(ValueError):
        luu_tru.quyet_dinh(db, cho["id"], "tu_choi", "", HOM_NAY)           # đã duyệt rồi: chỉ còn 'đã làm'
    luu_tru.quyet_dinh(db, cho["id"], "da_lam", "", HOM_NAY)
    with pytest.raises(ValueError):
        luu_tru.quyet_dinh(db, chan["id"], "da_duyet", "", HOM_NAY)         # Kiểm soát rủi ro đã chặn: không duyệt được
    with pytest.raises(ValueError):
        luu_tru.quyet_dinh(db, cho["id"], "xoa_het", "", HOM_NAY)
    with pytest.raises(LookupError):
        luu_tru.quyet_dinh(db, 999_999, "da_duyet", "", HOM_NAY)


# ---------- chế độ quan sát ----------
def test_observation_mode_counts_days_from_the_first_meeting(db, tmp_path):
    assert luu_tru.che_do(db, HOM_NAY, 7) == {"ten": "quan_sat", "ngay": 0, "tong": 7, "xong": False}
    hop_sang(db, tmp_path, AIGia(het_luot=True))
    hop_sang(db, tmp_path, AIGia(het_luot=True), ep=True)                    # họp lại không làm đổi ngày bắt đầu
    assert luu_tru.che_do(db, HOM_NAY, 7)["ngay"] == 1
    assert luu_tru.che_do(db, HOM_NAY + timedelta(days=3), 7)["ngay"] == 4
    assert luu_tru.che_do(db, HOM_NAY + timedelta(days=9), 7) == {"ten": "quan_sat", "ngay": 10, "tong": 7, "xong": True}


# ---------- Giai đoạn 3: công ty tự làm (chỉ khi công tắc bật VÀ đã hết thời gian quan sát) ----------
def them_mau_xau(db, so_mau=12):
    """Một sản phẩm có `so_mau` mẫu; mẫu đầu bị Facebook từ chối gần hết nên luật đề xuất tắt nó. Trả về id các mẫu"""
    san_pham = db.add_product(name="MSI G274QPF", price="2.500.000đ")
    ids = [db.add_variant(san_pham, f"Màn MSI G274QPF bản {i}, giá {{giá}}", "") for i in range(so_mau)]
    them_binh_luan(db, ngay(5), 25, 25, variant_id=ids[0], tt_binh_luan="Bị từ chối · đã xóa")
    return ids


def het_quan_sat(db):
    db.set_setting("cong_ty_bat_dau", (HOM_NAY - timedelta(days=8)).strftime("%Y-%m-%d"))


def de_xuat_tat_mau(db):
    return [d for d in de_xuat_cua(db, luu_tru.cuoc_hop_gan_nhat(db)["id"]) if d["loai"] == "bat_tat_mau"]


def dang_bat(db):
    return {v["id"] for v in db.variants(active_only=True)}


def test_the_switch_only_counts_after_observation_is_over(db):
    assert not luu_tru.duoc_tu_lam(db, HOM_NAY, 7)
    luu_tru.dat_tu_lam(db, True)
    assert luu_tru.tu_lam_dang_bat(db) and not luu_tru.duoc_tu_lam(db, HOM_NAY, 7)          # chưa họp lần nào
    luu_tru.ghi_bat_dau_quan_sat(db, HOM_NAY.strftime("%Y-%m-%d"))
    assert not luu_tru.duoc_tu_lam(db, HOM_NAY + timedelta(days=5), 7)
    assert luu_tru.duoc_tu_lam(db, HOM_NAY + timedelta(days=6), 7)                          # ngày thứ 7
    luu_tru.dat_tu_lam(db, False)
    assert not luu_tru.tu_lam_dang_bat(db) and not luu_tru.duoc_tu_lam(db, HOM_NAY + timedelta(days=6), 7)


def test_with_the_switch_off_the_company_only_proposes(db, tmp_path):
    ids = them_mau_xau(db)
    het_quan_sat(db)
    hop_sang(db, tmp_path, AIGia(het_luot=True))
    tat = de_xuat_tat_mau(db)
    assert [d["trang_thai"] for d in tat] == ["cho_duyet"] and json.loads(tat[0]["tham_so"])["variant_ids"] == [ids[0]]
    assert dang_bat(db) == set(ids) and hanh_dong.liet_ke(db) == []


def test_with_the_switch_on_but_still_observing_nothing_is_done(db, tmp_path):
    ids = them_mau_xau(db)
    luu_tru.dat_tu_lam(db, True)
    hop_sang(db, tmp_path, AIGia(het_luot=True))                                            # ngày 1 trong 7 ngày quan sát
    assert [d["trang_thai"] for d in de_xuat_tat_mau(db)] == ["cho_duyet"] and dang_bat(db) == set(ids)


def test_with_the_switch_on_and_observation_over_the_company_does_its_own_rule_proposals(db, tmp_path):
    ids = them_mau_xau(db)
    luu_tru.dat_tu_lam(db, True)
    het_quan_sat(db)
    hop_sang(db, tmp_path, AIGia(het_luot=True))
    tat = de_xuat_tat_mau(db)[0]
    assert tat["trang_thai"] == "da_lam" and "công tắc" in tat["ghi_chu_chu_shop"]
    assert dang_bat(db) == set(ids) - {ids[0]}
    assert [n["de_xuat_id"] for n in hanh_dong.liet_ke(db)] == [tat["id"]]
    cuoc = luu_tru.cuoc_hop_gan_nhat(db)
    assert "tự làm 1 việc" in cuoc["tom_tat"]
    assert any("Đã tự làm" in b["noi_dung"] for b in luu_tru.ban_tin_cua(db, cuoc["id"]))


def test_proposals_written_by_the_ai_are_never_carried_out_by_the_company(db, tmp_path):
    ids = them_mau_xau(db)
    luu_tru.dat_tu_lam(db, True)
    het_quan_sat(db)
    ai_viet = {**dx("bat_tat_mau", "Tắt mẫu số 3 cho gọn", f"Tắt mẫu #{ids[3]} ở tab Sản phẩm"),
               "tham_so": json.dumps({"hanh_dong": "tat_mau", "variant_ids": [ids[3]]})}      # AI cố gắn việc tự làm
    hop_sang(db, tmp_path, AIGia({"noi_dung": vai(ai_viet), "giam_doc": giam_doc()}))
    cua_ai = [d for d in de_xuat_tat_mau(db) if d["nguon"] == "ai"]
    assert cua_ai and all(d["tham_so"] == "" and d["trang_thai"] != "da_lam" for d in cua_ai)
    assert ids[3] in dang_bat(db)


def test_the_company_respects_a_recent_undo_when_acting_on_its_own(db, tmp_path):
    ids = them_mau_xau(db)
    hanh_dong.ensure_schema(db)
    tham_so = json.dumps({"hanh_dong": "tat_mau", "variant_ids": [ids[0]]})
    nhat_ky_id = hanh_dong.thuc_hien(db, 1, tham_so, "luat", datetime(2026, 10, 24, 6, 0))
    hanh_dong.hoan_tac(db, nhat_ky_id, datetime(2026, 10, 24, 6, 5))                        # chủ shop bật lại mẫu này
    luu_tru.dat_tu_lam(db, True)
    het_quan_sat(db)
    hop_sang(db, tmp_path, AIGia(het_luot=True))
    assert [d["trang_thai"] for d in de_xuat_tat_mau(db)] == ["cho_duyet"] and dang_bat(db) == set(ids)
    ban_tin = luu_tru.ban_tin_cua(db, luu_tru.cuoc_hop_gan_nhat(db)["id"])
    assert any("Chưa tự làm được" in b["noi_dung"] and "hoàn tác" in b["noi_dung"] for b in ban_tin)


def test_a_database_from_phase_two_gets_the_new_column(tmp_path):
    cu = Database(str(tmp_path / "cu.db"))
    cu.execute("CREATE TABLE de_xuat (id INTEGER PRIMARY KEY AUTOINCREMENT, cuoc_hop_id INTEGER NOT NULL, vai TEXT NOT NULL, "
               "loai TEXT NOT NULL, tieu_de TEXT NOT NULL, noi_dung TEXT NOT NULL, vi_sao TEXT NOT NULL, "
               "ky_vong TEXT NOT NULL DEFAULT '', rui_ro TEXT NOT NULL DEFAULT '', ngay_do TEXT NOT NULL, nguon TEXT NOT NULL, "
               "trang_thai TEXT NOT NULL, ly_do TEXT NOT NULL DEFAULT '', quyet_luc TEXT, "
               "ghi_chu_chu_shop TEXT NOT NULL DEFAULT '', tao_luc TEXT NOT NULL)")
    cu.execute("INSERT INTO de_xuat (cuoc_hop_id, vai, loai, tieu_de, noi_dung, vi_sao, ngay_do, nguon, trang_thai, tao_luc) "
               "VALUES (1, 'noi_dung', 'khac', 'Cũ', 'Đề xuất cũ', 'x', '2026-10-30', 'luat', 'cho_duyet', '2026-10-24 07:00:00')")
    luu_tru.ensure_schema(cu)
    luu_tru.ensure_schema(cu)                                                                # chạy hai lần cũng không hỏng
    assert cu.query("SELECT tieu_de, tham_so FROM de_xuat") == [{"tieu_de": "Cũ", "tham_so": ""}]


def test_a_limit_stops_the_automatic_action_and_the_proposal_waits_for_the_owner(db, tmp_path):
    ids = them_mau_xau(db, so_mau=10)                                                       # tắt 1 mẫu thì còn 9 < 10
    luu_tru.dat_tu_lam(db, True)
    het_quan_sat(db)
    hop_sang(db, tmp_path, AIGia(het_luot=True))
    assert [d["trang_thai"] for d in de_xuat_tat_mau(db)] == ["cho_duyet"] and dang_bat(db) == set(ids)
    ban_tin = luu_tru.ban_tin_cua(db, luu_tru.cuoc_hop_gan_nhat(db)["id"])
    assert any("Chưa tự làm được" in b["noi_dung"] and "10" in b["noi_dung"] for b in ban_tin)


# ---------- vai Nội dung: AI viết phần mở đầu bình luận, code ghép giá / SĐT / địa chỉ ----------
MAU_NGUOI_VIET = "MSI G2712F – 27 inch 2K · 180Hz · 1ms – Rapid IPS · Adaptive-Sync · HDR 400\nDũng-0902189751-64 Cầu Diễn"
MO_DAU_AI = "Mã màn: MSI G2712F\nThông số: 27 inch 2K · 180Hz · 1ms\nCông nghệ: Rapid IPS · Adaptive-Sync"


def them_san_pham_co_mau(db):
    pid = db.add_product(name="MSI G2712F 27 inch", price="2.500.000đ")
    db.add_variant(pid, MAU_NGUOI_VIET, "")
    return pid


def mau_ai_cua(db, cuoc_id):
    return [d for d in de_xuat_cua(db, cuoc_id) if d["nguon"] == "mau_ai"]


def test_the_content_role_proposes_new_comments_that_wait_for_the_owner_while_observing(db, tmp_path):
    pid = them_san_pham_co_mau(db)
    bo_ai = AIGia({"viet_mau": {"mo_dau": [MO_DAU_AI]}})
    hop_sang(db, tmp_path, bo_ai)
    cuoc = luu_tru.cuoc_hop_gan_nhat(db)
    dx = mau_ai_cua(db, cuoc["id"])
    assert [d["trang_thai"] for d in dx] == ["cho_duyet"] and "viet_mau" in bo_ai.da_hoi
    assert json.loads(dx[0]["tham_so"]) == {"hanh_dong": "them_mau", "san_pham_id": pid, "mo_dau": [MO_DAU_AI]}
    assert MO_DAU_AI in dx[0]["noi_dung"] and SDT_SHOP not in dx[0]["noi_dung"]
    assert len(db.variants(pid)) == 1                                         # chưa có gì tự thêm vào bot
    assert any(b["vai"] == "noi_dung" and "Đã viết 1 thẻ thông số" in b["noi_dung"] for b in luu_tru.ban_tin_cua(db, cuoc["id"]))


def test_with_the_switch_on_and_observation_over_the_new_comments_go_live_with_the_fixed_part(db, tmp_path):
    pid = them_san_pham_co_mau(db)
    luu_tru.dat_tu_lam(db, True)
    het_quan_sat(db)
    kq = hop_sang(db, tmp_path, AIGia({"viet_mau": {"mo_dau": [MO_DAU_AI]}}))
    dx = mau_ai_cua(db, kq["id"])
    assert [d["trang_thai"] for d in dx] == ["da_lam"]
    moi = [v for v in db.variants(pid) if v["text"] != MAU_NGUOI_VIET]
    assert len(moi) == 1 and moi[0]["active"] == 1 and moi[0]["text"].startswith(MO_DAU_AI)
    assert moi[0]["text"].splitlines()[-1] == f"Dũng-{SDT_SHOP.replace(' ', '')}-64 Cầu Diễn"      # MỘT dòng liên hệ, không họ tên đầy đủ
    assert "{giá}" not in moi[0]["text"] and "đã qua sử dụng" not in moi[0]["text"] and NGUOI_BAN not in moi[0]["text"]
    assert "tự làm 1 việc" in luu_tru.cuoc_hop_gan_nhat(db)["tom_tat"]
    assert [n["hanh_dong"] for n in hanh_dong.liet_ke(db)] == ["them_mau"]


def test_new_comments_are_not_piled_up_while_the_previous_ones_wait_for_the_owner(db, tmp_path):
    them_san_pham_co_mau(db)
    hop_sang(db, tmp_path, AIGia({"viet_mau": {"mo_dau": [MO_DAU_AI]}}))
    lan_hai = AIGia({"viet_mau": {"mo_dau": [MO_DAU_AI]}})
    kq = hop_sang(db, tmp_path, lan_hai, ep=True)
    assert "viet_mau" not in lan_hai.da_hoi and mau_ai_cua(db, kq["id"]) == []
    assert any(b["vai"] == "noi_dung" and "chờ bạn duyệt" in b["noi_dung"] for b in luu_tru.ban_tin_cua(db, kq["id"]))


def test_unsafe_ai_text_never_becomes_a_proposal_and_the_reason_is_in_the_minutes(db, tmp_path):
    them_san_pham_co_mau(db)
    xau = {"mo_dau": [MO_DAU_AI + " Gọi 0912 345 678 nhé.", "Màn đẹp."]}
    kq = hop_sang(db, tmp_path, AIGia({"viet_mau": xau}))
    assert mau_ai_cua(db, kq["id"]) == []
    ban_tin = [b["noi_dung"] for b in luu_tru.ban_tin_cua(db, kq["id"]) if b["vai"] == "noi_dung"]
    assert any("loại 2" in b for b in ban_tin)


def test_no_new_comment_is_asked_for_when_there_is_no_ai_left(db, tmp_path):
    them_san_pham_co_mau(db)
    bo_ai = AIGia({"viet_mau": {"mo_dau": [MO_DAU_AI]}}, het_luot=True)
    kq = hop_sang(db, tmp_path, bo_ai)
    assert bo_ai.da_hoi == [] and mau_ai_cua(db, kq["id"]) == []


def test_a_fact_sheet_without_an_address_stops_the_automatic_step_and_the_proposal_waits(db, tmp_path):
    pid = them_san_pham_co_mau(db)
    luu_tru.dat_tu_lam(db, True)
    het_quan_sat(db)
    kq = hop_sang(db, tmp_path, AIGia({"viet_mau": {"mo_dau": [MO_DAU_AI]}}), co_dia_chi=False)
    assert [d["trang_thai"] for d in mau_ai_cua(db, kq["id"])] == ["cho_duyet"] and len(db.variants(pid)) == 1
    assert any("Chưa tự làm được" in b["noi_dung"] and "Địa chỉ" in b["noi_dung"] for b in luu_tru.ban_tin_cua(db, kq["id"]))


# ---------- vai Săn khách: AI đề xuất từ khóa tìm nhóm mới ----------
TU_KHOA_AI = "thanh lý màn hình cũ Cầu Giấy Hà Nội"


def tu_khoa_cua(db, cuoc_id):
    return [d for d in de_xuat_cua(db, cuoc_id) if d["nguon"] == "tu_khoa_ai"]


def test_the_hunting_role_proposes_extra_search_keywords_that_wait_for_the_owner(db, tmp_path):
    bo_ai = AIGia({"tim_nhom": {"tu_khoa": [TU_KHOA_AI]}})
    hop_sang(db, tmp_path, bo_ai)
    cuoc = luu_tru.cuoc_hop_gan_nhat(db)
    dx = tu_khoa_cua(db, cuoc["id"])
    assert [d["trang_thai"] for d in dx] == ["cho_duyet"] and "tim_nhom" in bo_ai.da_hoi
    assert json.loads(dx[0]["tham_so"]) == {"hanh_dong": "them_tu_khoa", "tu_khoa": [TU_KHOA_AI]}
    assert nhom_ai.tu_khoa_dang_dung(db) == []                                # chưa có gì tự thêm cho bot
    assert any(b["vai"] == "san_khach" and "Đã chọn 1 từ khóa" in b["noi_dung"] for b in luu_tru.ban_tin_cua(db, cuoc["id"]))


def test_with_the_switch_on_and_observation_over_the_keywords_go_to_the_bot(db, tmp_path):
    luu_tru.dat_tu_lam(db, True)
    het_quan_sat(db)
    kq = hop_sang(db, tmp_path, AIGia({"tim_nhom": {"tu_khoa": [TU_KHOA_AI]}}))
    assert [d["trang_thai"] for d in tu_khoa_cua(db, kq["id"])] == ["da_lam"]
    assert nhom_ai.tu_khoa_dang_dung(db) == [TU_KHOA_AI] and "tự làm 1 việc" in luu_tru.cuoc_hop_gan_nhat(db)["tom_tat"]


def test_unsafe_keywords_never_become_a_proposal(db, tmp_path):
    kq = hop_sang(db, tmp_path, AIGia({"tim_nhom": {"tu_khoa": ["mua bán màn hình HCM", "linh kiện PC Hà Nội"]}}))
    assert tu_khoa_cua(db, kq["id"]) == []
    assert any(b["vai"] == "san_khach" and "loại 2" in b["noi_dung"] for b in luu_tru.ban_tin_cua(db, kq["id"]))


def test_keywords_are_not_piled_up_while_the_previous_ones_wait_for_the_owner(db, tmp_path):
    hop_sang(db, tmp_path, AIGia({"tim_nhom": {"tu_khoa": [TU_KHOA_AI]}}))
    lan_hai = AIGia({"tim_nhom": {"tu_khoa": ["mua bán màn hình Đống Đa Hà Nội"]}})
    kq = hop_sang(db, tmp_path, lan_hai, ep=True)
    assert "tim_nhom" not in lan_hai.da_hoi and tu_khoa_cua(db, kq["id"]) == []


def test_keywords_already_in_the_config_are_not_proposed_again(db, tmp_path, monkeypatch):
    monkeypatch.setattr(CFG_HOP, "GROUP_SEARCH_QUERIES", (TU_KHOA_AI,), raising=False)
    kq = hop_sang(db, tmp_path, AIGia({"tim_nhom": {"tu_khoa": [TU_KHOA_AI]}}))
    assert tu_khoa_cua(db, kq["id"]) == []


def test_a_crash_while_writing_comments_does_not_stop_the_meeting(db, tmp_path, monkeypatch):
    them_san_pham_co_mau(db)

    def hong(*a, **kw):
        raise RuntimeError("AI sập giữa chừng")

    monkeypatch.setattr("cong_ty.mau_ai.soan_mau", hong)
    kq = hop_sang(db, tmp_path, AIGia({"viet_mau": {"mo_dau": [MO_DAU_AI]}}))
    assert kq["trang_thai"] == "xong" and mau_ai_cua(db, kq["id"]) == []
    assert any("lỗi" in b["noi_dung"] for b in luu_tru.ban_tin_cua(db, kq["id"]) if b["vai"] == "noi_dung")
