"""
Các file Excel danh sách nhóm (quản lý trên web, bảng group_lists):
  main   — data/groups.xlsx (danh sách gốc, có thể chỉ lấy nhóm thuộc TARGET_REGION)
  found  — data/groups_found.xlsx (nhóm script tự tìm theo từ khóa)
  upload — file bạn tải lên trên web, lưu ở data/group_lists/<key>.xlsx (đã chuẩn hóa cột)
Script gộp mọi danh sách đang bật (bỏ trùng link), xếp theo ưu tiên rồi quét / bình luận / tham gia.
"""
import os
import re
import time

import pandas as pd

from modules.group_finder import normalize_group_url, parse_count, keyword_hits, load_found, HANOI, FOUND_COLUMNS

LIST_COLUMNS = ["group_url", "group_name", "category", "region", "privacy", "members", "activity"]
LISTS_DIR = "group_lists"


def _rel(path, config):
    """Đường dẫn tương đối với thư mục dự án (khác ổ đĩa thì giữ đường dẫn đầy đủ)"""
    try:
        return os.path.relpath(path, config.BASE_DIR)
    except ValueError:
        return os.path.abspath(path)


def ensure_builtin(db, config):
    """Thêm 2 danh sách có sẵn vào bảng (lần đầu)"""
    rel = lambda p: _rel(p, config)
    db.add_group_list("main", "Danh sách gốc (groups.xlsx)", rel(config.GROUPS_FILE), "main",
                      enabled=1, region_filter=1 if config.TARGET_REGION else 0)
    db.add_group_list("found", "Nhóm tự tìm theo từ khóa (groups_found.xlsx)", rel(config.GROUPS_FOUND_FILE), "found",
                      enabled=1, region_filter=0)


def _pick(columns, *patterns):
    for c in columns:
        if any(re.search(p, str(c), re.IGNORECASE) for p in patterns):
            return c
    return None


def parse_group_file(path):
    """Đọc 1 file Excel/CSV bất kỳ có cột link nhóm Facebook. Trả về danh sách nhóm (cột chuẩn LIST_COLUMNS).
    Tự nhận cột: link (ô có facebook.com/groups/), tên nhóm, số thành viên, mức hoạt động, quyền riêng tư."""
    if path.lower().endswith(".csv"):
        sheets = {"csv": pd.read_csv(path, dtype=str)}
    else:
        sheets = pd.read_excel(path, sheet_name=None, dtype=str)
    best = []
    for df in sheets.values():
        df = df.fillna("")
        if df.empty:
            continue
        # cột link = cột có nhiều ô chứa link nhóm nhất
        counts = {c: df[c].str.contains(r"facebook\.com/groups/", case=False, regex=True).sum() for c in df.columns}
        url_col = max(counts, key=counts.get)
        if not counts[url_col]:
            continue
        others = [c for c in df.columns if c != url_col]
        name_col = _pick(others, r"tên", r"name", r"nhóm", r"group")
        mem_col = _pick(others, r"thành viên", r"member")
        act_col = _pick(others, r"hoạt động", r"activity", r"bài viết", r"post")
        priv_col = _pick(others, r"riêng tư", r"privacy", r"quyền", r"công khai")
        cat_col = _pick(others, r"phân loại", r"category", r"loại")
        rows, seen = [], set()
        for _, r in df.iterrows():
            m = re.search(r"https?://(?:www\.|m\.|web\.)?facebook\.com/groups/[^\s\"']+", str(r[url_col]))
            if not m:
                continue
            url = normalize_group_url(m.group(0))
            if url in seen:
                continue
            seen.add(url)
            name = str(r[name_col]).strip() if name_col else ""
            rows.append({
                "group_url": url,
                "group_name": name or url.rstrip("/").split("/")[-1],
                "category": str(r[cat_col]).strip() if cat_col else "",
                "region": "Hà Nội" if HANOI.search(name) else "",
                "privacy": str(r[priv_col]).strip() if priv_col else "",
                "members": parse_count(str(r[mem_col])) if mem_col else 0,
                "activity": str(r[act_col]).strip() if act_col else "",
            })
        if len(rows) > len(best):
            best = rows
    return best


def save_uploaded(db, config, file_storage, name):
    """Lưu file tải lên từ web: chuẩn hóa -> data/group_lists/<key>.xlsx, thêm vào bảng (bật sẵn).
    Trả về (key, số nhóm)"""
    ext = os.path.splitext(file_storage.filename or "")[1].lower()
    if ext not in (".xlsx", ".csv"):
        raise ValueError("Chỉ nhận file .xlsx hoặc .csv")
    folder = os.path.join(config.DATA_DIR, LISTS_DIR)
    os.makedirs(os.path.join(folder, "goc"), exist_ok=True)
    key = f"u{int(time.time())}"
    original = os.path.join(folder, "goc", f"{key}{ext}")
    file_storage.save(original)
    rows = parse_group_file(original)
    if not rows:
        os.remove(original)
        raise ValueError("Không tìm thấy link nhóm Facebook nào (cần ô dạng https://www.facebook.com/groups/...)")
    path = os.path.join(folder, f"{key}.xlsx")
    pd.DataFrame(rows, columns=LIST_COLUMNS).to_excel(path, index=False)
    label = name.strip() or os.path.splitext(file_storage.filename)[0]
    db.add_group_list(key, label, _rel(path, config), "upload", enabled=1, region_filter=0)
    return key, len(rows)


