"""Nội dung bán hàng (20/10): 5 mẫu màn × 30 bình luận + 10 bài đăng, đọc từ data/noi_dung (định dạng của thư mục
"Ảnh Màn-20-10"), nạp vào CSDL, chọn 2 mẫu màn mỗi bài, xoay vòng mẫu màn khi đăng bài theo lịch."""
import json
import os
from datetime import date
from types import SimpleNamespace

import pytest

from modules import noi_dung as nd
from modules.db import Database
from modules.products import pick_pool

CFG = {
    "cong_ty": "ASL Workshop", "nguoi_ban": "Hoàng Văn Dũng", "sdt": "0902 189 751", "zalo": "0902 189 751",
    "dia_chi": "64 Cầu Diễn, Hà Nội", "bao_hanh": "tháng đầu lỗi 1 đổi 1", "tinh_trang": "x",
    "ket_bl_day_du": ["SĐT/Zalo: {sdt} – {nguoi_ban} · Địa chỉ: {dia_chi}", "Gọi {sdt} – {cong_ty}"],
    "ket_bl_chi_ten": ["— {nguoi_ban}", "Người bán: {nguoi_ban}"],
    "san_pham": [
        {"ma": "aaa", "ten": "MSI AAA", "anh": "Anh-ban-hang/MSI-AAA.png",
         "anh_goc": ["assets/aaa/img1.png", "assets/aaa/img2.png"], "gia": "2.500.000đ",
         "gia_co_chan": "2.650.000đ", "phu_thu_chan": "150k"},
        {"ma": "bbb", "ten": "MSI BBB", "anh": "Anh-ban-hang/MSI-BBB.png", "anh_goc": ["assets/bbb/img1.png"],
         "gia": "1.950.000đ", "gia_co_chan": None, "phu_thu_chan": None},
    ],
}
COMMENTS = """# Bình luận
<!-- ghi chú
## KHONG-PHAI-MUC
-->

## A-01
Giá {gia}, có chân {gia_co_chan}.
BH {bao_hanh}.

## A-02
Ảnh: assets/aaa/img2.png
Màn {ten} giá {gia}.
"""
POSTS = """## A-BD01 | Nhóm game thủ
Bán {ten} giá {gia}. Gọi {sdt} – {dia_chi}

## A-BD02 | Nhóm sinh viên
{ten} {gia} – {nguoi_ban}
"""


