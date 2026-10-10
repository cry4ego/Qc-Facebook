"""Chuỗi bộ lọc bài viết / nhóm (Yêu cầu 1, 2, 3 + khả năng mở rộng)."""
from types import SimpleNamespace

from config import Config
from modules.engagement import Engagement
from modules.filters import (GROUP_FILTERS, POST_FILTERS, PostCandidate, Verdict, run_filters)
from modules.group_finder import min_members
from modules.intent import DEFAULT_FILE


def cfg(**over):
    base = dict(COMMENT_TOPICS=["Màn hình", "PC"], INTENT_FILTER=True, INTENT_KEYWORDS_FILE=DEFAULT_FILE,
                INTENT_MIN_SCORE=3, INTENT_MARGIN=2, REGION_FILTER=True, REGION_FILE=Config.REGION_FILE,
                REGION_REQUIRED_IN_NATIONAL_GROUPS=True, POST_MIN_ENGAGEMENT=10,
                ENGAGEMENT_WEIGHTS={"reaction": 1, "comment": 2, "share": 3},
                GROUP_MIN_MEMBERS=5000, GROUP_MIN_MEMBERS_HANOI=500, GROUP_MIN_POSTS_PER_DAY=0)
    return SimpleNamespace(**{**base, **over})


def post(text, engagement=Engagement(5, 5, 0), calls=None, hanoi_group=True):
    def read():
        if calls is not None:
            calls.append(1)
        return engagement
    return PostCandidate(text, 10, cfg(), read, hanoi_group=hanoi_group)


def test_buy_post_with_enough_engagement_passes():
    v = run_filters(POST_FILTERS, post("Cần tìm màn 27 inch 2K tầm 3tr"), cfg())
    assert v.ok
    assert "MUA" in v.reason and "điểm tương tác 15" in v.reason


def test_sell_post_is_rejected_without_reading_engagement():
    calls = []
    v = run_filters(POST_FILTERS, post("Thanh lý màn Dell 24 inch giá 1tr5, bao test", calls=calls), cfg())
    assert not v.ok and v.reason.startswith("BÁN")
    assert calls == []  # không tốn công đọc tương tác cho bài bán


def test_low_engagement_buy_post_is_rejected():
    v = run_filters(POST_FILTERS, post("Cần tìm màn 27 inch", Engagement(1, 2, 0)), cfg())
    assert not v.ok and "điểm tương tác 5 < 10" in v.reason


def test_unreadable_engagement_does_not_silently_block_buy_posts():
    v = run_filters(POST_FILTERS, post("Cần tìm màn 27 inch", Engagement(0, 0, 0, known=False)), cfg())
    assert v.ok and "không đọc chắc được tương tác" in v.reason


def test_thresholds_and_switches_come_from_config():
    p = post("Thanh lý màn Dell 24 inch giá 1tr5", Engagement(0, 0, 0))
    assert run_filters(POST_FILTERS, p, cfg(INTENT_FILTER=False, POST_MIN_ENGAGEMENT=0)).ok


def test_off_topic_post_is_rejected():
    v = run_filters(POST_FILTERS, post("Cần mua laptop thinkpad x1"), cfg())
    assert not v.ok and "Laptop" in v.reason


def test_group_member_threshold():
    assert run_filters(GROUP_FILTERS, {"members": 417705, "posts_today": 236}, cfg()).ok
    v = run_filters(GROUP_FILTERS, {"members": 1200, "posts_today": 5}, cfg())
    assert not v.ok and "1.200 thành viên < 5.000" == v.reason


def test_hanoi_group_needs_fewer_members_than_national_group():
    v = run_filters(GROUP_FILTERS, {"members": 652, "hanoi": True}, cfg())
    assert v.ok and v.reason == "652 thành viên ≥ 500 (nhóm Hà Nội)"
    v = run_filters(GROUP_FILTERS, {"members": 400, "hanoi": True}, cfg())
    assert not v.ok and v.reason == "400 thành viên < 500 (nhóm Hà Nội)"
    assert not run_filters(GROUP_FILTERS, {"members": 4535, "hanoi": False}, cfg()).ok


def test_group_search_keeps_small_hanoi_groups_only():
    c = cfg(MIN_GROUP_MEMBERS=5000)
    assert min_members("CHỢ MÀN HÌNH MÁY TÍNH HÀ NỘI", c) == 500
    assert min_members("Mua bán màn hình máy tính cũ", c) == 5000


def test_group_without_member_count_is_skipped_with_reason():
    v = run_filters(GROUP_FILTERS, {"members": None, "error": "lỗi mở trang Giới thiệu"}, cfg())
    assert not v.ok and "lỗi mở trang Giới thiệu" in v.reason
    assert not run_filters(GROUP_FILTERS, None, cfg()).ok


def test_group_activity_threshold_optional():
    stats = {"members": 9000, "posts_today": 2}
    assert run_filters(GROUP_FILTERS, stats, cfg()).ok
    assert not run_filters(GROUP_FILTERS, stats, cfg(GROUP_MIN_POSTS_PER_DAY=5)).ok


def test_new_filter_can_be_added_without_changing_flow():
    no_dell = lambda p, c: Verdict("dell" not in p.text.lower(), "không nhận bài hỏi màn Dell")
    v = run_filters(POST_FILTERS + [no_dell], post("Cần tìm màn Dell 27 inch"), cfg())
    assert not v.ok and v.reason == "không nhận bài hỏi màn Dell"


def test_far_away_buyer_is_skipped_before_reading_engagement():
    calls = []
    v = run_filters(POST_FILTERS, post("Cần tìm màn 27 inch 2K ở TPHCM", calls=calls), cfg())
    assert not v.ok and v.reason.startswith("khách ở xa (HCM)")
    assert calls == []


def test_hanoi_buyer_passes_with_region_in_reason():
    v = run_filters(POST_FILTERS, post("Cần tìm màn 27 inch ở Cầu Giấy, Hà Nội"), cfg())
    assert v.ok and "khu vực hà nội, cầu giấy" in v.reason


def test_national_group_needs_hanoi_mentioned():
    # nhóm toàn quốc (vd MÀN HÌNH MÁY TÍNH): bài không ghi khu vực ~ một nửa là khách tỉnh xa -> bỏ qua
    v = run_filters(POST_FILTERS, post("Cần tìm màn 27 inch 2K tầm 3tr", hanoi_group=False), cfg())
    assert not v.ok and v.reason.startswith("không ghi khu vực (nhóm toàn quốc")
    assert run_filters(POST_FILTERS, post("Cần tìm màn 27 inch 2K ở Đống Đa", hanoi_group=False), cfg()).ok
    assert run_filters(POST_FILTERS, post("Cần tìm màn 27 inch 2K", hanoi_group=False),
                       cfg(REGION_REQUIRED_IN_NATIONAL_GROUPS=False)).ok


def test_hanoi_group_accepts_posts_without_region():
    v = run_filters(POST_FILTERS, post("Cần tìm màn 27 inch 2K tầm 3tr", hanoi_group=True), cfg())
    assert v.ok and "không ghi khu vực, nhóm Hà Nội" in v.reason


def test_pc_parts_post_is_skipped_when_only_monitors_are_wanted():
    v = run_filters(POST_FILTERS, post("Tìm bộ pc 5tr chơi game"), cfg(COMMENT_TOPICS=["Màn hình"]))
    assert not v.ok and v.reason.startswith("chủ đề PC")


def test_region_filter_can_be_switched_off():
    assert run_filters(POST_FILTERS, post("Cần tìm màn 27 inch ở TPHCM"), cfg(REGION_FILTER=False)).ok
