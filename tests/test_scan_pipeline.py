"""Luồng quét nhóm với trình duyệt giả (không mở Chrome, CSDL tạm): lọc nhóm theo số thành viên, lọc bài theo
chủ đề / MUA-BÁN / tương tác, ghi mọi quyết định kèm lý do, chế độ chạy thử không bình luận."""
from types import SimpleNamespace

import pytest

from config import Config
from modules import fb_selectors as sel
from modules import watcher as w
from modules.db import COMMENT, COMMENT_DRY, SKIP, Database

GROUP = {"group_url": "https://www.facebook.com/groups/testgroup/", "group_name": "Chợ màn hình Hà Nội"}
NATIONAL = {"group_url": "https://www.facebook.com/groups/testgroup/", "group_name": "MÀN HÌNH MÁY TÍNH"}


class El:
    """Phần tử trang giả: chữ, link, phần tử con theo XPath, các aria-label"""
    rect = {"y": 0}

    def __init__(self, text="", href=None, children=None, labels=()):
        self.text, self.href, self.children, self.labels = text, href, children or {}, list(labels)
        self.id = id(self)

    def is_displayed(self):
        return True

    def get_attribute(self, name):
        return self.href if name == "href" else None

    def find_elements(self, by, xpath):
        return self.children.get(xpath, [])


def feed_item(message, post_id, age="20 phút", counts=(), labels=()):
    text = "\n".join(["Người đăng", age, "·", message, *counts, "Bình luận dưới tên Shop"])
    link = El(href=f"https://www.facebook.com/groups/testgroup/posts/{post_id}/")
    return El(text, children={sel.XP_MESSAGE: [El(message)], sel.XP_LINKS: [link]}, labels=labels)


class FakeDriver:
    title = "Nhóm test | Facebook"

    def __init__(self, items, about, joined=True):
        self.items, self.about, self.joined, self.visited = items, about, joined, []

    def get(self, url):
        self.visited.append(url)

    def find_elements(self, by, xpath):
        if xpath == sel.XP_FEED_ITEMS:
            return self.items
        if xpath == sel.XP_JOINED_BTN:
            return [El("Đã tham gia")] if self.joined else []
        if xpath == sel.XP_MAIN:
            return [El(self.about)]
        return []

    def find_element(self, by, xpath):
        return El(self.about)

    def execute_script(self, script, *args):
        return args[0].labels if script == sel.JS_ITEM_LABELS else None

    def get_cookie(self, name):
        return {"value": "999"}


REACTED = ["Xem ai đã bày tỏ cảm xúc về tin này", "Thích: 3 người"]
ITEMS = [
    feed_item("Cần tìm màn 27 inch 2K tầm 3tr ở Cầu Giấy", 1, counts=("3", "5"), labels=REACTED),   # MUA, điểm 13
    feed_item("Thanh lý màn Dell U2419h giá 2tr, bao test 1 tuần", 2, counts=("8", "12"), labels=REACTED),  # BÁN
    feed_item("Tìm màn 24 inch tầm 1tr", 3),                                                         # MUA, điểm 0
    feed_item("Bán laptop Dell Latitude 7490 i5 ram 8", 4),                                         # Laptop
] + [feed_item(f"Bài cũ {i}", 10 + i, age="2 ngày") for i in range(3)]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(w.time, "sleep", lambda s: None)
    monkeypatch.setattr("modules.group_stats.ABOUT_WAIT_SECONDS", 0.2)  # trang Giới thiệu giả: không cần chờ
    cfg = SimpleNamespace(**{k: getattr(Config, k) for k in dir(Config) if k.isupper()})
    cfg.DB_FILE = str(tmp_path / "test.db")
    cfg.COMMENT_LOG_FILE = str(tmp_path / "nhat_ky.xlsx")  # không ghi đè nhật ký Excel thật
    cfg.INTENT_AI = False            # test không gọi Gemini thật
    cfg.POST_MIN_ENGAGEMENT = 10     # các test dưới kiểm tra cơ chế ngưỡng tương tác (cấu hình thật đang đặt 0)
    db = Database(cfg.DB_FILE)
    log = SimpleNamespace(info=lambda *a: None, warning=lambda *a: None, error=lambda *a: None)

    def make(about="Tổng cộng 12.000 thành viên\nHôm nay có 50 bài viết mới", items=ITEMS, dry_run=False, joined=True):
        driver = FakeDriver(items, about, joined)
        return w.GroupWatcher(driver, cfg, log, db, dry_run=dry_run), driver
    return SimpleNamespace(db=db, cfg=cfg, make=make)