def write_source(root, comments=COMMENTS, cfg=CFG):
    (root / "binh-luan").mkdir(parents=True)
    (root / "bai-dang").mkdir()
    (root / "cau-hinh.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    for sp in cfg["san_pham"]:
        (root / "binh-luan" / f"{sp['ma']}.md").write_text(comments, encoding="utf-8")
        (root / "bai-dang" / f"{sp['ma']}.md").write_text(POSTS, encoding="utf-8")
    return root


def test_markdown_items_skip_html_comments_and_read_image_lines():
    items = nd.parse_md(COMMENTS)
    assert [i.code for i in items] == ["A-01", "A-02"]
    assert items[0].text == "Giá {gia}, có chân {gia_co_chan}.\nBH {bao_hanh}."
    assert items[1].image == "assets/aaa/img2.png" and "Ảnh:" not in items[1].text
    assert nd.parse_md(POSTS)[0].note == "Nhóm game thủ"


def test_unknown_or_empty_variable_is_an_error():
    with pytest.raises(ValueError, match="sdt"):
        nd.render("Gọi {sdt}", {"gia": "1"}, "A-01")
    with pytest.raises(ValueError, match="gia_co_chan"):
        nd.render("Có chân {gia_co_chan}", {"gia_co_chan": None}, "B-01")


def test_image_paths_map_into_data_images():
    assert nd.image_name("Anh-ban-hang/MSI-AAA.png") == "MSI-AAA.png"
    assert nd.image_name("assets/aaa/img1.png") == "goc/aaa/img1.png"


def test_comments_full_version_has_contact_safe_version_only_seller_name(tmp_path):
    content = nd.load(str(write_source(tmp_path / "nd")))
    c1, c2 = nd.comments(content, content.products[0])
    assert c1.full == "Giá 2.500.000đ, có chân 2.650.000đ.\nBH tháng đầu lỗi 1 đổi 1.\n" \
                      "SĐT/Zalo: 0902 189 751 – Hoàng Văn Dũng · Địa chỉ: 64 Cầu Diễn, Hà Nội"
    assert c1.safe.endswith("\n— Hoàng Văn Dũng") and "0902" not in c1.safe and "Cầu Diễn" not in c1.safe
    # 20/10 (sau): chủ shop muốn cả 2 bản đều dùng ảnh bán hàng (Anh-ban-hang), không dùng ảnh gốc MSI
    assert (c1.image, c1.safe_image) == ("MSI-AAA.png", "MSI-AAA.png")
    assert c2.safe_image == "goc/aaa/img2.png" and c2.image == "goc/aaa/img2.png"  # dòng "Ảnh:" dùng cho cả 2 bản
    assert c2.full.endswith("Gọi 0902 189 751 – ASL Workshop")


@pytest.mark.parametrize("nguoi_ban, sdt, dia_chi, mong_doi", [
    ("Hoàng Văn Dũng", "0902 189 751", "64 Cầu Diễn, Hà Nội", "Dũng-0902189751-64 Cầu Diễn"),
    ("Dũng", "0902.189.751", "64 Cầu Diễn", "Dũng-0902189751-64 Cầu Diễn"),
    ("  Nguyễn  An ", "(090) 218-9751", "12 Ngõ 5, Cầu Giấy, Hà Nội", "An-0902189751-12 Ngõ 5"),
    ("", "0902 189 751", "64 Cầu Diễn", ""), ("Dũng", "", "64 Cầu Diễn", ""), ("Dũng", "0902 189 751", "", "")])
def test_the_short_contact_line_is_first_name_phone_digits_and_street(nguoi_ban, sdt, dia_chi, mong_doi):
    """26/10/2026: họ tên đầy đủ trong bình luận bị Facebook gợi ý gắn thẻ nhầm người -> chỉ ghi tên gọi, SĐT liền, số nhà + phố"""
    assert nd.lien_he_gon(nguoi_ban, sdt, dia_chi) == mong_doi


def test_the_comment_ending_can_be_the_short_contact_line_and_the_safe_version_can_have_no_ending(tmp_path):
    cfg = {**CFG, "ket_bl_day_du": ["{lien_he}"], "ket_bl_chi_ten": [""]}
    content = nd.load(str(write_source(tmp_path / "nd", cfg=cfg)))
    c1, c2 = nd.comments(content, content.products[0])
    assert c1.full == "Giá 2.500.000đ, có chân 2.650.000đ.\nBH tháng đầu lỗi 1 đổi 1.\nDũng-0902189751-64 Cầu Diễn"
    assert "Hoàng" not in c1.full and "Hoàng" not in c1.safe
    assert c1.safe == "Giá 2.500.000đ, có chân 2.650.000đ.\nBH tháng đầu lỗi 1 đổi 1."          # không câu kết: không thừa dòng trống
    assert not c2.safe.endswith("\n") and c2.full.endswith("\nDũng-0902189751-64 Cầu Diễn")


def test_comment_using_price_with_stand_for_model_without_stand_is_an_error(tmp_path):
    content = nd.load(str(write_source(tmp_path / "nd")))
    with pytest.raises(ValueError, match="gia_co_chan"):
        nd.comments(content, content.products[1])


def test_posts_are_rendered_with_contact_and_sales_image(tmp_path):
    content = nd.load(str(write_source(tmp_path / "nd")))
    p1, p2 = nd.posts(content, content.products[0])
    assert p1.text == "Bán MSI AAA giá 2.500.000đ. Gọi 0902 189 751 – 64 Cầu Diễn, Hà Nội"
    assert p1.image == "MSI-AAA.png" and p2.note == "Nhóm sinh viên"


def test_rotation_posts_every_model_equally_with_two_slots_a_day():
    models = ["a", "b", "c", "d", "e"]
    seen = [nd.rotate(models, date(2026, 10, 20 + d), slot) for d in range(5) for slot in (0, 1)]
    assert all(seen.count(m) == 2 for m in models)
    assert nd.rotate(models, date(2026, 10, 20), 0) != nd.rotate(models, date(2026, 10, 20), 1)


def test_each_group_gets_a_different_post_of_the_model():
    posts = [f"bai {i}" for i in range(10)]
    pick = nd.post_picker(posts, date(2026, 10, 20))
    assert len({pick(i) for i in range(10)}) == 10


def test_schedule_cell_rotates_models_or_uses_given_model(tmp_path):
    root = str(write_source(tmp_path / "nd", cfg={**CFG, "san_pham": CFG["san_pham"][:1]}))
    assert nd.scheduled_post("Bài viết thường", 0, date(2026, 10, 20), root) is None   # chữ thường: đăng như cũ
    pick, image, name = nd.scheduled_post("@xoay", 0, date(2026, 10, 20), root)
    assert name == "MSI AAA" and image == "MSI-AAA.png"
    assert {pick(0), pick(1)} == {"Bán MSI AAA giá 2.500.000đ. Gọi 0902 189 751 – 64 Cầu Diễn, Hà Nội",
                                  "MSI AAA 2.500.000đ – Hoàng Văn Dũng"}
    assert nd.scheduled_post(" @AAA ", 1, date(2026, 10, 20), root)[2] == "MSI AAA"
    with pytest.raises(ValueError, match="zzz"):
        nd.scheduled_post("@zzz", 0, date(2026, 10, 20), root)


def test_import_creates_products_and_replaces_old_comments(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    old = db.add_product(name='MSI AAA 27"', price="2.600.000đ", image="cu.png", text="", safe_text="", active=1)
    old_variant = db.add_variant(old, "mẫu cũ")
    content = nd.load(str(write_source(tmp_path / "nd")))
    content = nd.Content(content.root, content.config, content.products[:1])   # chỉ mẫu AAA (BBB lỗi biến)
    summary = nd.import_to_db(db, content)
    p = db.get_product(old)                                                  # cùng mẫu máy: cập nhật, không tạo mới
    assert (p["price"], p["image"], p["active"]) == ("2.500.000đ", "MSI-AAA.png", 1)
    assert [v["active"] for v in db.variants(old) if v["id"] == old_variant] == [0]   # mẫu cũ tắt (giữ lịch sử)
    new = db.variants(old, active_only=True)
    assert len(new) == 2 and new[0]["safe_image"] == "MSI-AAA.png"
    assert summary == [("MSI AAA", 2)]
    nd.import_to_db(db, content)                                             # nạp lại: không nhân đôi mẫu
    assert len(db.variants(old, active_only=True)) == 2


def test_every_active_model_gets_its_own_comment_when_limit_is_five(tmp_path):
    # 20/10 (sau): mỗi bài 5 bình luận độc lập — 5 mẫu màn, mỗi bình luận 1 nội dung + 1 ảnh riêng
    db = Database(str(tmp_path / "t.db"))
    (tmp_path / "images").mkdir()
    for n in range(5):
        (tmp_path / "images" / f"m{n}.png").write_bytes(b"x")
        pid = db.add_product(name=f"Màn {n}", price="1đ", image=f"m{n}.png", text="", safe_text="", active=1)
        db.add_variant(pid, f"đầy đủ {n}", f"chỉ tên {n}")
    pool = pick_pool(db, SimpleNamespace(IMAGE_DIR=str(tmp_path / "images"), COMMENT_PRODUCTS_PER_POST=5))
    assert sorted(c["name"] for c in pool) == [f"Màn {n}" for n in range(5)]
    assert len({c["text"] for c in pool}) == 5 and len({c["image"] for c in pool}) == 5


def test_two_random_models_per_post_and_safe_image(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    (tmp_path / "images" / "goc").mkdir(parents=True)
    for n in range(4):
        (tmp_path / "images" / f"m{n}.png").write_bytes(b"x")
        (tmp_path / "images" / "goc" / f"m{n}.png").write_bytes(b"x")
        pid = db.add_product(name=f"Màn {n}", price="1đ", image=f"m{n}.png", text="", safe_text="", active=1)
        vid = db.add_variant(pid, f"đầy đủ {n}", f"chỉ tên {n}")
        db.update_variant(vid, safe_image=f"goc/m{n}.png")
    config = SimpleNamespace(IMAGE_DIR=str(tmp_path / "images"), COMMENT_PRODUCTS_PER_POST=2)
    pool = pick_pool(db, config)
    assert len(pool) == 2 and len({c["name"] for c in pool}) == 2
    for c in pool:
        n = c["name"][-1]
        assert os.path.normpath(c["image"]).endswith(os.sep + f"m{n}.png")
        assert os.path.normpath(c["safe_image"]).endswith(os.path.join("goc", f"m{n}.png"))  # nhóm cấm SĐT: ảnh gốc
