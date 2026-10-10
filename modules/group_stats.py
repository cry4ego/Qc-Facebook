"""
Thông tin chất lượng nhóm: số thành viên và số bài mỗi ngày, đọc từ trang Giới thiệu (…/groups/<nhóm>/about).
Lưu vào CSDL (bảng group_stats) kèm thời gian; dùng lại trong GROUP_STATS_CACHE_HOURS giờ (mặc định 24) —
chỉ đọc lại khi cũ, khi lần trước bị lỗi (sau GROUP_STATS_RETRY_MINUTES phút), hoặc khi bạn bấm "Cập nhật số thành viên".
"""
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from selenium.webdriver.common.by import By

from modules import fb_selectors as sel
from modules.group_finder import parse_count

ABOUT_WAIT_SECONDS = 12
FMT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class GroupInfo:
    members: int = None       # None = không đọc được
    posts_today: int = None   # số bài mới mỗi ngày (None = trang không ghi)
    activity: str = ""        # câu gốc trên trang, vd "Hôm nay có 236 bài viết mới"


def _int(s):
    digits = re.sub(r"\D", "", s or "")
    return int(digits) if digits else None


def parse_about(text):
    """Đọc số thành viên + số bài/ngày từ chữ trang Giới thiệu nhóm"""
    text = text or ""
    m = sel.ABOUT_TOTAL_MEMBERS.search(text)
    members = _int(m.group(1)) if m else None
    if members is None:  # "417,7K thành viên" — lấy số lớn nhất (tránh "7 thành viên khác là quản trị viên")
        found = [parse_count(x) for x in sel.ABOUT_MEMBERS.findall(text)]
        members = max(found) if found else None

    m = sel.ABOUT_POSTS_TODAY.search(text)
    if m:
        return GroupInfo(members, _int(m.group(1) or m.group(2)), m.group(0))
    m = sel.ABOUT_POSTS_PERIOD.search(text)
    n = _int(m.group(1) or m.group(3)) if m else None
    if n is not None:
        unit = (m.group(2) or m.group(4)).lower()
        return GroupInfo(members, round(n / (30 if unit in ("tháng", "month") else 7)), m.group(0))
    return GroupInfo(members, None, "")


def fetch_group_info(driver, group_url):
    """Mở trang Giới thiệu của nhóm, chờ tới khi hiện số thành viên, đọc thông tin"""
    driver.get(sel.GROUP_ABOUT_URL.format(group_url=group_url.rstrip("/")))
    info, end = GroupInfo(), time.time() + ABOUT_WAIT_SECONDS
    while time.time() < end:
        time.sleep(2)
        mains = driver.find_elements(By.XPATH, sel.XP_MAIN)
        info = parse_about(mains[0].text if mains else driver.find_element(By.TAG_NAME, "body").text)
        if info.members is not None:
            break
    return info


def is_fresh(row, config, now=None):
    """Dữ liệu trong cache còn dùng được không"""
    if not row or not row.get("fetched_at"):
        return False
    age = (now or datetime.now()) - datetime.strptime(row["fetched_at"], FMT)
    if row.get("error"):
        return age < timedelta(minutes=config.GROUP_STATS_RETRY_MINUTES)
    return age < timedelta(hours=config.GROUP_STATS_CACHE_HOURS)


def group_info(driver, db, config, group, force=False):
    """Thông tin nhóm (dict: members, posts_today, activity, fetched_at, error) — từ cache hoặc đọc lại trang Giới thiệu.
    Lỗi tạm thời (mạng, Chrome…) KHÔNG lưu vào cache: dùng số đọc được lần trước nếu có, lần sau đọc lại ngay.
    Trang mở được mà không thấy số thành viên: lưu lỗi, đọc lại sau GROUP_STATS_RETRY_MINUTES phút."""
    url = group["group_url"]
    row = db.get_group_stats(url)
    if not force and is_fresh(row, config):
        return row
    try:
        info = fetch_group_info(driver, url)
    except Exception as e:
        error = f"lỗi mở trang Giới thiệu: {str(e).splitlines()[0][:120]}"
        if row and row.get("members") is not None:
            return {**row, "error": error}  # dùng tạm số cũ
        return {"group_url": url, "members": None, "posts_today": None, "activity": "", "error": error}
    error = "" if info.members is not None else "không đọc được số thành viên trên trang Giới thiệu"
    db.save_group_stats(url, group.get("group_name", ""), info.members, info.posts_today, info.activity, error)
    return db.get_group_stats(url)
