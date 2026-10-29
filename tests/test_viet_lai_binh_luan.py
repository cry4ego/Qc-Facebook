"""Công cụ viết lại bình luận thành THẺ NGẮN (26/10/2026): chỉ mã màn, thông số, công nghệ + tên người bán, SĐT, địa chỉ.
Kiểm tra công cụ, và khóa chính sách "ngắn" lên nội dung thật của chủ shop (Ảnh Màn-20-10/noi-dung)."""
import importlib.util
import json
import os
import re
import shutil

import pytest

from modules import noi_dung

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUONG_DAN = os.path.join(GOC, "tools", "viet_lai_binh_luan.py")
_spec = importlib.util.spec_from_file_location("viet_lai_binh_luan", DUONG_DAN)
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

NOI_DUNG_THAT = os.path.join(GOC, "Ảnh Màn-20-10", "noi-dung")
CAC_TOM_TAT = {
    "MSI G274QPX": '27" 2K · Rapid IPS · 240Hz · 1ms · HDR 400 · USB-C sạc 65W',
    "MSI G274QRFW": '27" 2K · Rapid IPS · 170Hz · 1ms · màu trắng · RGB',
    "MSI G272QPF E2": '27" 2K · Rapid IPS · 180Hz · 1ms · tương phản 1200:1',
    "MSI PRO MP273QP": '27" 2K · IPS · 75Hz · loa 2×2W · bảo vệ mắt TÜV',
}
# những chữ làm bình luận dài / giống spam: giá, bảo hành, tình trạng máy, mời nhắn tin
CHU_THUA = re.compile(r"\bgiá\b|bảo hành|\bBH\b|qua sử dụng|1 đổi 1|inbox|nhắn|liên hệ|lưu ý|\{|hoàng|người bán|zalo|hotline", re.IGNORECASE)


def _cau_hinh_that():
    with open(os.path.join(NOI_DUNG_THAT, "cau-hinh.json"), encoding="utf-8") as f:
        return json.load(f)


# ---------- tách thông số / công nghệ ----------
def test_the_summary_is_split_into_specs_and_technology():
    thong_so, cong_nghe = tool.tach_tom_tat(CAC_TOM_TAT["MSI G274QPX"])
    assert thong_so == ['27" 2K', "240Hz", "1ms"] and cong_nghe == ["Rapid IPS", "HDR 400", "USB-C sạc 65W"]
    thong_so, cong_nghe = tool.tach_tom_tat(CAC_TOM_TAT["MSI PRO MP273QP"])
    assert thong_so == ['27" 2K', "75Hz"] and cong_nghe == ["IPS", "loa 2×2W", "bảo vệ mắt TÜV"]


@pytest.mark.parametrize("ten, tom_tat", list(CAC_TOM_TAT.items()))
def test_every_real_summary_has_both_specs_and_technology(ten, tom_tat):
    thong_so, cong_nghe = tool.tach_tom_tat(tom_tat)
    assert len(thong_so) >= 2 and len(cong_nghe) >= 1, (ten, thong_so, cong_nghe)


def test_a_summary_without_specs_or_technology_is_refused_with_the_product_name():
    with pytest.raises(ValueError, match="MSI X"):
        tool.tach_tom_tat("Rapid IPS · HDR 400", "MSI X")
    with pytest.raises(ValueError, match="MSI X"):
        tool.tach_tom_tat('27" 2K · 240Hz', "MSI X")


# ---------- các kiểu trình bày ----------
@pytest.mark.parametrize("kieu", range(len(tool.KIEU_TRINH_BAY)))
def test_every_layout_has_the_code_specs_and_technology_and_nothing_else(kieu):
    thong_so, cong_nghe = tool.tach_tom_tat(CAC_TOM_TAT["MSI G274QPX"])
    chu = tool.the_ngan("MSI G274QPX", thong_so, cong_nghe, kieu)
    for phan in ["MSI G274QPX", *thong_so, *cong_nghe]:
        assert phan in chu, (kieu, phan)
    assert chu.count("\n") <= 2 and len(chu) <= 140 and not CHU_THUA.search(chu)


def test_there_are_enough_layouts_so_the_same_text_is_not_posted_over_and_over():
    """Dòng liên hệ cố định (một dạng duy nhất) nên độ đa dạng chỉ đến từ kiểu trình bày: cần ít nhất 12 kiểu cho mỗi mẫu màn"""
    assert len(tool.KIEU_TRINH_BAY) >= 12


def test_the_layouts_look_different_from_each_other():
    thong_so, cong_nghe = tool.tach_tom_tat(CAC_TOM_TAT["MSI G274QPX"])
    chu = {tool.the_ngan("MSI G274QPX", thong_so, cong_nghe, k) for k in range(len(tool.KIEU_TRINH_BAY))}
    assert len(chu) == len(tool.KIEU_TRINH_BAY)


