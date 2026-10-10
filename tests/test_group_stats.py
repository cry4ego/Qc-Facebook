"""Đọc số thành viên / số bài mỗi ngày từ trang Giới thiệu của nhóm (Yêu cầu 2)."""
import pytest

from modules.group_stats import parse_about

ABOUT_VI = """Nhóm Công khai
417,7K thành viên
Giới thiệu
Công khai
Đã tạo nhóm vào 1 tháng 8, 2023.
Hoạt động
Hôm nay có 236 bài viết mới
Tổng cộng 417.705 thành viên
Ngày tạo:"""


def test_exact_total_members_and_posts_today():
    info = parse_about(ABOUT_VI)
    assert info.members == 417705
    assert info.posts_today == 236


def test_short_member_count_when_no_total_line():
    info = parse_about("Nhóm Riêng tư\n338,7K thành viên\nHoạt động")
    assert info.members == 338700
    assert info.posts_today is None


@pytest.mark.parametrize("text,members", [
    ("Nhóm Công khai · 1,2 Tr thành viên", 1200000),
    ("Public group · 25K members", 25000),
    ("Total members: 4,512", 4512),
    ("Nhóm Công khai\n649 thành viên", 649),
])
def test_member_formats(text, members):
    assert parse_about(text).members == members


def test_posts_per_month_converted_to_per_day():
    info = parse_about("Tổng cộng 5.230 thành viên\n90 bài viết mới trong tháng trước")
    assert info.posts_today == 3


def test_missing_member_count_returns_none():
    info = parse_about("Bạn hiện không xem được nội dung này")
    assert info.members is None