def decisions(db):
    return {r["post_text"][:20]: r for r in db.decisions(limit=50)}


def test_only_buy_post_with_enough_engagement_is_selected(env):
    gw, _ = env.make()
    member, posts = gw.scan_group(GROUP)
    assert [p["url"] for p in posts] == ["https://www.facebook.com/groups/testgroup/posts/1/"]
    assert posts[0]["score"] == 13

    d = decisions(env.db)
    assert d["Cần tìm màn 27 inch "]["decision"] == COMMENT
    assert d["Cần tìm màn 27 inch "]["intent"] == "MUA"
    assert d["Thanh lý màn Dell U2"]["decision"] == SKIP and d["Thanh lý màn Dell U2"]["intent"] == "BÁN"
    assert d["Thanh lý màn Dell U2"]["score"] is None          # bài bán: không tốn công đọc tương tác
    assert "điểm tương tác 0 < 10" in d["Tìm màn 24 inch tầm "]["reason"]
    assert "Laptop" in d["Bán laptop Dell Lati"]["reason"]
    assert len(d) == 4                                          # bài cũ hơn 24 giờ không tính là quyết định


def test_with_threshold_zero_fresh_buy_posts_are_selected_immediately(env):
    env.cfg.POST_MIN_ENGAGEMENT = 0  # góp ý chủ shop: bài cần mua thì bình luận ngay, không chờ tương tác
    gw, driver = env.make()
    calls = []
    driver.execute_script = lambda script, *a: calls.append(script) if script == sel.JS_ITEM_LABELS else None
    _, posts = gw.scan_group(GROUP)
    assert sorted(p["url"][-3:] for p in posts) == ["/1/", "/3/"]   # cả bài 0 tương tác ("Tìm màn 24 inch tầm 1tr")
    assert calls == []                                              # không tốn công đọc tương tác


def test_national_group_only_selects_posts_that_mention_hanoi(env):
    env.cfg.POST_MIN_ENGAGEMENT = 0
    gw, _ = env.make()
    _, posts = gw.scan_group(NATIONAL)
    assert [p["url"][-3:] for p in posts] == ["/1/"]                # "… ở Cầu Giấy" — bài không ghi khu vực bị bỏ
    assert "nhóm toàn quốc" in decisions(env.db)["Tìm màn 24 inch tầm "]["reason"]


def test_seeing_the_same_posts_again_does_not_duplicate_log(env):
    gw, _ = env.make()
    gw.scan_group(GROUP)
    gw.scan_group(GROUP)
    rows = env.db.decisions(limit=50)
    assert len(rows) == 4 and all(r["seen_count"] == 2 for r in rows)


def test_already_commented_post_is_not_selected_again(env):
    gw, _ = env.make()
    env.db.add_post("https://www.facebook.com/groups/testgroup/posts/1/", "Nhóm test", GROUP["group_url"], "", 20)
    gw.scan_group(GROUP)   # lần đầu: ghi quyết định kèm link
    _, posts = gw.scan_group(GROUP)
    assert posts == []


def test_group_with_enough_members_passes_and_is_cached(env):
    gw, driver = env.make()
    assert gw._group_check(GROUP).ok
    assert gw._group_check(GROUP).ok
    assert sum("/about" in u for u in driver.visited) == 1      # lần 2 dùng số đã lưu (cache 24 giờ)
    stats = env.db.get_group_stats(GROUP["group_url"])
    assert stats["members"] == 12000 and stats["posts_today"] == 50 and stats["fetched_at"]


