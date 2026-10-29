"""Prompt của vai Nội dung (vai.py): mẫu bình luận phải NGẮN — chỉ mã màn, thông số, công nghệ; tên người bán, SĐT, địa chỉ do hệ thống ghép."""
from cong_ty import vai


def test_the_content_role_asks_for_short_cards_made_of_code_specs_and_technology_only():
    p = vai.NHIEM_VU["noi_dung"]
    for can in ("NGẮN", "mã màn hình", "thông số màn", "công nghệ màn", "tối đa 3 dòng", "dòng liên hệ"):
        assert can in p, can


def test_the_content_role_must_not_write_what_the_system_or_the_sales_image_already_carries():
    p = vai.NHIEM_VU["noi_dung"]
    for cam in ("lời chào", "giá", "bảo hành", "tình trạng máy", "số điện thoại", "địa chỉ", "tên người bán"):
        assert cam in p, cam
    assert "{giá}" not in p      # mẫu mới không ghi giá nên không còn dặn dùng chỗ trống giá


def test_the_system_prompt_of_the_content_role_carries_the_common_rules_and_the_format():
    he_thong = vai._he_thong("noi_dung")
    assert vai.LUAT_CHUNG in he_thong and vai.NHIEM_VU["noi_dung"] in he_thong and vai.KHUON_VAI in he_thong