def list_path(lst, config):
    return os.path.join(config.BASE_DIR, lst["path"])


def read_list(lst, config, names=None, apply_filter=True):
    """Các nhóm trong 1 danh sách (đã áp 'chỉ nhóm TARGET_REGION' nếu bật).
    names: {link: tên} script đọc được — điền cho link chưa có tên"""
    path = list_path(lst, config)
    if not os.path.exists(path):
        return []
    try:
        rows = load_found(path) if lst["kind"] == "found" else pd.read_excel(path).fillna("").to_dict("records")
    except Exception:
        return []  # file đang được ghi / hỏng: lượt sau đọc lại
    rows = [r for r in rows if str(r.get("group_url", "")).strip()]
    for r in rows:
        if not str(r.get("group_name", "")).strip():
            url = normalize_group_url(r["group_url"])
            r["group_name"] = (names or {}).get(url) or url.rstrip("/").split("/")[-1]
            if not r.get("region") and HANOI.search(r["group_name"]):
                r["region"] = "Hà Nội"
    if apply_filter and lst["region_filter"] and config.TARGET_REGION:
        rows = [r for r in rows if r.get("region") == config.TARGET_REGION]
    return rows


# ---------- Sửa file Excel danh sách nhóm từ web ----------
def _read_df(lst, config):
    path = list_path(lst, config)
    if os.path.exists(path):
        return pd.read_excel(path, dtype=object).fillna("")
    return pd.DataFrame(columns=FOUND_COLUMNS if lst["kind"] == "found" else LIST_COLUMNS)


def _save_df(df, lst, config):
    """Ghi file qua file tạm rồi thay thế (script không đọc phải file ghi dở)"""
    path = list_path(lst, config)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp.xlsx"
    df.to_excel(tmp, index=False)
    try:
        os.replace(tmp, path)
    except PermissionError:
        os.remove(tmp)
        raise ValueError(f"File {os.path.basename(path)} đang mở trong Excel — đóng file rồi thử lại")


def _find(df, url):
    url = normalize_group_url(url)
    hits = [i for i, u in df["group_url"].items() if normalize_group_url(u) == url]
    return hits[0] if hits else None


def parse_links(text):
    """Đọc link nhóm trong đoạn văn bản dán vào. Mỗi dòng: 'link' hoặc 'link | tên nhóm' (hoặc tab / dấu phẩy).
    Trả về ([(link, tên)], số dòng không có link)"""
    found, bad = [], 0
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        urls = re.findall(r"https?://(?:www\.|m\.|web\.)?facebook\.com/groups/[^\s|,;\t\"']+", line)
        if not urls:
            bad += 1
            continue
        # tên nhóm chỉ lấy khi có dấu | hoặc tab ngăn cách (chữ thường lẫn trong đoạn văn không phải tên)
        name = ""
        if len(urls) == 1:
            before, after = line.split(urls[0], 1)
            if re.search(r"[|\t]", after):      # "link | tên"
                name = re.split(r"[|\t]", after, maxsplit=1)[1]
            elif re.search(r"[|\t]", before):   # "tên | link"
                name = re.split(r"[|\t]", before)[0]
            name = re.sub(r"^[\s|,;:\t–-]+|[\s|,;:\t–-]+$", "", name)
        found += [(normalize_group_url(u), name) for u in urls]
    return found, bad


def _new_row(df, lst, url, name="", members=0, activity="", region=None):
    row = {c: "" for c in df.columns}
    row.update(group_url=url, group_name=name, members=members or 0, activity=activity,
               region=region if region is not None else ("Hà Nội" if HANOI.search(name) else ""))
    if "category" in df.columns:
        row["category"] = "Thêm trên web"
    if "found_at" in df.columns:
        row["found_at"] = time.strftime("%Y-%m-%d %H:%M")
    return row


def add_links(lst, config, text):
    """Thêm các link dán vào danh sách. Trả về (đã thêm, trùng, dòng không có link, bị ẩn do 'chỉ nhóm Hà Nội')"""
    links, bad = parse_links(text)
    df = _read_df(lst, config)
    for c in LIST_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    existing = {normalize_group_url(u) for u in df["group_url"]}
    added, dup, hidden, new_rows = 0, 0, 0, []
    for url, name in links:
        if url in existing:
            dup += 1
            continue
        existing.add(url)
        row = _new_row(df, lst, url, name)
        new_rows.append(row)
        added += 1
        if lst["region_filter"] and config.TARGET_REGION and row["region"] != config.TARGET_REGION:
            hidden += 1
    if new_rows:
        _save_df(pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True), lst, config)
    return added, dup, bad, hidden


