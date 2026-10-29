"""Từ khóa tìm nhóm do AI đề xuất: chỉ nhóm màn hình ở Hà Nội; mỗi từ khóa qua rào chắn bằng code; có hạn mức, nhật ký, hoàn tác.
Bot đọc các từ khóa này (bảng settings) khi tìm nhóm mới và vẫn áp bộ lọc nhóm riêng của nó."""
import json
from datetime import datetime, timedelta

import pytest

from cong_ty import ai, hanh_dong, nhom_ai
from modules.db import Database

BAY_GIO = datetime(2026, 10, 24, 7, 30)
GOC = ("màn hình máy tính Hà Nội", "mua bán màn hình Hà Nội", "màn hình cũ Hà Nội")
TU_KHOA_TOT = "thanh lý màn hình cũ Cầu Giấy Hà Nội"


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "t.db"))
    hanh_dong.ensure_schema(database)
    return database


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


def ghi_nhat_ky(db, tu_khoa, luc="2026-10-24 06:00:00", hoan_tac_luc=None):
    db.execute("INSERT INTO nhat_ky_hanh_dong (de_xuat_id, hanh_dong, doi_tuong, luc, hoan_tac_luc) VALUES (?, ?, ?, ?, ?)",
               (1, nhom_ai.THEM_TU_KHOA, json.dumps({"tu_khoa": tu_khoa}, ensure_ascii=False), luc, hoan_tac_luc))


# ---------- rào chắn cho từng từ khóa ----------
def test_a_good_keyword_passes():
    assert nhom_ai.kiem_tra_tu_khoa(TU_KHOA_TOT, list(GOC)) == ()


@pytest.mark.parametrize("tu_khoa, tu_chinh", [
    ("màn hình", "từ"),
    ("thanh lý màn hình cũ ở các quận nội thành Hà Nội giá rẻ nhất hiện nay", "từ"),
    ("mua bán màn hình HCM", "Hà Nội"),
    ("mua bán màn hình Sài Gòn Hà Nội", "tỉnh"),
    ("linh kiện máy tính Hà Nội", "màn hình"),
    ("màn hình laptop cũ Hà Nội", "laptop"),
    ("mua bán PC gaming màn hình Hà Nội", "PC"),
    ("thanh ly man hinh cu Ha Noi", "dấu"),
    ("màn hình Hà Nội giá rẻ", "giá"),
    ("mua bán màn hình Hà Nam Hà Nội", "tỉnh"),
    ("thanh lý màn hình Hưng Yên Hà Nội", "tỉnh"),
    ("màn hình Hà Nội 2024", "chữ"),
    ("màn hình Hà Nội!!!", "chữ"),
    ("xem màn hình Hà Nội tại facebook.com/groups", "chữ"),
    ("màn hình cũ Hà Nội", "trùng"),
    ("MÀN HÌNH   MÁY TÍNH hà nội", "trùng"),
])
def test_bad_keywords_are_refused(tu_khoa, tu_chinh):
    van_de = nhom_ai.kiem_tra_tu_khoa(tu_khoa, list(GOC))
    assert van_de and any(tu_chinh in v for v in van_de), (tu_khoa, van_de)


def test_hidden_characters_cannot_smuggle_a_duplicate_or_a_link():
    assert nhom_ai.kiem_tra_tu_khoa("màn​ hình cũ Hà Nội", list(GOC))


# ---------- soạn từ khóa ----------
def test_composing_keeps_good_keywords_and_explains_the_refused_ones(db):
    bo_ai = AIGia({"tu_khoa": [TU_KHOA_TOT, "mua bán HCM", "dân văn phòng cần màn hình cũ Hà Nội"]})
    kq = nhom_ai.soan_tu_khoa(db, GOC, bo_ai, BAY_GIO)
    assert kq.tu_khoa == (TU_KHOA_TOT, "dân văn phòng cần màn hình cũ Hà Nội") and kq.nguon == "gemini"
    assert len(kq.bi_loai) == 1 and "loại 1" in kq.ghi_chu


def test_what_is_sent_to_the_ai_is_only_public_search_text(db):
    bo_ai = AIGia({"tu_khoa": [TU_KHOA_TOT]})
    nhom_ai.soan_tu_khoa(db, GOC, bo_ai, BAY_GIO)
    gui = " ".join(" ".join(p[:2]) for p in bo_ai.prompts)
    assert "màn hình cũ Hà Nội" in gui and "0902" not in gui and "Dũng" not in gui


@pytest.mark.parametrize("tra_loi", [None, "không phải json", {"tu_khoa": "một chuỗi"}, {"tu_khoa": [1, None]}, {}])
def test_a_bad_or_missing_ai_reply_gives_nothing_and_a_reason(db, tra_loi):
    kq = nhom_ai.soan_tu_khoa(db, GOC, AIGia(tra_loi), BAY_GIO)
    assert kq.tu_khoa == () and kq.ghi_chu


def test_it_does_not_ask_the_ai_when_there_is_no_ai_left_or_no_room(db):
    bo_ai = AIGia({"tu_khoa": [TU_KHOA_TOT]}, het_luot=True)
    assert nhom_ai.soan_tu_khoa(db, GOC, bo_ai, BAY_GIO).tu_khoa == () and bo_ai.prompts == []
    ghi_nhat_ky(db, ["a"] * nhom_ai.MAX_TU_KHOA_MOI_NGAY)
    bo_ai = AIGia({"tu_khoa": [TU_KHOA_TOT]})
    assert nhom_ai.soan_tu_khoa(db, GOC, bo_ai, BAY_GIO).tu_khoa == () and bo_ai.prompts == []