def test_small_national_group_is_skipped_with_reason(env):
    gw, _ = env.make(about="Nhóm Công khai\n1,2K thành viên")
    v = gw._group_check(NATIONAL)
    assert not v.ok and v.reason == "1.200 thành viên < 5.000"


def test_small_hanoi_group_is_scanned(env):
    gw, _ = env.make(about="Nhóm Công khai\n652 thành viên")
    v = gw._group_check(GROUP)                                  # "Chợ màn hình Hà Nội": chỉ cần từ 500 thành viên
    assert v.ok and "652 thành viên ≥ 500 (nhóm Hà Nội)" in v.reason
    assert gw._group_check({**NATIONAL, "region": "Hà Nội"}).ok  # cột khu vực = Hà Nội cũng tính là nhóm Hà Nội


def test_group_without_member_count_is_skipped(env):
    gw, _ = env.make(about="Bạn hiện không xem được nội dung này")
    v = gw._group_check(GROUP)
    assert not v.ok and "không lấy được số thành viên" in v.reason


def test_manual_refresh_rereads_about_page(env):
    gw, driver = env.make()
    gw._group_check(GROUP)
    gw.force_stats, gw.stats_refreshed = True, set()
    gw._group_check(GROUP)
    assert sum("/about" in u for u in driver.visited) == 2


def test_dry_run_never_comments(env):
    gw, _ = env.make(dry_run=True)

    def boom(*a, **k):
        raise AssertionError("chạy thử không được bình luận")
    gw.comment_post = boom
    result = gw.run([GROUP], None, lambda g: [{"text": "x", "safe_text": "x", "image": None, "name": "sp"}])
    assert result == 0
    decided = [r["decision"] for r in env.db.decisions(limit=50)]
    assert COMMENT_DRY in decided and COMMENT not in decided   # chạy thử không ghi như đã bình luận thật
    assert env.db.query("SELECT * FROM group_join") == []        # không ghi trạng thái tham gia nhóm


def test_transient_about_page_error_is_not_cached(env):
    gw, driver = env.make()

    def broken_get(url):
        raise RuntimeError("chrome not reachable")
    driver.get = broken_get
    v = gw._group_check(GROUP)
    assert not v.ok and "lỗi mở trang Giới thiệu" in v.reason
    assert env.db.get_group_stats(GROUP["group_url"]) is None   # không lưu lỗi tạm thời -> lần sau đọc lại ngay
    driver.get = driver.visited.append
    gw.stats_refreshed = set()
    assert gw._group_check(GROUP).ok


def test_transient_error_keeps_using_last_known_member_count(env):
    gw, driver = env.make()
    gw._group_check(GROUP)                                      # lần đầu đọc được 12.000
    driver.get = lambda url: (_ for _ in ()).throw(RuntimeError("mất mạng"))
    gw.force_stats, gw.stats_refreshed = True, set()
    assert gw._group_check(GROUP).ok                            # vẫn dùng số cũ


def test_short_identical_text_from_another_post_is_still_considered(env):
    gw, _ = env.make(items=[feed_item("Cần mua màn hình 24 inch", 50, counts=("3", "5"), labels=REACTED)]
                     + ITEMS[-3:])
    env.db.log_decision(w.gc_url(GROUP["group_url"]), "Nhóm test", w.text_key("Cần mua màn hình 24 inch"),
                        "Cần mua màn hình 24 inch", COMMENT, "x", post_url="https://www.facebook.com/groups/testgroup/posts/49/")
    env.db.add_post("https://www.facebook.com/groups/testgroup/posts/49/", "Nhóm test", GROUP["group_url"], "", 5)
    _, posts = gw.scan_group(GROUP)                             # bài khác (link 50) cùng chữ ngắn vẫn được xét
    assert [p["url"] for p in posts] == ["https://www.facebook.com/groups/testgroup/posts/50/"]