def update_group(lst, config, old_url, fields):
    """Sửa 1 nhóm trong file (link, tên, số thành viên, hoạt động, khu vực)"""
    df = _read_df(lst, config)
    i = _find(df, old_url)
    if i is None:
        raise ValueError("Không tìm thấy nhóm này trong file (có thể file vừa thay đổi) — tải lại trang")
    new_url = normalize_group_url(fields.get("group_url") or old_url)
    if not re.search(r"facebook\.com/groups/[^/]+/$", new_url):
        raise ValueError("Link nhóm không hợp lệ (cần dạng https://www.facebook.com/groups/...)")
    j = _find(df, new_url)
    if j is not None and j != i:
        raise ValueError("Link này đã có trong danh sách")
    for c in ("region", "members", "activity"):
        if c not in df.columns:
            df[c] = ""
    df.at[i, "group_url"] = new_url
    df.at[i, "group_name"] = str(fields.get("group_name", "")).strip()
    df.at[i, "members"] = parse_count(str(fields.get("members") or 0))
    df.at[i, "activity"] = str(fields.get("activity", "")).strip()
    df.at[i, "region"] = str(fields.get("region", "")).strip()
    _save_df(df, lst, config)
    return new_url


def delete_group(lst, config, url):
    df = _read_df(lst, config)
    i = _find(df, url)
    if i is None:
        raise ValueError("Không tìm thấy nhóm này trong file — tải lại trang")
    _save_df(df.drop(index=i).reset_index(drop=True), lst, config)


def create_list(db, config, name):
    """Tạo danh sách trống mới (để dán link vào). Trả về key"""
    key = f"u{int(time.time() * 1000)}"
    path = os.path.join(config.DATA_DIR, LISTS_DIR, f"{key}.xlsx")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(columns=LIST_COLUMNS).to_excel(path, index=False)
    db.add_group_list(key, name.strip() or "Nhóm dán thêm", _rel(path, config), "upload", enabled=1, region_filter=0)
    return key


def group_priority(groups, config):
    """Xếp nhóm: PRIORITY_REGION trước, rồi điểm = (hoạt động + số thành viên)
    x từ khóa quan trọng trong tên nhóm (GROUP_KEYWORDS: mỗi từ khóa +25%, tối đa 3) x2 nhóm màn hình, x0,7 nhóm laptop"""
    def members(g):
        try:
            return float(g.get("members") or 0)
        except ValueError:
            return 0
    top = max([members(g) for g in groups] + [1])

    def score(g):
        text = str(g.get("activity") or "")
        m = re.search(r"\d+", text)
        per_day = int(m.group()) / (7 if "tuần" in text else 30 if "tháng" in text else 1) if m else None
        # chưa có số liệu hoạt động -> ước theo số thành viên (nhóm 20k+ thành viên ~ 30 bài/ngày)
        activity = min(per_day, 100) / 100 if per_day is not None else 0.3 * min(1, members(g) / 20000)
        name = str(g.get("group_name", ""))
        hits = keyword_hits(name, [k for k in config.GROUP_KEYWORDS if k != config.PRIORITY_REGION])
        boost = 1 + 0.25 * min(len(hits), 3)
        if re.search(r"màn hình|man hinh", name, re.IGNORECASE):
            boost *= 2    # nhóm màn hình: đúng khách nhất
        elif re.search(r"laptop|lap top", name, re.IGNORECASE) and not re.search(r"\bpc\b", name, re.IGNORECASE):
            boost *= 0.7  # nhóm chỉ về laptop: không ưu tiên
        return (activity + members(g) / top) * boost
    # nhóm được tick "Ưu tiên" trên web (hoặc thuộc danh sách được tick "Ưu tiên") luôn chạy trước
    return sorted(groups, key=lambda g: (not g.get("priority"), g.get("region") != config.PRIORITY_REGION, -score(g)))


def load_groups(db, config, enabled_only=True):
    """Gộp nhóm từ các danh sách đang bật (bỏ trùng link), mỗi nhóm ghi kèm tên danh sách ('list')"""
    ensure_builtin(db, config)
    groups, seen, prio, names = [], {}, db.priority_urls(), db.group_names()
    for lst in db.group_lists(enabled_only=enabled_only):
        for g in read_list(lst, config, names):
            url = normalize_group_url(g["group_url"])
            if url in seen:
                if lst["priority"]:
                    seen[url]["priority"] = True  # nhóm trùng: thuộc 1 danh sách ưu tiên là đủ
                continue
            seen[url] = {**g, "group_url": url, "list": lst["name"],
                         "priority": bool(lst["priority"]) or url in prio}
            groups.append(seen[url])
    return groups
