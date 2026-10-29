"""Công cụ xem kết quả thử nghiệm bài không ghi khu vực ở nhóm toàn quốc: đếm đúng bài thử nghiệm, so với bài bình thường, chỉ ĐỌC CSDL."""
import importlib.util
import itertools
import os

import pytest

from modules.db import Database, SENT
from modules.filters import LY_DO_THU_NGHIEM_KHU_VUC

DUONG_DAN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "thu_nghiem_khu_vuc.py")
_spec = importlib.util.spec_from_file_location("thu_nghiem_khu_vuc", DUONG_DAN)
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

NHOM = "https://www.facebook.com/groups/toanquoc/"
_dem = itertools.count(1)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def bai(db, ngay, thu_nghiem, trang_thai_binh_luan=SENT, so_binh_luan=3, verify=None):
    """1 bài đã bình luận ngày `ngay`; thu_nghiem=True: quyết định ghi lý do thử nghiệm"""
    url = f"{NHOM}posts/{next(_dem)}"
    post_id = db.add_post(url, "MÀN HÌNH MÁY TÍNH", NHOM, "Cần tìm màn", 5)
    db.execute("UPDATE posts SET found_at = ?, status = 'Hoàn tất', verify_result = ? WHERE id = ?", (f"{ngay} 10:00:00", verify, post_id))
    for i in range(so_binh_luan):
        db.add_comment(post_id, i + 1, "Bình luận", "", trang_thai_binh_luan)
    ly_do = ("chủ đề Màn hình · MUA · " + LY_DO_THU_NGHIEM_KHU_VUC) if thu_nghiem else "chủ đề Màn hình · MUA · khu vực hà nội"
    db.execute("INSERT INTO post_decisions (group_url, group_name, text_key, post_text, post_url, decision, reason, first_seen, last_seen) "
               "VALUES (?, 'MÀN HÌNH MÁY TÍNH', ?, 'Cần tìm màn', ?, 'Bình luận', ?, ?, ?)",
               (NHOM, f"k{next(_dem)}", url, ly_do, f"{ngay} 09:59:00", f"{ngay} 09:59:00"))


def bao_cao(db, tu="2026-10-25", den="2026-10-28"):
    return tool.bao_cao(tool.ket_noi(db.path), tu, den)


def test_it_counts_trial_posts_per_day_and_in_total(db):
    for _ in range(3):
        bai(db, "2026-10-25", thu_nghiem=True)
    bai(db, "2026-10-25", thu_nghiem=False)
    for _ in range(2):
        bai(db, "2026-10-26", thu_nghiem=True)
    chu = bao_cao(db)
    assert "2026-10-25: 4 bài, thử nghiệm 3" in chu and "2026-10-26: 2 bài, thử nghiệm 2" in chu
    assert "thử nghiệm: 5 bài, 15 bình luận" in chu and "bình thường: 1 bài, 3 bình luận" in chu


def test_only_the_asked_period_is_counted(db):
    bai(db, "2026-10-24", thu_nghiem=True)                         # trước khi thử nghiệm
    bai(db, "2026-10-29", thu_nghiem=True)                         # sau kỳ xem
    assert "(chưa có bài nào)" in bao_cao(db)


def test_it_compares_rejection_and_lost_comments_with_normal_posts(db):
    bai(db, "2026-10-25", thu_nghiem=True, trang_thai_binh_luan="Bị từ chối · đã xóa", verify="Không thấy 0/3 — có thể đã bị xóa")
    bai(db, "2026-10-25", thu_nghiem=False)
    chu = bao_cao(db)
    assert "thử nghiệm: 1 bài, 3 bình luận, bị từ chối 3 (100%), bài mất bình luận khi kiểm tra lại 1 (100%)" in chu
    assert "bình thường: 1 bài, 3 bình luận, bị từ chối 0 (0%)" in chu


def test_the_hint_says_when_the_trial_looks_worse_and_when_it_looks_fine(db):
    for _ in range(12):
        bai(db, "2026-10-25", thu_nghiem=True, trang_thai_binh_luan="Bị từ chối · đã xóa", so_binh_luan=1)
        bai(db, "2026-10-25", thu_nghiem=False)
    assert "NHƯNG bị từ chối" in bao_cao(db)
    sach = Database(os.path.join(os.path.dirname(db.path), "sach.db"))
    for _ in range(12):
        bai(sach, "2026-10-25", thu_nghiem=True)
        bai(sach, "2026-10-25", thu_nghiem=False)
    assert "có thể giữ" in bao_cao(sach)


def test_without_any_trial_post_it_tells_to_check_the_bot_was_restarted(db):
    bai(db, "2026-10-25", thu_nghiem=False)
    assert "chưa có bài thử nghiệm nào" in bao_cao(db)


def test_posts_skipped_for_region_are_reported_so_a_stale_bot_is_noticed(db):
    db.execute("INSERT INTO post_decisions (group_url, group_name, text_key, post_text, decision, reason, first_seen, last_seen) "
               "VALUES (?, 'X', 'k1', 'Cần tìm màn', 'Bỏ qua', 'không ghi khu vực (nhóm toàn quốc — chỉ bình luận bài ghi Hà Nội)', "
               "'2026-10-26 09:00:00', '2026-10-26 09:00:00')", (NHOM,))
    assert "Còn 1 bài bị bỏ vì không ghi khu vực" in bao_cao(db)


def test_the_database_is_opened_read_only(db):
    c = tool.ket_noi(db.path)
    with pytest.raises(Exception):
        c.execute("INSERT INTO settings (key, value) VALUES ('x', 'y')")
