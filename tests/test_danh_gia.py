"""Bộ đánh giá trên dữ liệu thật (danh_gia/): hàm đo đúng, bộ che thông tin không để lọt SĐT, các tầng lấy mẫu phủ kín dữ liệu, và CỔNG HỒI QUY
chạy trên dữ liệu thật (chỉ chạy khi đặt biến môi trường CHAY_DANH_GIA=1 — cần bộ nhãn local trong danh_gia/du_lieu/ và CSDL thật, đọc chỉ đọc)."""
import importlib.util
import math
import os
import random
import re
from types import SimpleNamespace

import pytest

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def nap(ten):
    spec = importlib.util.spec_from_file_location(ten, os.path.join(GOC, "danh_gia", f"{ten}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


xay_mau = nap("xay_mau")
chay = nap("chay_danh_gia")


# ---------- hàm đo ----------
def test_agreement_is_one_for_identical_labels_and_zero_for_unrelated_ones():
    a = ["MUA", "BAN"] * 10
    assert chay.kappa(a, list(a)) == 1.0
    assert chay.kappa(["a"] * 10 + ["b"] * 10, ["a", "b"] * 10) == pytest.approx(0.0)
    assert math.isnan(chay.kappa([], []))


def test_stratum_weights_add_up_to_the_real_size_of_every_stratum():
    tang = {"A": {"tong": 100, "mau": 4}, "B": {"tong": 10, "mau": 2}}
    ds = [{"tang": "A"}, {"tang": "A"}, {"tang": "A"}, {"tang": "B"}]       # một mẫu tầng A và một mẫu tầng B đã bị loại (nhãn bất đồng)
    co_w = chay.trong_so_tang(tang, ds)
    assert sum(m["w"] for m in co_w if m["tang"] == "A") == pytest.approx(100)
    assert sum(m["w"] for m in co_w if m["tang"] == "B") == pytest.approx(10)


def test_a_ratio_with_nothing_to_divide_is_nan_not_a_crash():
    assert math.isnan(chay.ti_le(1, 0))
    assert chay.phan_tram(float("nan")) == "—"


def _ds_gia(rng, n_a=60, n_b=20):
    """Hai tầng: A rất nhiều bài, đúng 80%; B ít bài, đúng 30% — nếu bỏ trọng số thì kết quả lệch hẳn"""
    ds = [{"tang": "A", "w": 1000 / n_a, "dung": rng.random() < 0.8} for _ in range(n_a)]
    ds += [{"tang": "B", "w": 100 / n_b, "dung": rng.random() < 0.3} for _ in range(n_b)]
    return ds


def test_bootstrap_interval_contains_the_estimate_and_is_reproducible():
    ds = _ds_gia(random.Random(1))
    ham = lambda s: chay.ti_le(chay.tong_w(s, lambda m: m["dung"]), chay.tong_w(s, lambda m: True))    # noqa: E731
    gt = ham(ds)
    lo, hi = chay.bootstrap(ds, ham, 300)
    assert lo <= gt <= hi and 0.6 < gt < 0.9                                  # bị tầng A chi phối, đúng như trọng số
    assert chay.bootstrap(ds, ham, 300) == (lo, hi)


def test_the_weighted_estimate_differs_from_the_plain_average_when_strata_differ():
    ds = _ds_gia(random.Random(2))
    thuong = sum(m["dung"] for m in ds) / len(ds)
    co_w = chay.ti_le(chay.tong_w(ds, lambda m: m["dung"]), chay.tong_w(ds, lambda m: True))
    assert abs(co_w - thuong) > 0.02


# ---------- chính sách "nên bình luận" ----------
@pytest.mark.parametrize("chu_de, y_dinh, khu_vuc, ha_noi, bat_buoc_ghi_khu_vuc, mong_doi", [
    ("man_hinh", "MUA", "gan", True, True, True),
    ("man_hinh", "MUA", "xa", True, True, False),             # khách ở xa: bỏ, kể cả nhóm Hà Nội
    ("man_hinh", "MUA", "khong_ghi", True, True, True),       # nhóm Hà Nội: không ghi khu vực vẫn bình luận
    ("man_hinh", "MUA", "khong_ghi", False, True, False),     # nhóm toàn quốc + chưa thử nghiệm: bỏ
    ("man_hinh", "MUA", "khong_ghi", False, False, True),     # nhóm toàn quốc + đang thử nghiệm: bình luận
    ("man_hinh", "BAN", "gan", True, True, False),
    ("man_hinh", "KHAC", "gan", True, True, False),
    ("pc", "MUA", "gan", True, True, False),
    ("laptop", "MUA", "gan", True, True, False),
])
def test_comment_policy_truth_table(chu_de, y_dinh, khu_vuc, ha_noi, bat_buoc_ghi_khu_vuc, mong_doi):
    cfg = SimpleNamespace(REGION_REQUIRED_IN_NATIONAL_GROUPS=bat_buoc_ghi_khu_vuc)
    assert chay.nen_binh_luan(chu_de, y_dinh, khu_vuc, ha_noi, cfg) is mong_doi


# ---------- bộ che thông tin ----------
CHUOI_9_SO = re.compile(r"(?:\d[\s.\-]?){9,}")


@pytest.mark.parametrize("van_ban", [
    "Liên hệ 0902 189 751 nhé", "zalo0388123456", "ib 912000111 nha", "gọi 987-000-222", "+84 902 189 751", "0 9 0 2 1 8 9 7 5 1",
    "sdt:0902.189.751 ạ", "Zl <SĐT> 0912345678", "số em 84902189751",
])
def test_phone_numbers_in_every_format_seen_in_production_are_masked(van_ban):
    sach = xay_mau.che_thong_tin(van_ban)
    assert not CHUOI_9_SO.search(sach), sach


@pytest.mark.parametrize("van_ban", ["Giá 2.200.000đ bao ship", "Màn 27 inch 2K 240Hz 1ms", "MSI G274QPX 4tr5 còn bảo hành 2029", "ram 16gb ssd 512gb"])
def test_prices_and_specs_are_left_alone(van_ban):
    assert xay_mau.che_thong_tin(van_ban) == van_ban


def test_links_and_emails_are_masked():
    sach = xay_mau.che_thong_tin("xem https://bit.ly/abc hoặc ten.nguoi@gmail.com hoặc www.shop.vn/x")
    assert "bit.ly" not in sach and "gmail" not in sach and "shop.vn" not in sach


# ---------- các tầng lấy mẫu phải phủ kín và loại trừ nhau ----------
def _dong(**kw):
    return {"post_text": "Cần mua màn hình 27 inch ở Hà Nội", "topic": "Màn hình", "intent": "MUA", "decision": "Bỏ qua", "reason": "", **kw}


@pytest.mark.parametrize("kw, tang", [
    ({"post_text": ""}, "R_trong_hoac_qua_ngan"), ({"post_text": "bán"}, "R_trong_hoac_qua_ngan"),
    ({"topic": "Laptop", "post_text": "Laptop Dell màn 15.6 inch 144hz bán"}, "T_chu_de_khac_co_chu_man"),
    ({"topic": None, "post_text": "Bán bếp từ Sơn Hà còn bảo hành tốt"}, "T_chu_de_khac"),
    ({"decision": "Bình luận"}, "M_da_binh_luan"), ({"intent": "MUA"}, "M_mua_nhung_bo_qua"),
    ({"intent": "KHÔNG XÁC ĐỊNH"}, "M_khong_xac_dinh"),
    ({"intent": "BÁN", "reason": "BÁN (AI Gemini: quảng cáo)"}, "M_ban_do_ai"),
    ({"intent": "BÁN", "post_text": "Em cần tìm người mua màn Dell 24 inch giá tốt"}, "M_ban_co_dau_hieu_mua"),
    ({"intent": "BÁN", "post_text": "Thanh lý màn Dell 24 inch giá tốt bảo hành"}, "M_ban_khac"),
    ({"intent": None}, "M_khac"),
])
def test_every_row_falls_into_exactly_one_known_stratum(kw, tang):
    assert xay_mau.xep_tang(_dong(**kw)) == tang
    assert tang in xay_mau.MAU_MOI_TANG


def test_sampling_is_reproducible_with_the_same_seed(tmp_path):
    import sqlite3
    db = tmp_path / "t.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE post_decisions (id INTEGER PRIMARY KEY, group_name TEXT, text_key TEXT, post_text TEXT, topic TEXT, intent TEXT, decision TEXT, reason TEXT)")
    for i in range(300):
        c.execute("INSERT INTO post_decisions (group_name, text_key, post_text, topic, intent, decision, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  ("Chợ Hà Nội", f"k{i}", f"Cần mua màn hình số {i} giá tốt", "Màn hình" if i % 3 else "PC", "MUA" if i % 2 else "BÁN", "Bỏ qua", ""))
    c.commit()
    c.close()
    m1, h1, t1 = xay_mau.dung_mau(str(db), 5)
    m2, h2, t2 = xay_mau.dung_mau(str(db), 5)
    assert m1 == m2 and h1 == h2 and t1 == t2
    assert sum(t["tong"] for t in t1.values()) == 300
    assert all(set(m) == {"id", "van_ban", "ten_nhom", "nhom_ha_noi"} for m in m1)       # người gán nhãn KHÔNG thấy kết quả của hệ thống


# ---------- CỔNG HỒI QUY trên dữ liệu thật ----------
THU_MUC_DU_LIEU = os.path.join(GOC, "danh_gia", "du_lieu")
CAN_DU_LIEU = pytest.mark.skipif(not os.environ.get("CHAY_DANH_GIA") or not os.path.exists(os.path.join(THU_MUC_DU_LIEU, "nhan_doc_lap.jsonl")),
                                 reason="đặt CHAY_DANH_GIA=1 và có bộ nhãn local (danh_gia/du_lieu) mới chạy cổng hồi quy trên dữ liệu thật")


@CAN_DU_LIEU
def test_classifier_does_not_get_worse_than_the_first_measurement():
    """Ngưỡng = lần đo đầu (29/10/2026) trừ ~10 điểm: để phát hiện hồi quy, KHÔNG phải mục tiêu chất lượng."""
    a = chay.do_phan_loai(chay.dung_ds_mau(chay.CSDL), 50)
    v = a["kich_ban"]["vang"]
    assert v["recall_nen"][0] >= 0.80 and v["precision_nen"][0] >= 0.75
    assert v["chu_de_recall"] >= 0.88 and v["chu_de_precision"] >= 0.80
    assert v["y_dinh_recall_mua"] >= 0.80 and v["y_dinh_precision_mua"] >= 0.80
    assert v["khu_vuc_chinh_xac"] >= 0.80
    assert a["dong_thuan"]["ca_ba"] >= 0.85                                    # nhãn còn đáng tin: hai người khớp ≥ 85%


@CAN_DU_LIEU
def test_comment_cards_have_no_known_defect_on_real_data():
    b = chay.do_the_binh_luan(chay.CSDL)
    assert b["b1_mau_dang_bat"]["loi"] == []
    assert b["b2_ai_that"]["bi_chap_nhan_nham"] == [] and b["b3_mau_cu_dai"]["bi_chap_nhan_nham"] == []
    assert b["b4_da_dang"]["an_toan_lo_lien_he"] == [] and b["b4_da_dang"]["day_du_con_lien_he_sau_make_safe"] == []
    assert b["b5_tan_cong"]["bi_lot_qua"] == [] and b["b5_tan_cong"]["bi_tu_choi_nham"] == []


@CAN_DU_LIEU
def test_masking_leaves_no_phone_like_number_in_the_whole_real_data():
    c = chay.do_che_thong_tin(chay.CSDL)
    assert c["van_con_giong_sdt_sau_khi_che"] == 0           # chuỗi ≥ 9 số còn lại là thông số máy / năm / giá / mã dài, đã xem tay (29/10/2026)