POOL = lambda g: [{"text": "x", "safe_text": "x", "image": None, "name": "sp"}]


def feed_visits(driver):
    return sum("sorting_setting" in u for u in driver.visited)


def test_scanned_group_waits_its_turn_in_the_next_round(env):
    gw, driver = env.make()
    gw.comment_post = lambda *a, **k: "Hoàn tất"
    gw.verify = lambda commenter: None
    gw.run([GROUP], None, POOL)
    assert feed_visits(driver) == 1
    assert env.db.group_yields(7)[GROUP["group_url"]]["scans"] == 1
    gw.run([GROUP], None, POOL)
    assert feed_visits(driver) == 1   # vừa quét xong: chưa tới lượt (GROUP_RESCAN_MINUTES), nhường nhóm khác


def test_daily_cap_still_joins_groups_and_verifies_comments(env):
    env.cfg.MAX_COMMENTED_POSTS_PER_DAY = 1
    done = env.db.add_post("https://www.facebook.com/groups/testgroup/posts/77/", "Nhóm test", GROUP["group_url"], "", 5)
    env.db.update_post(done, status="Hoàn tất")
    gw, driver = env.make()
    verified = []
    gw.verify = lambda commenter: verified.append(1)
    gw.run([GROUP], None, POOL)
    assert feed_visits(driver) == 0   # đủ bài hôm nay: không quét thêm
    assert verified == [1]            # nhưng vẫn kiểm tra lại các bài đã bình luận (trước đây bị bỏ qua)


def test_unavailable_group_is_reported_and_skipped_for_a_while(env):
    # nhóm Thanh Lý 08/10: "Bạn hiện không xem được nội dung này" -> trước đây cuộn trang trống 2 phút mỗi 5 phút
    env.db.save_group_stats(GROUP["group_url"], "Nhóm test", 417000, None, "")  # số thành viên đã biết từ trước
    gw, driver = env.make(about="Bạn hiện không xem được nội dung này", items=[], joined=False)
    gw.verify = lambda commenter: None
    gw.run([GROUP], None, POOL)
    assert env.db.get_join(GROUP["group_url"])["status"] == w.gc.UNAVAILABLE
    visits = len(driver.visited)
    gw.run([GROUP], None, POOL)
    assert len(driver.visited) == visits    # trong GROUP_UNAVAILABLE_RETRY_HOURS giờ không mở lại nhóm


def test_scan_window_check_and_scan_records_interactions(env):
    env.cfg.POST_MIN_ENGAGEMENT = 0
    gw, _ = env.make()
    result, posts = gw.check_and_scan(GROUP, 360)
    assert result == "ok" and sorted(p["url"][-3:] for p in posts) == ["/1/", "/3/"]
    y = env.db.group_yields(7)[GROUP["group_url"]]
    assert y["scans"] == 1 and y["interactions"] and y["interactions"] > 0   # có ước tương tác mỗi bài cho ưu tiên nhóm
    assert env.db.get_join(GROUP["group_url"])["status"] == w.gc.JOINED


def test_check_and_scan_reports_not_joined_group_for_the_comment_window(env):
    gw, _ = env.make(joined=False)
    env.db.save_group_stats(GROUP["group_url"], "Chợ màn hình Hà Nội", 12000, 50, "")
    gw.driver.find_elements = lambda by, xpath: [El()] if xpath == sel.XP_JOIN_BTN else []
    result, posts = gw.check_and_scan(GROUP, 30)
    assert result.startswith("chưa tham gia nhóm") and posts == []
    assert env.db.groups_with_status(w.gc.NOT_JOINED)[0]["group_url"] == GROUP["group_url"]


def test_text_key_ignores_post_age():
    assert w.text_key("Người A\n5 phút\nCần tìm màn") == w.text_key("Người A\n2 giờ\nCần tìm màn")
