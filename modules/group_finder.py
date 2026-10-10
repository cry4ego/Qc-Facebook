"""
Tìm nhóm Facebook mới theo từ khóa (Config.GROUP_SEARCH_QUERIES), giữ nhóm có tên chứa từ khóa quan trọng
(Config.GROUP_KEYWORDS), đủ đông thành viên, không thuộc tỉnh khác -> lưu data/groups_found.xlsx.
Các nhóm này được gộp vào danh sách nhóm; cuối mỗi vòng script tự tham gia, vòng sau bình luận.
"""
import os
import re
import time
import random
import unicodedata
import urllib.parse
from datetime import datetime

import pandas as pd
from selenium.webdriver.common.by import By

from modules import fb_selectors as sel

FOUND_COLUMNS = ["group_url", "group_name", "category", "region", "keywords", "privacy", "members", "activity",
                 "query", "found_at"]
HANOI = re.compile(r"hà nội|ha noi|hanoi|\bhn\b", re.IGNORECASE)
OTHER_REGION = re.compile(
    r"hcm|tphcm|sài gòn|sai gon|saigon|\bsg\b|hồ chí minh|đà nẵng|da nang|bình dương|đồng nai|cần thơ|biên hòa|thủ đức"
    r"|nha trang|hải phòng|quảng ninh|nghệ an|vinh\b|huế|quảng nam|phú yên|đắk lắk|gia lai|khánh hòa|thanh hóa"
    r"|bắc ninh|bắc giang|thái nguyên|nam định|hải dương|vũng tàu|long an|tây ninh|miền nam|miền trung", re.IGNORECASE)
# Nhóm không phải khách mua màn hình máy tính / PC
NOT_PC = re.compile(
    r"điện thoại|dien thoai|iphone|samsung|oppo|xiaomi|apple|chữa cháy|ô tô|xe máy|camera|tivi|\btv\b"
    r"|\bled\b|quảng cáo|màn hình ghép|máy chiếu|cho thuê|vỡ kính|màn hình laptop|pin và màn|\bpin\b"
    r"|handheld|steam ?deck|bàn ghế|rã xác|xác laptop|\bram pc\b|săn sale",
    re.IGNORECASE)
PC_WORDS = re.compile(r"máy tính|may tinh|gaming|linh kiện|công nghệ|gear", re.IGNORECASE)


