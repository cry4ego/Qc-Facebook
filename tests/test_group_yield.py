"""Xoay vòng nhóm theo số bài cần mua: thứ tự quét, tới lượt quét lại, thứ tự đăng bài, số liệu trong CSDL."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from modules.db import COMMENT, SKIP, Database
from modules.group_yield import (group_score, next_group, posting_order, rank_by_yield, scan_due, scan_interval,
                                 scan_window)

CFG = SimpleNamespace(GROUP_RESCAN_MINUTES=120, LOW_YIELD_MIN_SCANS=3, LOW_YIELD_RESCAN_HOURS=24,
                      LOW_YIELD_OBSERVE_HOURS=24, HOT_RESCAN_MINUTES=3, SCAN_ACTIVE_MINUTES=10,
                      SCAN_ACTIVE_POSTS_PER_DAY=100, SCAN_OVERLAP_MINUTES=10, MAX_POST_AGE_MINUTES=360)
NOW = datetime(2026, 10, 8, 12, 0)
FMT = "%Y-%m-%d %H:%M:%S"


def group(name, **kw):
    return {"group_url": f"https://www.facebook.com/groups/{name}/", "group_name": name, **kw}


def stats(scans=0, buy=0, hours_ago=None, watched_hours=48, interactions=None):
    """Số liệu 1 nhóm: quét lần cuối ... giờ trước, theo dõi từ ... giờ trước"""
    last = (NOW - timedelta(hours=hours_ago)).strftime(FMT) if hours_ago is not None else None
    first = (NOW - timedelta(hours=watched_hours)).strftime(FMT) if scans else None
    return {"scans": scans, "buy": buy, "first_scan": first, "last_scan": last, "interactions": interactions}


def by_name(**yields):
    return {group(name)["group_url"]: y for name, y in yields.items()}


def names(groups):
    return [g["group_name"] for g in groups]


def test_rank_hot_then_priority_then_buyers_then_new_then_low_yield():
    groups = [group("low"), group("new1"), group("buyer2"), group("hot", hot=True), group("buyer9"),
              group("prio", priority=True), group("new2")]
    yields = by_name(low=stats(scans=5), buyer2=stats(scans=4, buy=2), buyer9=stats(scans=1, buy=9))
    assert names(rank_by_yield(groups, yields, CFG)) == ["hot", "prio", "buyer9", "buyer2", "new1", "new2", "low"]


def test_group_is_rescanned_only_after_its_waiting_time():
    g = group("a")
    assert scan_due(g, {}, CFG, NOW)                                            # chưa quét lần nào
    assert not scan_due(g, by_name(a=stats(scans=1, hours_ago=0.5)), CFG, NOW)  # vừa quét 30 phút trước
    assert scan_due(g, by_name(a=stats(scans=1, hours_ago=3)), CFG, NOW)        # quá 2 giờ


def test_low_yield_group_waits_a_day():
    g = group("a")
    assert not scan_due(g, by_name(a=stats(scans=4, hours_ago=5)), CFG, NOW)
    assert scan_due(g, by_name(a=stats(scans=4, hours_ago=25)), CFG, NOW)
    assert scan_due(g, by_name(a=stats(scans=4, buy=1, hours_ago=5)), CFG, NOW)  # có bài mua: 2 giờ là đủ


def test_busy_scanning_does_not_label_a_new_group_low_yield_too_early():
    # quét dày (10 phút/lần) nên 3 lần quét có thể chỉ trong 30 phút — chưa đủ 24 giờ theo dõi thì chưa kết luận
    fresh = by_name(a=stats(scans=5, hours_ago=0.6, watched_hours=1))
    assert scan_interval(group("a"), None, fresh["https://www.facebook.com/groups/a/"], CFG, NOW) == 120


def test_scan_interval_follows_group_activity():
    y0, y_buy, y_low = stats(scans=1, hours_ago=1), stats(scans=1, buy=2, hours_ago=1), stats(scans=5, hours_ago=1)
    assert scan_interval(group("hot", hot=True), None, y0, CFG, NOW) == 3
    assert scan_interval(group("a"), None, y_buy, CFG, NOW) == 10                     # có khách tìm màn hình
    assert scan_interval(group("a"), {"posts_today": 250}, y0, CFG, NOW) == 10        # nhóm đông bài mỗi ngày
    assert scan_interval(group("a"), {"posts_today": 20}, y0, CFG, NOW) == 120        # nhóm thường
    assert scan_interval(group("a"), None, y_low, CFG, NOW) == 24 * 60                # ít khách


def test_score_prefers_buyers_interactions_activity_and_members():
    base = stats(scans=1)
    big = group_score(group("a"), {"members": 300_000, "posts_today": 200}, {**base, "interactions": 25})
    small = group_score(group("b"), {"members": 8_000, "posts_today": 5}, {**base, "interactions": 1})
    buyers = group_score(group("c"), {"members": 8_000, "posts_today": 5}, {**base, "buy": 6, "interactions": 1})
    assert big > small and buyers > big
    assert group_score(group("d", hot=True), None, base) >= 2


def test_next_group_picks_most_overdue_high_score_and_skips_not_due():
    groups = [group("vua_quet"), group("tre_han", members=300_000), group("hot", hot=True)]
    yields = by_name(vua_quet=stats(scans=1, hours_ago=0.1), tre_han=stats(scans=1, hours_ago=5),
                     hot=stats(scans=1, hours_ago=0.02))
    assert next_group(groups, {}, yields, CFG, now=NOW)["group_name"] == "tre_han"   # hot vừa quét 1 phút trước
    yields[group("hot")["group_url"]] = stats(scans=1, hours_ago=0.1)                 # hot: 6 phút > 3 phút
    assert next_group(groups, {}, yields, CFG, now=NOW)["group_name"] == "hot"


def test_next_group_respects_recent_failed_attempts():
    tried = {group("a")["group_url"]: (NOW - timedelta(minutes=5)).strftime(FMT)}   # vừa thử (chưa tham gia…)
    assert next_group([group("a")], {}, {}, CFG, last_try=tried, now=NOW) is None
    assert next_group([group("a")], {}, {}, CFG, now=NOW)["group_name"] == "a"


def test_scan_window_only_covers_posts_since_last_scan():
    assert scan_window(stats(), CFG, NOW) == 360                          # chưa quét lần nào: 6 giờ
    assert scan_window(stats(scans=1, hours_ago=0.05), CFG, NOW) == 15    # quét 3 phút trước: tối thiểu 15 phút
    assert scan_window(stats(scans=1, hours_ago=1), CFG, NOW) == 70       # 60 phút + 10 phút dự phòng
    assert scan_window(stats(scans=1, hours_ago=30), CFG, NOW) == 360


def test_hot_group_is_always_due():
    assert scan_due(group("a", hot=True), by_name(a=stats(scans=9, hours_ago=0.1)), CFG, NOW)


def test_posting_goes_to_groups_with_buyers_first():
    groups = [group("x"), group("buyer3"), group("y"), group("buyer7")]
    yields = by_name(buyer3=stats(buy=3), buyer7=stats(buy=7))
    assert names(posting_order(groups, yields, shuffle=lambda rest: rest.reverse())) == ["buyer7", "buyer3", "y", "x"]


def test_posting_prefers_monitor_groups_after_groups_with_buyers():
    groups = [group("laptop"), {**group("mh1"), "group_name": "Chợ màn hình Hà Nội"}, group("buyer1"),
              {**group("mh2"), "group_name": "MUA BÁN MÀN HÌNH"}]
    yields = by_name(buyer1=stats(buy=1))
    order = names(posting_order(groups, yields, shuffle=lambda rest: None))
    assert order == ["buyer1", "Chợ màn hình Hà Nội", "MUA BÁN MÀN HÌNH", "laptop"]


def test_db_counts_scans_and_selected_buy_posts(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    url = group("a")["group_url"]
    db.add_group_scan(url, 2)
    db.add_group_scan(url, 0)
    db.log_decision(url, "a", "k1", "Cần mua màn 24 inch", COMMENT, "MUA")
    db.log_decision(url, "a", "k2", "Bán màn Dell", SKIP, "BÁN")
    y = db.group_yields(7)[url]
    assert y["scans"] == 2 and y["buy"] == 1 and y["last_scan"]


def test_db_yields_only_look_at_recent_days(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    url = group("a")["group_url"]
    old = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute("INSERT INTO group_scans (group_url, scanned_at, found) VALUES (?, ?, 0)", (url, old))
    assert url not in db.group_yields(7)