def test_the_total_of_ai_keywords_is_capped(db):
    nhom_ai.them_vao_setting(db, [f"mua bán màn hình quận {i} Hà Nội" for i in range(nhom_ai.MAX_TU_KHOA_DANG_DUNG)])
    bo_ai = AIGia({"tu_khoa": [TU_KHOA_TOT]})
    kq = nhom_ai.soan_tu_khoa(db, GOC, bo_ai, BAY_GIO)
    assert kq.tu_khoa == () and bo_ai.prompts == [] and "tối đa" in kq.ghi_chu


def test_it_pauses_for_a_week_after_the_owner_undoes_keywords(db):
    ghi_nhat_ky(db, ["x"], luc="2026-10-23 06:00:00", hoan_tac_luc="2026-10-23 09:00:00")
    bo_ai = AIGia({"tu_khoa": [TU_KHOA_TOT]})
    kq = nhom_ai.soan_tu_khoa(db, GOC, bo_ai, BAY_GIO)
    assert kq.tu_khoa == () and bo_ai.prompts == [] and "hoàn tác" in kq.ghi_chu
    het_nghi = BAY_GIO + timedelta(days=nhom_ai.NGAY_NGHI_SAU_HOAN_TAC + 1)
    assert nhom_ai.soan_tu_khoa(db, GOC, AIGia({"tu_khoa": [TU_KHOA_TOT]}), het_nghi).tu_khoa == (TU_KHOA_TOT,)


def test_keywords_already_in_use_are_not_asked_for_again(db):
    nhom_ai.them_vao_setting(db, [TU_KHOA_TOT])
    kq = nhom_ai.soan_tu_khoa(db, GOC, AIGia({"tu_khoa": [TU_KHOA_TOT]}), BAY_GIO)
    assert kq.tu_khoa == () and len(kq.bi_loai) == 1


# ---------- cài đặt mà bot đọc ----------
def test_keywords_are_saved_merged_without_duplicates_and_removed_on_undo(db):
    assert nhom_ai.tu_khoa_dang_dung(db) == []
    nhom_ai.them_vao_setting(db, [TU_KHOA_TOT])
    nhom_ai.them_vao_setting(db, [TU_KHOA_TOT, "dân văn phòng cần màn hình cũ Hà Nội"])
    assert nhom_ai.tu_khoa_dang_dung(db) == [TU_KHOA_TOT, "dân văn phòng cần màn hình cũ Hà Nội"]
    nhom_ai.bo_khoi_setting(db, [TU_KHOA_TOT])
    assert nhom_ai.tu_khoa_dang_dung(db) == ["dân văn phòng cần màn hình cũ Hà Nội"]


def test_a_damaged_setting_is_treated_as_empty_and_never_crashes_the_bot(db):
    db.set_setting(nhom_ai.SETTING, "không phải json")
    assert nhom_ai.tu_khoa_dang_dung(db) == []
    db.set_setting(nhom_ai.SETTING, json.dumps({"a": 1}))
    assert nhom_ai.tu_khoa_dang_dung(db) == []
    db.set_setting(nhom_ai.SETTING, json.dumps(["tốt", 5, None, "màn hình Hà Nội cũ"]))
    assert nhom_ai.tu_khoa_dang_dung(db) == ["tốt", "màn hình Hà Nội cũ"]


# ---------- đề xuất do code dựng ----------
def test_the_proposal_is_built_by_code_with_the_action_and_passes_the_group_rules(db):
    kq = nhom_ai.soan_tu_khoa(db, GOC, AIGia({"tu_khoa": [TU_KHOA_TOT]}), BAY_GIO)
    dx = nhom_ai.de_xuat_tu_ket_qua(kq, BAY_GIO.date())
    assert json.loads(dx.tham_so) == {"hanh_dong": "them_tu_khoa", "tu_khoa": [TU_KHOA_TOT]}
    assert dx.loai == "nhom_moi" and dx.vai == "san_khach" and TU_KHOA_TOT in dx.noi_dung and dx.vi_sao and dx.rui_ro


# ---------- kiểm tra lại lúc thực hiện ----------
def test_carrying_out_checks_everything_again(db):
    assert nhom_ai.chuan_bi_them(db, {"tu_khoa": [TU_KHOA_TOT]}, GOC, BAY_GIO) == [TU_KHOA_TOT]
    for xau in ({"tu_khoa": []}, {"tu_khoa": "x"}, {"tu_khoa": [1]}, {"tu_khoa": ["mua bán HCM"]},
                {"tu_khoa": [TU_KHOA_TOT] * 4}, {}):
        with pytest.raises(nhom_ai.LoiTuKhoa):
            nhom_ai.chuan_bi_them(db, xau, GOC, BAY_GIO)
    with pytest.raises(nhom_ai.LoiTuKhoa, match="trùng"):
        nhom_ai.chuan_bi_them(db, {"tu_khoa": ["màn hình cũ Hà Nội"]}, GOC, BAY_GIO)
