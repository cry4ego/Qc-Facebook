"""Dữ liệu mẫu dùng chung cho test công ty AI: bơm số liệu giả vào CSDL tạm của bot (quét, quyết định, bình luận)."""
import itertools
from datetime import date, timedelta
from types import SimpleNamespace

from cong_ty import so_lieu

HOM_NAY = date(2026, 10, 24)
CFG = SimpleNamespace(MAX_COMMENTED_POSTS_PER_DAY=40)
NHOM = "https://www.facebook.com/groups/{}/"
_dem = itertools.count()


def ngay(truoc):
    return (HOM_NAY - timedelta(days=truoc)).strftime("%Y-%m-%d")


def chen(db, sql, rows):
    with db._conn() as c:
        c.executemany(sql, rows)


def them_quet(db, day, so_quet, so_nhom):
    chen(db, "INSERT INTO group_scans (group_url, scanned_at, found) VALUES (?, ?, 0)",
         [(NHOM.format(i % so_nhom), f"{day} 09:00:00") for i in range(so_quet)])


def them_bai_thay(db, day, tong, mua, dat_loc, nhom=0, ly_do="không ghi khu vực"):
    assert dat_loc <= mua <= tong
    rows = []
    for i in range(tong):
        intent = "MUA" if i < mua else "KHÔNG XÁC ĐỊNH"
        quyet_dinh, ly = ("Bình luận", "") if i < dat_loc else ("Bỏ qua", ly_do)
        rows.append((NHOM.format(nhom), f"Nhóm {nhom}", f"k{next(_dem)}", "Cần mua màn", intent, quyet_dinh, ly,
                     f"{day} 10:00:00", f"{day} 10:00:00"))
    chen(db, "INSERT INTO post_decisions (group_url, group_name, text_key, post_text, intent, decision, reason, "
             "first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


def them_binh_luan(db, day, so_bai, so_binh_luan, nhom=0, trang_thai="Hoàn tất", variant_id=None, verify=None,
                   tt_binh_luan="Đã đăng"):
    chen(db, "INSERT INTO posts (post_url, group_name, group_url, post_text, post_age_min, found_at, status, "
             "verify_result) VALUES (?, ?, ?, ?, 5, ?, ?, ?)",
         [(f"https://fb/p/{next(_dem)}", f"Nhóm {nhom}", NHOM.format(nhom), "Cần mua màn", f"{day} 12:00:00",
           trang_thai, verify) for _ in range(so_bai)])
    ids = [r["id"] for r in db.query("SELECT id FROM posts ORDER BY id DESC LIMIT ?", (so_bai,))]
    chen(db, "INSERT INTO comments (post_id, idx, text, image, sent_at, status, variant_id) "
             "VALUES (?, ?, 'nội dung', '', ?, ?, ?)",
         [(ids[i % len(ids)], i, f"{day} 12:05:00", tt_binh_luan, variant_id) for i in range(so_binh_luan)])


def ngay_binh_thuong(db, truoc):
    day = ngay(truoc)
    them_quet(db, day, 900, 57)
    them_bai_thay(db, day, 1500, 60, 35)
    them_binh_luan(db, day, 33, 66)


def ngay_it_bai(db, truoc):
    """Bot quét như cũ nhưng người cần mua đăng ít hơn"""
    day = ngay(truoc)
    them_quet(db, day, 900, 57)
    them_bai_thay(db, day, 700, 25, 16)
    them_binh_luan(db, day, 15, 70)


def chuoi_giam(db):
    """7 ngày bình thường rồi 3 ngày ít bài (bài MUA 60 -> 25 mỗi ngày); hôm nay mới nửa ngày"""
    for truoc in range(10, 3, -1):
        ngay_binh_thuong(db, truoc)
    for truoc in (3, 2, 1):
        ngay_it_bai(db, truoc)
    them_quet(db, ngay(0), 100, 20)
    return so_lieu.chuoi_ngay(db, 14, HOM_NAY)