def strip_accents(s):
    s = unicodedata.normalize("NFD", str(s).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return " " + re.sub(r"[^a-z0-9]+", " ", s).strip() + " "


def keyword_hits(name, keywords):
    """Các từ khóa có trong tên nhóm (không phân biệt hoa thường, có dấu / không dấu)"""
    n = strip_accents(name)
    return [k for k in keywords if strip_accents(k) in n]


def normalize_group_url(url):
    m = re.search(r"/groups/([^/?#]+)", str(url))
    return f"https://www.facebook.com/groups/{m.group(1)}/" if m else str(url)


def parse_count(text):
    """'1,8K' -> 1800, '64K' -> 64000, '1,2 Tr' -> 1200000, '649' -> 649"""
    m = re.search(r"([\d.,]+)\s*(K|N|Tr|triệu|M)?\b", text, re.IGNORECASE)
    if not m:
        return 0
    num = float(m.group(1).replace(".", "").replace(",", ".")) if m.group(2) else float(re.sub(r"[.,]", "", m.group(1)))
    unit = (m.group(2) or "").lower()
    return round(num * (1000 if unit in ("k", "n") else 1_000_000 if unit in ("tr", "triệu", "m") else 1))


def is_hanoi_group(group):
    """Nhóm Hà Nội: cột khu vực = Hà Nội hoặc tên nhóm có "Hà Nội" / "HN" (khác: nhóm toàn quốc)"""
    return group.get("region") == "Hà Nội" or bool(HANOI.search(group.get("group_name") or ""))


def min_members(name, config):
    """Số thành viên tối thiểu khi tìm nhóm mới: nhóm Hà Nội nhỏ vẫn đúng khách nên chỉ cần ít thành viên hơn"""
    return config.GROUP_MIN_MEMBERS_HANOI if HANOI.search(name) else config.MIN_GROUP_MEMBERS


def qualifies(name, config):
    """Tên nhóm có từ khóa quan trọng, không thuộc tỉnh khác, không phải nhóm LED / điện thoại / pin laptop..."""
    if OTHER_REGION.search(name) or NOT_PC.search(name):
        return False
    topic_hits = [k for k in keyword_hits(name, config.GROUP_KEYWORDS) if not HANOI.search(k)]
    return bool(topic_hits) or bool(HANOI.search(name) and PC_WORDS.search(name))


def refilter_found(config):
    """Áp lại bộ lọc cho groups_found.xlsx (khi bộ lọc thay đổi). Trả về số nhóm bị bỏ"""
    found = load_found(config.GROUPS_FOUND_FILE)
    keep = [g for g in found if qualifies(g["group_name"], config)]
    pd.DataFrame(keep, columns=FOUND_COLUMNS).to_excel(config.GROUPS_FOUND_FILE, index=False)
    return len(found) - len(keep)


def load_found(path):
    if not os.path.exists(path):
        return []
    return pd.read_excel(path).fillna("").to_dict("records")


def search_groups(driver, query, scrolls=4):
    """Kết quả tìm nhóm trên Facebook: [{url, name, privacy, members, activity}]"""
    driver.get(sel.GROUP_SEARCH_URL.format(query=urllib.parse.quote(query)))
    time.sleep(random.uniform(6, 9))
    for _ in range(scrolls):
        driver.execute_script("window.scrollBy(0, 2000)")
        time.sleep(random.uniform(2, 3))
    results = []
    for item in driver.find_elements(By.XPATH, sel.XP_FEED_ITEMS):
        try:
            links = [a for a in item.find_elements(By.XPATH, sel.XP_GROUP_LINKS) if a.text.strip()]
            lines = [l.strip() for l in item.text.split("\n") if l.strip()]
            if not links or len(lines) < 2:
                continue
            info = next((l for l in lines if "thành viên" in l or "members" in l), "")
            parts = [p.strip() for p in info.split("·")]
            results.append({
                "url": normalize_group_url(links[0].get_attribute("href")),
                "name": links[0].text.strip(),
                "privacy": parts[0] if parts else "",
                "members": parse_count(next((p for p in parts if "thành viên" in p or "members" in p), "")),
                "activity": next((p for p in parts if "bài viết" in p or "posts" in p), ""),
            })
        except Exception:
            continue
    return results


def find_groups(driver, config, logger, known_urls):
    """Tìm nhóm mới theo GROUP_SEARCH_QUERIES, lọc theo từ khóa + số thành viên, lưu GROUPS_FOUND_FILE.
    Trả về số nhóm mới thêm"""
    known = {normalize_group_url(u) for u in known_urls}
    found = load_found(config.GROUPS_FOUND_FILE)
    known |= {normalize_group_url(g["group_url"]) for g in found}
    added = 0
    for q in config.GROUP_SEARCH_QUERIES:
        try:
            results = search_groups(driver, q)
        except Exception as e:
            logger.error(f"  ✗ Lỗi tìm nhóm '{q}': {str(e).splitlines()[0][:120]}")
            continue
        new = 0
        for r in results:
            name = r["name"]
            hits = keyword_hits(name, config.GROUP_KEYWORDS)
            if r["url"] in known or r["members"] < min_members(name, config) or not qualifies(name, config):
                continue
            known.add(r["url"])
            activity = "" if "chưa đọc" in r["activity"] else r["activity"]  # nhóm đã tham gia hiện "… chưa đọc"
            found.append({
                "group_url": r["url"], "group_name": name, "category": "Tìm theo từ khóa",
                "region": "Hà Nội" if HANOI.search(name) else "Toàn quốc",
                "keywords": ", ".join(hits), "privacy": r["privacy"], "members": r["members"],
                "activity": activity, "query": q, "found_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
            new += 1
            logger.info(f"  + {name} ({r['members']:,} thành viên, {r['activity'] or '?'}) — từ khóa: {', '.join(hits)}")
        added += new
        logger.info(f"→ Tìm '{q}': {len(results)} kết quả, {new} nhóm mới phù hợp")
        time.sleep(random.uniform(5, 10))

    # Giữ tối đa MAX_FOUND_GROUPS nhóm: Hà Nội trước, rồi nhóm đông thành viên
    found.sort(key=lambda g: (g["region"] != "Hà Nội", -float(g["members"] or 0)))
    found = found[:config.MAX_FOUND_GROUPS]
    pd.DataFrame(found, columns=FOUND_COLUMNS).to_excel(config.GROUPS_FOUND_FILE, index=False)
    return added
