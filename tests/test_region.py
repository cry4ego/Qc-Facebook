"""Khu vực người cần mua (data/khu_vuc.txt): khách ở xa bị bỏ qua, khách Hà Nội / lân cận / không ghi khu vực giữ lại."""
import pytest

from config import Config
from modules.region import find_regions, load_regions, parse_regions

REGIONS = load_regions(Config.REGION_FILE)


def region(text):
    return find_regions(text, REGIONS)


@pytest.mark.parametrize("text", [
    "Tc 400 cần màn 24 inch kv hcm",
    "Cần mua màn 27 2K ở TPHCM",
    "tp.hcm cần tìm màn hình 24 inch",
    "Ai có màn 24 inch q7 không ạ",
    "Màn 24inch ở cao bằng",
    "Biên Hòa cần mua màn cũ",
    "cần mua màn ở Sài Gòn",
    "Tìm màn 27 inch khu vực Thủ Đức",
    "Đà Nẵng có ai pass màn 24 không",
])
def test_far_buyers_are_detected(text):
    assert region(text).is_far


@pytest.mark.parametrize("text", [
    "HN khu vực Ngã tư sở cần mua 1 màn hình 2nd 24inch",
    "Hoàng mai, hà nội e cần tìm màn 24/27",
    "Cần tìm màn 27 inch ở Cầu Giấy",
    "Bắc Ninh cần mua màn 24",
    "Cần mua màn ở Hà Nội, ship vào HCM cho em gái cũng được",  # nhắc cả Hà Nội: vẫn là khách gần
])
def test_hanoi_and_nearby_buyers_are_kept(text):
    r = region(text)
    assert r.near and not r.is_far


@pytest.mark.parametrize("text", [
    "Cần tìm màn 27 inch 2K tầm 3tr",
    "TC 500k tìm màn",
    "Mua màn Samsung Odyssey G5 27 inch",
    "Cần màn MSI G274QPF hoặc AOC Q27G2",     # tên model không bị nhầm thành "quận"
    "Tìm màn cho chị Huệ dùng văn phòng",      # Huệ không phải Huế
])
def test_posts_without_region_are_kept(text):
    r = region(text)
    assert not r.far and not r.is_far


def test_region_file_has_no_broken_lines():
    errors = []
    with open(Config.REGION_FILE, encoding="utf-8") as f:
        regions = parse_regions(f.read(), errors)
    assert errors == []
    assert regions.near and regions.far
