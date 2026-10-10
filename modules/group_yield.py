"""
Chọn nhóm để quét theo số bài cần mua tìm được + mức hoạt động của nhóm
(bảng group_scans + post_decisions trong YIELD_DAYS ngày, số thành viên / bài mỗi ngày trong group_stats).

  rank_by_yield : thứ tự quét (chạy 1 cửa sổ) — nhóm tương tác cao -> nhóm "Ưu tiên" -> nhóm có bài cần mua
                  (nhiều trước) -> nhóm chưa đủ lần quét để đánh giá -> nhóm ít khách (quét nhiều lần, 0 bài cần mua)
  scan_due      : nhóm đã tới lượt quét lại chưa (chạy 1 cửa sổ)
  group_score   : điểm ưu tiên nhóm — khách tìm màn hình, tương tác trung bình mỗi bài, số bài/ngày, số thành viên
  scan_interval : bao lâu quét lại 1 nhóm (cửa sổ QUÉT): nhóm tương tác cao 3 phút, nhóm có khách / đông bài 10 phút,
                  nhóm thường 60 phút, nhóm ít khách 24 giờ
  next_group    : nhóm cửa sổ QUÉT nên quét ngay (tới lượt + trễ hạn nhiều × điểm cao)
  scan_window   : chỉ xét bài đăng sau lần quét trước (+ SCAN_OVERLAP_MINUTES) -> quét lại rất nhanh
  posting_order : thứ tự đăng bài bán — nhóm có nhiều bài cần mua trước (khách đang tìm ở đó), rồi nhóm màn hình
"""
import random
import re
from datetime import datetime

EMPTY = {"scans": 0, "first_scan": None, "last_scan": None, "buy": 0, "interactions": None}
MONITOR_GROUP = re.compile(r"màn hình|man hinh", re.IGNORECASE)  # nhóm chuyên màn hình (theo tên nhóm)
NEVER_SCANNED_RATIO = 3  # nhóm chưa quét lần nào coi như trễ hạn 3 lần chu kỳ


def _yield(yields, group):
    return yields.get(group["group_url"]) or EMPTY


def _time(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def _minutes_since(text, now):
    return (now - _time(text)).total_seconds() / 60


def is_low_yield(y, config, now=None):
    """Nhóm ít khách: quét >= LOW_YIELD_MIN_SCANS lần, đã theo dõi >= LOW_YIELD_OBSERVE_HOURS giờ, 0 bài cần mua"""
    if y["buy"] or y["scans"] < config.LOW_YIELD_MIN_SCANS:
        return False
    first = y.get("first_scan")
    return bool(first) and _minutes_since(first, now or datetime.now()) >= config.LOW_YIELD_OBSERVE_HOURS * 60


def tier(y, config):
    """0 = có bài cần mua, 1 = chưa đủ lần quét để đánh giá, 2 = ít khách"""
    return 0 if y["buy"] else 2 if is_low_yield(y, config) else 1


def rank_by_yield(groups, yields, config):
    """Cùng hạng thì giữ thứ tự cũ (khu vực, số thành viên… theo group_priority)"""
    def key(item):
        i, g = item
        y = _yield(yields, g)
        return not g.get("hot"), not g.get("priority"), tier(y, config), -y["buy"], i
    return [g for _, g in sorted(enumerate(groups), key=key)]


def scan_due(group, yields, config, now=None):
    if group.get("hot"):
        return True  # nhóm tương tác cao: luôn quét (và còn được quét lại mỗi HOT_RESCAN_MINUTES phút)
    y = _yield(yields, group)
    if not y["last_scan"]:
        return True
    wait = config.LOW_YIELD_RESCAN_HOURS * 60 if is_low_yield(y, config, now) else config.GROUP_RESCAN_MINUTES
    return _minutes_since(y["last_scan"], now or datetime.now()) >= wait


# ---------- cửa sổ QUÉT (chạy song song) ----------
def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def group_score(group, stats, y):
    """Điểm ưu tiên nhóm (~0..7.5): bài cần mua tìm được (nặng nhất — 5 bài/tuần là tối đa), tương tác trung bình mỗi
    bài, số bài mới/ngày, số thành viên (mỗi tiêu chí tối đa 1); nhóm tương tác cao (HOT_GROUPS) +2, "Ưu tiên" +0,5"""
    members = (stats or {}).get("members") or _number(group.get("members"))
    posts_per_day = (stats or {}).get("posts_today") or 0
    score = (3 * min(y["buy"], 5) / 5 + min(y.get("interactions") or 0, 30) / 30
             + min(posts_per_day, 300) / 300 + min(members, 400_000) / 400_000)
    return round(score + (2 if group.get("hot") else 0) + (0.5 if group.get("priority") else 0), 3)


def scan_interval(group, stats, y, config, now=None):
    """Bao lâu (phút) quét lại nhóm này"""
    if group.get("hot"):
        return config.HOT_RESCAN_MINUTES
    if is_low_yield(y, config, now):
        return config.LOW_YIELD_RESCAN_HOURS * 60
    if y["buy"] or ((stats or {}).get("posts_today") or 0) >= config.SCAN_ACTIVE_POSTS_PER_DAY:
        return config.SCAN_ACTIVE_MINUTES
    return config.GROUP_RESCAN_MINUTES


def next_group(groups, stats, yields, config, last_try=None, now=None):
    """Nhóm nên quét ngay: trong các nhóm đã tới lượt, chọn nhóm có (điểm × mức trễ hạn) cao nhất. None = chưa nhóm
    nào tới lượt. last_try: {link nhóm: lần thử gần nhất} — nhóm bị bỏ qua (chưa tham gia, không xem được…) cũng
    phải chờ tới lượt sau, không thử lại liên tục"""
    now = now or datetime.now()
    best, best_key = None, None
    for g in groups:
        url = g["group_url"]
        y, st = _yield(yields, g), stats.get(url)
        last = max(filter(None, [y["last_scan"], (last_try or {}).get(url)]), default=None)
        interval = scan_interval(g, st, y, config, now)
        if last:
            waited = _minutes_since(last, now)
            if waited < interval:
                continue
            overdue = min(waited / interval, NEVER_SCANNED_RATIO)
        else:
            overdue = NEVER_SCANNED_RATIO
        key = group_score(g, st, y) * overdue + (1 if g.get("hot") else 0)
        if best_key is None or key > best_key:
            best, best_key = g, key
    return best


def scan_window(y, config, now=None):
    """Chỉ xét bài đăng trong ... phút: từ lần quét trước (+ dự phòng); nhóm chưa quét -> MAX_POST_AGE_MINUTES"""
    if not y["last_scan"]:
        return config.MAX_POST_AGE_MINUTES
    since = _minutes_since(y["last_scan"], now or datetime.now()) + config.SCAN_OVERLAP_MINUTES
    return int(min(config.MAX_POST_AGE_MINUTES, max(15, since)))


def posting_order(groups, yields, shuffle=random.shuffle):
    """Nhóm có bài cần mua trước (nhiều trước), rồi nhóm màn hình, rồi nhóm khác — mỗi phần sau xáo trộn để mỗi ngày
    đăng vào nhóm khác nhau"""
    best = sorted((g for g in groups if _yield(yields, g)["buy"]), key=lambda g: -_yield(yields, g)["buy"])
    rest = [g for g in groups if not _yield(yields, g)["buy"]]
    monitor = [g for g in rest if MONITOR_GROUP.search(g.get("group_name") or "")]
    other = [g for g in rest if not MONITOR_GROUP.search(g.get("group_name") or "")]
    shuffle(monitor)
    shuffle(other)
    return best + monitor + other
