"""
Cơ sở dữ liệu SQLite lưu mọi hoạt động bình luận để kiểm soát script (web quản lý đọc từ đây).

Bảng:
  posts     — mỗi bài viết đã xử lý (1 dòng / bài)
  comments  — từng bình luận đã gửi vào bài (3 dòng / bài)
  runs      — mỗi lượt quét nhóm
  settings  — cài đặt điều khiển từ web (vd tạm dừng)
  products  — sản phẩm để bình luận (ảnh, giá, bản có / không SĐT), bật/tắt trên web
  group_lists — các file Excel danh sách nhóm, bật/tắt trên web
"""
import os
import json
import sqlite3
from datetime import datetime, timedelta

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    post_url      TEXT UNIQUE NOT NULL,
    group_name    TEXT,
    group_url     TEXT,
    post_text     TEXT,
    post_age_min  INTEGER,
    found_at      TEXT,
    status        TEXT,      -- Hoàn tất / Một phần / Thất bại / Bỏ qua: đã có bình luận
    screenshot    TEXT,      -- tên file trong data/screenshots
    verified_at   TEXT,
    verify_result TEXT       -- kết quả kiểm tra lại sau ~1 giờ
);
CREATE TABLE IF NOT EXISTS comments (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id   INTEGER NOT NULL REFERENCES posts(id),
    idx       INTEGER,       -- bình luận số 1/2/3
    text      TEXT,
    image     TEXT,
    sent_at   TEXT,
    status    TEXT,          -- Đã đăng / Chờ duyệt / Bị chặn / Lỗi
    detail    TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT,
    finished_at     TEXT,
    groups_scanned  INTEGER DEFAULT 0,
    new_posts       INTEGER DEFAULT 0,
    commented_posts INTEGER DEFAULT 0,
    note            TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS safe_groups (   -- nhóm đã từ chối bình luận -> dùng bản không SĐT/địa chỉ
    group_url  TEXT PRIMARY KEY,
    group_name TEXT,
    since      TEXT,
    reason     TEXT,
    stop       INTEGER DEFAULT 0  -- 1 = bản không SĐT/địa chỉ cũng bị từ chối -> ngừng bình luận nhóm này
);
CREATE TABLE IF NOT EXISTS group_join (    -- kết quả tự tham gia nhóm
    group_url  TEXT PRIMARY KEY,
    group_name TEXT,
    status     TEXT,   -- Đã tham gia / Chờ duyệt / Cần trả lời câu hỏi / Lỗi
    note       TEXT,
    clicked_at TEXT,   -- lần cuối bấm "Tham gia nhóm"
    checked_at TEXT
);
CREATE TABLE IF NOT EXISTS products (      -- mỗi sản phẩm bật = 1 bình luận (kèm ảnh) vào mỗi bài
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    price      TEXT,
    new_price  TEXT,      -- giá mua mới (để so sánh trong bình luận: {giá_mới}, {tiết_kiệm})
    image      TEXT,      -- tên file trong data/images
    text       TEXT,      -- bình luận đầy đủ (có SĐT/địa chỉ)
    safe_text  TEXT,      -- bình luận không SĐT/địa chỉ (trống = tự bỏ dòng có SĐT)
    active     INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS comment_variants (  -- nhiều mẫu bình luận cho 1 sản phẩm, mỗi bài chọn ngẫu nhiên 1 mẫu
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   INTEGER NOT NULL,
    text         TEXT,      -- bản đầy đủ (có SĐT/địa chỉ)
    safe_text    TEXT,      -- bản không SĐT/địa chỉ (trống = tự bỏ dòng có SĐT)
    active       INTEGER DEFAULT 1,
    used_count   INTEGER DEFAULT 0,
    last_used_at TEXT,
    created_at   TEXT,
    updated_at   TEXT
);
CREATE TABLE IF NOT EXISTS group_lists (   -- file Excel danh sách nhóm
    key           TEXT PRIMARY KEY,
    name          TEXT,
    path          TEXT,     -- đường dẫn file (tương đối với thư mục dự án)
    kind          TEXT,     -- main / found / upload
    enabled       INTEGER DEFAULT 1,
    region_filter INTEGER DEFAULT 0,  -- 1 = chỉ dùng nhóm thuộc TARGET_REGION
    priority      INTEGER DEFAULT 0,  -- 1 = mọi nhóm trong danh sách này được chạy trước
    created_at    TEXT
);
CREATE TABLE IF NOT EXISTS group_names (      -- tên nhóm script đọc được khi mở trang nhóm (link dán thêm chưa có tên)
    group_url  TEXT PRIMARY KEY,
    group_name TEXT
);
CREATE TABLE IF NOT EXISTS removed_groups (    -- nhóm bạn xóa khỏi danh sách tự tìm: không tự thêm lại
    group_url  TEXT PRIMARY KEY,
    removed_at TEXT
);
CREATE TABLE IF NOT EXISTS priority_groups (  -- nhóm được tick "Ưu tiên" trên web: chạy trước
    group_url  TEXT PRIMARY KEY,
    group_name TEXT,
    since      TEXT
);
"""

# Bản nội dung bình luận
FULL = "Đầy đủ"
SAFE = "Không SĐT/địa chỉ"

# Trạng thái bình luận
SENT = "Đã đăng"
PENDING = "Chờ duyệt"
BLOCKED = "Bị chặn"
ERROR = "Lỗi"
REJECTED = "Bị từ chối"                    # Facebook/nhóm gắn nhãn "Bị từ chối" (chưa xóa được)
REJECTED_DELETED = "Bị từ chối · đã xóa"   # đã tự xóa bình luận bị từ chối


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)
            # nâng cấp CSDL cũ: thêm cột variant (bản nội dung đã dùng)
            cols = [r["name"] for r in c.execute("PRAGMA table_info(comments)")]
            if "variant" not in cols:
                c.execute("ALTER TABLE comments ADD COLUMN variant TEXT")
            cols = [r["name"] for r in c.execute("PRAGMA table_info(safe_groups)")]
            if "stop" not in cols:
                c.execute("ALTER TABLE safe_groups ADD COLUMN stop INTEGER DEFAULT 0")
            cols = [r["name"] for r in c.execute("PRAGMA table_info(products)")]
            if cols and "new_price" not in cols:
                c.execute("ALTER TABLE products ADD COLUMN new_price TEXT")
            cols = [r["name"] for r in c.execute("PRAGMA table_info(comments)")]
            if "variant_id" not in cols:
                c.execute("ALTER TABLE comments ADD COLUMN variant_id INTEGER")  # mẫu bình luận đã dùng
            cols = [r["name"] for r in c.execute("PRAGMA table_info(group_lists)")]
            if "priority" not in cols:
                c.execute("ALTER TABLE group_lists ADD COLUMN priority INTEGER DEFAULT 0")

    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # cho phép web đọc trong lúc script đang ghi
        return conn

    def query(self, sql, params=()):
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    def execute(self, sql, params=()):
        with self._conn() as c:
            cur = c.execute(sql, params)
            return cur.lastrowid

    # ---- posts ----
    def has_post(self, post_url):
        return bool(self.query("SELECT 1 FROM posts WHERE post_url = ?", (post_url,)))

    def add_post(self, post_url, group_name, group_url, post_text, post_age_min):
        return self.execute(
            "INSERT INTO posts (post_url, group_name, group_url, post_text, post_age_min, found_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (post_url, group_name, group_url, post_text, post_age_min, now_str(), "Đang bình luận"))

    def fix_interrupted(self):
        """Bài kẹt "Đang bình luận" do script bị tắt giữa chừng: chưa gửi được gì -> xóa để vòng sau bình luận lại;
        đã gửi được 1 phần -> ghi 'Một phần'. Trả về số bài được trả lại hàng chờ"""
        stuck = self.query("SELECT id FROM posts WHERE status = 'Đang bình luận'")
        retry = 0
        for p in stuck:
            if self.query("SELECT 1 FROM comments WHERE post_id = ?", (p["id"],)):
                self.execute("UPDATE posts SET status = 'Một phần' WHERE id = ?", (p["id"],))
            else:
                self.execute("DELETE FROM posts WHERE id = ?", (p["id"],))
                retry += 1
        return retry

    def update_post(self, post_id, **fields):
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.execute(f"UPDATE posts SET {cols} WHERE id = ?", (*fields.values(), post_id))

    def add_comment(self, post_id, idx, text, image, status, detail="", variant=FULL, variant_id=None):
        return self.execute(
            "INSERT INTO comments (post_id, idx, text, image, sent_at, status, detail, variant, variant_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (post_id, idx, text, image, now_str(), status, detail, variant, variant_id))

    # ---- bản an toàn (không SĐT/địa chỉ) ----
    def use_safe(self, group_url):
        """Dùng bản an toàn cho nhóm này? (nhóm từng từ chối, hoặc đã bật cho mọi nhóm)"""
        if self.get_setting("safe_all", "0") == "1":
            return True
        return bool(group_url) and bool(self.query("SELECT 1 FROM safe_groups WHERE group_url = ?", (group_url,)))

    def mark_safe(self, group_url, group_name, reason):
        """Chuyển nhóm sang bản an toàn (chỉ ghi lần đầu). Trả về True nếu vừa chuyển"""
        if not group_url or self.use_safe(group_url):
            return False
        self.execute("INSERT OR IGNORE INTO safe_groups (group_url, group_name, since, reason) VALUES (?, ?, ?, ?)",
                     (group_url, group_name, now_str(), reason))
        return True

    def mark_stop(self, group_url, group_name, reason):
        """Bản không SĐT/địa chỉ cũng bị từ chối -> ngừng bình luận nhóm này"""
        if not group_url:
            return
        self.execute("INSERT INTO safe_groups (group_url, group_name, since, reason, stop) VALUES (?, ?, ?, ?, 1) "
                     "ON CONFLICT(group_url) DO UPDATE SET stop = 1, reason = excluded.reason, since = excluded.since",
                     (group_url, group_name, now_str(), reason))

    def is_stopped(self, group_url):
        return bool(self.query("SELECT 1 FROM safe_groups WHERE group_url = ? AND stop = 1", (group_url,)))

    # ---- tham gia nhóm ----
    def get_join(self, group_url):
        rows = self.query("SELECT * FROM group_join WHERE group_url = ?", (group_url,))
        return rows[0] if rows else None

    def set_join(self, group_url, group_name, status, note="", clicked=False):
        now = now_str()
        self.execute(
            "INSERT INTO group_join (group_url, group_name, status, note, clicked_at, checked_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(group_url) DO UPDATE SET group_name = excluded.group_name, status = excluded.status, "
            "note = excluded.note, checked_at = excluded.checked_at, "
            "clicked_at = COALESCE(excluded.clicked_at, group_join.clicked_at)",
            (group_url, group_name, status, note, now if clicked else None, now))

    def joins_today(self):
        """Số nhóm đã bấm Tham gia hôm nay"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.query("SELECT COUNT(*) AS n FROM group_join WHERE clicked_at LIKE ?", (today + "%",))[0]["n"]

    # ---- sản phẩm ----
    def products(self, active_only=False):
        sql = "SELECT * FROM products" + (" WHERE active = 1" if active_only else "") + " ORDER BY id"
        return self.query(sql)

    def get_product(self, product_id):
        rows = self.query("SELECT * FROM products WHERE id = ?", (product_id,))
        return rows[0] if rows else None

    def add_product(self, **fields):
        fields.update(created_at=now_str(), updated_at=now_str())
        cols = ", ".join(fields)
        return self.execute(f"INSERT INTO products ({cols}) VALUES ({', '.join('?' * len(fields))})",
                            tuple(fields.values()))

    def update_product(self, product_id, **fields):
        fields["updated_at"] = now_str()
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.execute(f"UPDATE products SET {cols} WHERE id = ?", (*fields.values(), product_id))

    def delete_product(self, product_id):
        self.execute("DELETE FROM products WHERE id = ?", (product_id,))

    # ---- mẫu bình luận ----
    def variants(self, product_id=None, active_only=False):
        sql, params = "SELECT * FROM comment_variants WHERE 1 = 1", []
        if product_id is not None:
            sql += " AND product_id = ?"
            params.append(product_id)
        if active_only:
            sql += " AND active = 1"
        return self.query(sql + " ORDER BY product_id, id", params)

    def get_variant(self, variant_id):
        rows = self.query("SELECT * FROM comment_variants WHERE id = ?", (variant_id,))
        return rows[0] if rows else None

    def add_variant(self, product_id, text, safe_text="", active=1):
        return self.execute("INSERT INTO comment_variants (product_id, text, safe_text, active, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?)", (product_id, text, safe_text, active, now_str(), now_str()))

    def update_variant(self, variant_id, **fields):
        fields["updated_at"] = now_str()
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.execute(f"UPDATE comment_variants SET {cols} WHERE id = ?", (*fields.values(), variant_id))

    def delete_variant(self, variant_id):
        self.execute("DELETE FROM comment_variants WHERE id = ?", (variant_id,))

    def mark_variant_used(self, variant_id):
        self.execute("UPDATE comment_variants SET used_count = used_count + 1, last_used_at = ? WHERE id = ?",
                     (now_str(), variant_id))

    def recent_variants_in_group(self, group_url, days=3):
        """Mẫu bình luận đã dùng trong nhóm này ... ngày gần đây (để tránh lặp lại trong cùng nhóm)"""
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        return {r["variant_id"] for r in self.query(
            "SELECT DISTINCT c.variant_id FROM comments c JOIN posts p ON p.id = c.post_id "
            "WHERE p.group_url = ? AND c.sent_at >= ? AND c.variant_id IS NOT NULL", (group_url, since))}

    # ---- danh sách nhóm (file Excel) ----
    def group_lists(self, enabled_only=False):
        sql = "SELECT * FROM group_lists" + (" WHERE enabled = 1" if enabled_only else "")
        return self.query(sql + " ORDER BY CASE kind WHEN 'main' THEN 0 WHEN 'found' THEN 1 ELSE 2 END, created_at")

    def get_group_list(self, key):
        rows = self.query("SELECT * FROM group_lists WHERE key = ?", (key,))
        return rows[0] if rows else None

    def add_group_list(self, key, name, path, kind, enabled=1, region_filter=0):
        self.execute("INSERT OR IGNORE INTO group_lists (key, name, path, kind, enabled, region_filter, created_at) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?)", (key, name, path, kind, enabled, region_filter, now_str()))

    def update_group_list(self, key, **fields):
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.execute(f"UPDATE group_lists SET {cols} WHERE key = ?", (*fields.values(), key))

    def delete_group_list(self, key):
        self.execute("DELETE FROM group_lists WHERE key = ?", (key,))

    # ---- tiến trình (web hiển thị) ----
    def progress(self):
        try:
            return json.loads(self.get_setting("progress") or "{}")
        except ValueError:
            return {}

    def set_progress(self, reset=False, **fields):
        """Cập nhật tiến trình đang chạy. reset=True: bắt đầu mới (giữ pid, started)"""
        old = self.progress()
        p = {k: old[k] for k in ("pid", "started") if k in old} if reset else old
        p.update(fields)
        p["updated_at"] = now_str()
        self.set_setting("progress", json.dumps(p, ensure_ascii=False))

    # ---- tên nhóm / nhóm đã xóa ----
    def group_names(self):
        return {r["group_url"]: r["group_name"] for r in self.query("SELECT * FROM group_names")}

    def set_group_name(self, group_url, name):
        self.execute("INSERT INTO group_names (group_url, group_name) VALUES (?, ?) "
                     "ON CONFLICT(group_url) DO UPDATE SET group_name = excluded.group_name", (group_url, name))

    def removed_urls(self):
        return {r["group_url"] for r in self.query("SELECT group_url FROM removed_groups")}

    def mark_removed(self, group_url):
        self.execute("INSERT OR IGNORE INTO removed_groups (group_url, removed_at) VALUES (?, ?)", (group_url, now_str()))

    def priority_urls(self):
        return {r["group_url"] for r in self.query("SELECT group_url FROM priority_groups")}

    def set_priority(self, group_url, group_name, on):
        if on:
            self.execute("INSERT OR IGNORE INTO priority_groups (group_url, group_name, since) VALUES (?, ?, ?)",
                         (group_url, group_name, now_str()))
        else:
            self.execute("DELETE FROM priority_groups WHERE group_url = ?", (group_url,))

    def comments_of(self, post_id):
        return self.query("SELECT * FROM comments WHERE post_id = ? ORDER BY id", (post_id,))

    def update_comment(self, comment_id, **fields):
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.execute(f"UPDATE comments SET {cols} WHERE id = ?", (*fields.values(), comment_id))

    def mark_safe_all(self, reason):
        self.set_setting("safe_all", "1")
        self.set_setting("safe_all_reason", f"{now_str()} — {reason}")

    def reset_safe(self, group_url=None):
        """Quay lại bản đầy đủ cho 1 nhóm, hoặc cho tất cả (group_url=None)"""
        if group_url:
            self.execute("DELETE FROM safe_groups WHERE group_url = ?", (group_url,))
        else:
            self.execute("DELETE FROM safe_groups")
            self.set_setting("safe_all", "0")
            self.set_setting("safe_all_reason", "")

    def commented_posts_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return self.query(
            "SELECT COUNT(*) AS n FROM posts WHERE found_at LIKE ? AND status IN ('Hoàn tất', 'Một phần')",
            (today + "%",))[0]["n"]

    def posts_to_verify(self, min_age_minutes, limit):
        """Bài đã bình luận được ít nhất ... phút (tối đa 24 giờ) và chưa kiểm tra lại"""
        older = (datetime.now() - timedelta(minutes=min_age_minutes)).strftime("%Y-%m-%d %H:%M:%S")
        newer = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        return self.query(
            "SELECT p.*, (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.status = ?) AS sent "
            "FROM posts p WHERE verified_at IS NULL AND status IN ('Hoàn tất', 'Một phần') "
            "AND found_at <= ? AND found_at >= ? ORDER BY found_at LIMIT ?",
            (SENT, older, newer, limit))

    # ---- runs ----
    def start_run(self):
        return self.execute("INSERT INTO runs (started_at) VALUES (?)", (now_str(),))

    def finish_run(self, run_id, groups_scanned, new_posts, commented_posts, note=""):
        self.execute(
            "UPDATE runs SET finished_at = ?, groups_scanned = ?, new_posts = ?, commented_posts = ?, note = ? "
            "WHERE id = ?", (now_str(), groups_scanned, new_posts, commented_posts, note, run_id))

    # ---- settings ----
    def get_setting(self, key, default=None):
        rows = self.query("SELECT value FROM settings WHERE key = ?", (key,))
        return rows[0]["value"] if rows else default

    def set_setting(self, key, value):
        self.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))

    def is_paused(self):
        return self.get_setting("paused", "0") == "1"

    # ---- xuất Excel ----
    def comments_table(self):
        return pd.DataFrame(self.query(
            "SELECT c.sent_at AS 'Thời gian', p.group_name AS 'Nhóm', p.post_url AS 'Link bài viết', "
            "c.idx AS 'Bình luận số', c.image AS 'Ảnh', c.variant AS 'Bản nội dung', c.text AS 'Nội dung bình luận', "
            "c.status AS 'Trạng thái', c.detail AS 'Ghi chú', p.verify_result AS 'Kiểm tra lại' "
            "FROM comments c JOIN posts p ON p.id = c.post_id ORDER BY c.sent_at DESC"))

    def export_excel(self, path):
        """Ghi lại toàn bộ nhật ký ra Excel. Trả về False nếu file đang mở trong Excel."""
        try:
            self.comments_table().to_excel(path, index=False)
            return True
        except PermissionError:
            return False