# ---------- file markdown ----------
def test_the_file_has_one_comment_per_layout_with_unique_codes_that_the_importer_can_read():
    sp = {"ma": "g274qpx", "ten": "MSI G274QPX", "tom_tat": CAC_TOM_TAT["MSI G274QPX"], "nguon": ["https://www.msi.com/x"]}
    cac_muc = noi_dung.parse_md(tool.viet_file(sp, "QPX"))
    assert [m.code for m in cac_muc] == [f"QPX-{i:02d}" for i in range(1, len(tool.KIEU_TRINH_BAY) + 1)]
    assert all(m.text and not m.image and not CHU_THUA.search(m.text) for m in cac_muc)


def test_the_comment_code_prefix_is_kept_from_the_existing_file(tmp_path):
    (tmp_path / "a.md").write_text("# x\n\n## QPF-01\nnội dung\n", encoding="utf-8")
    assert tool.tien_to_ma(str(tmp_path / "a.md"), "g274qpf-e2") == "QPF"
    assert tool.tien_to_ma(str(tmp_path / "khong-co.md"), "g274qpf-e2") == "G274"


# ---------- chạy trên một thư mục nội dung ----------
@pytest.fixture
def thu_muc(tmp_path):
    dich = tmp_path / "noi-dung"
    (dich / "binh-luan").mkdir(parents=True)
    shutil.copy2(os.path.join(NOI_DUNG_THAT, "cau-hinh.json"), dich / "cau-hinh.json")
    return str(dich)


def test_running_it_writes_a_file_per_product_and_all_the_comments_are_distinct(thu_muc):
    ket_qua = tool.chay(thu_muc)
    cau_hinh = _cau_hinh_that()
    so_kieu = len(tool.KIEU_TRINH_BAY)
    assert [ma for ma, _ in ket_qua] == [sp["ma"] for sp in cau_hinh["san_pham"]] and all(n == so_kieu for _, n in ket_qua)
    content = noi_dung.load(thu_muc)
    for sp in content.products:
        cac_bl = noi_dung.comments(content, sp)
        assert len(cac_bl) == so_kieu
        assert len({c.full for c in cac_bl}) == so_kieu and len({c.safe for c in cac_bl}) == so_kieu   # không có hai bình luận y hệt nhau


def test_running_it_twice_gives_the_same_files(thu_muc):
    thu_muc_bl = os.path.join(thu_muc, "binh-luan")

    def doc_het():
        return {f: open(os.path.join(thu_muc_bl, f), encoding="utf-8").read() for f in os.listdir(thu_muc_bl)}

    tool.chay(thu_muc)
    lan_1 = doc_het()
    tool.chay(thu_muc)
    assert lan_1 == doc_het() and len(lan_1) == len(_cau_hinh_that()["san_pham"])


# ---------- nội dung THẬT của chủ shop phải ngắn ----------
@pytest.mark.skipif(not os.path.isdir(NOI_DUNG_THAT), reason="không có thư mục nội dung gốc")
def test_the_owners_real_comments_are_short_cards():
    """Chính sách chủ shop chốt 26/10/2026: bình luận chỉ có mã màn, thông số, công nghệ, SĐT, địa chỉ, tên người bán."""
    content = noi_dung.load(NOI_DUNG_THAT)
    cfg = content.config
    sdt_so = re.sub(r"\D", "", cfg["sdt"])
    pho = cfg["dia_chi"].split(",")[0].strip()
    lien_he = noi_dung.lien_he_gon(cfg["nguoi_ban"], cfg["sdt"], cfg["dia_chi"])          # "Dũng-0902189751-64 Cầu Diễn"
    assert lien_he.startswith(cfg["nguoi_ban"].split()[-1] + "-") and lien_he.count("-") == 2
    tong = 0
    for sp in content.products:
        cac_bl = noi_dung.comments(content, sp)
        tong += len(cac_bl)
        for c in cac_bl:
            ctx = f"{sp['ma']} {c.code}"
            assert sp["ten"] in c.full and sp["ten"] in c.safe, ctx
            assert len(c.full) <= 190 and c.full.count("\n") <= 3, (ctx, c.full)
            assert not CHU_THUA.search(c.full) and not CHU_THUA.search(c.safe), (ctx, c.full)
            assert c.full.splitlines()[-1] == lien_he, (ctx, c.full)                          # MỘT dòng liên hệ ở cuối cùng
            assert c.full.count(sdt_so) == 1 and cfg["nguoi_ban"] not in c.full, ctx          # không ghi họ tên đầy đủ
            assert c.safe == c.full.rsplit("\n", 1)[0], (ctx, c.safe)                         # bản không SĐT = chỉ thẻ thông số
            assert sdt_so not in re.sub(r"\D", "", c.safe) and pho not in c.safe and "Dũng" not in c.safe, (ctx, c.safe)
    assert tong == len(tool.KIEU_TRINH_BAY) * len(content.products)
