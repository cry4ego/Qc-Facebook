"""
Xem kết quả THỬ NGHIỆM "bình luận cả bài không ghi khu vực ở nhóm toàn quốc" (bật 25/10/2026, REGION_REQUIRED_IN_NATIONAL_GROUPS = False).
Chỉ ĐỌC CSDL. Chạy:  .\\.venv\\Scripts\\python.exe tools\\thu_nghiem_khu_vuc.py [--tu YYYY-MM-DD] [--den YYYY-MM-DD]

So sánh bài thuộc diện thử nghiệm (lý do quyết định có "(thử nghiệm)") với các bài bình luận bình thường cùng kỳ: số bài thêm mỗi ngày,
tỷ lệ bình luận bị từ chối, tỷ lệ bài mất bình luận khi kiểm tra lại, nhóm nào cho nhiều bài thử nghiệm nhất, và khách bạn đã ghi (nếu
có ghi theo nguồn nhóm). Số liệu chỉ để bạn quyết định giữ / tắt thử nghiệm; khách thật vẫn phải do bạn ghi ở tab Công ty AI.
"""
import argparse
import os
import sqlite3
import sys
from datetime import date, datetime

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GOC)
from config import Config  # noqa: E402
from modules.filters import LY_DO_THU_NGHIEM_KHU_VUC  # noqa: E402

NGAY_BAT_DAU = "2026-10-25"


def ket_noi(duong_dan: str) -> sqlite3.Connection:
    """Mở CSDL CHỈ ĐỌC (không bao giờ ghi vào dữ liệu thật)"""
    uri = "file:" + os.path.abspath(duong_dan).replace("\\", "/") + "?mode=ro"
    c = sqlite3.connect(uri, uri=True)
    c.row_factory = sqlite3.Row
    return c


def _tu_choi(c: sqlite3.Connection, dieu_kien_bai: str, tham_so: tuple) -> tuple[int, int, int, int]:
    """(số bình luận, số bị từ chối, số bài, số bài mất bình luận khi kiểm tra lại) của các bài thỏa điều kiện"""
    r = c.execute(
        f"SELECT COUNT(c.id) AS bl, COALESCE(SUM(c.status LIKE 'Bị từ chối%'), 0) AS tc, COUNT(DISTINCT p.id) AS bai, "
        f"COUNT(DISTINCT CASE WHEN p.verify_result LIKE 'Không thấy%' OR p.verify_result LIKE 'Chỉ còn%' THEN p.id END) AS mat "
        f"FROM posts p LEFT JOIN comments c ON c.post_id = p.id WHERE p.status IN ('Hoàn tất', 'Một phần') AND {dieu_kien_bai}",
        tham_so).fetchone()
    return r["bl"], r["tc"], r["bai"], r["mat"]


def bao_cao(c: sqlite3.Connection, tu: str, den: str) -> str:
    """Bản chữ kết quả thử nghiệm từ ngày `tu` tới hết ngày `den`"""
    dong = [f"THỬ NGHIỆM bình luận bài không ghi khu vực ở nhóm toàn quốc — từ {tu} tới {den}", ""]
    the = f"%{LY_DO_THU_NGHIEM_KHU_VUC}%"
    cua_thu_nghiem = ("p.post_url IN (SELECT d.post_url FROM post_decisions d WHERE d.reason LIKE ? AND d.decision = 'Bình luận') "
                      "AND substr(p.found_at, 1, 10) BETWEEN ? AND ?")
    binh_thuong = ("p.post_url NOT IN (SELECT d.post_url FROM post_decisions d WHERE d.reason LIKE ? AND d.decision = 'Bình luận' "
                   "AND d.post_url IS NOT NULL) AND substr(p.found_at, 1, 10) BETWEEN ? AND ?")
    theo_ngay = c.execute(
        "SELECT substr(p.found_at, 1, 10) AS ngay, COUNT(DISTINCT p.id) AS tong, COUNT(DISTINCT CASE WHEN p.post_url IN "
        "(SELECT d.post_url FROM post_decisions d WHERE d.reason LIKE ? AND d.decision = 'Bình luận') THEN p.id END) AS thu_nghiem "
        "FROM posts p WHERE p.status IN ('Hoàn tất', 'Một phần') AND substr(p.found_at, 1, 10) BETWEEN ? AND ? "
        "GROUP BY 1 ORDER BY 1", (the, tu, den)).fetchall()
    dong.append("Số bài đã bình luận mỗi ngày (trong đó bài thuộc diện thử nghiệm):")
    dong += [f"  {r['ngay']}: {r['tong']} bài, thử nghiệm {r['thu_nghiem']}" for r in theo_ngay] or ["  (chưa có bài nào)"]

    tn, bt = _tu_choi(c, cua_thu_nghiem, (the, tu, den)), _tu_choi(c, binh_thuong, (the, tu, den))
    dong += ["", "So sánh chất lượng (bài thử nghiệm so với bài bình thường cùng kỳ):"]
    for ten, (bl, tc, bai, mat) in (("thử nghiệm", tn), ("bình thường", bt)):
        dong.append(f"  {ten}: {bai} bài, {bl} bình luận, bị từ chối {tc} ({_phan_tram(tc, bl)}), "
                    f"bài mất bình luận khi kiểm tra lại {mat} ({_phan_tram(mat, bai)})")

    nhom = c.execute(
        "SELECT p.group_name AS nhom, COUNT(DISTINCT p.id) AS so_bai FROM posts p WHERE p.status IN ('Hoàn tất', 'Một phần') "
        f"AND {cua_thu_nghiem} GROUP BY p.group_url ORDER BY 2 DESC LIMIT 8", (the, tu, den)).fetchall()
    dong += ["", "Nhóm cho nhiều bài thử nghiệm nhất:"] + [f"  {r['nhom']}: {r['so_bai']} bài" for r in nhom]

    chua_xet = c.execute("SELECT COUNT(*) AS n FROM post_decisions WHERE reason LIKE 'không ghi khu vực (nhóm toàn quốc —%' "
                         "AND substr(first_seen, 1, 10) BETWEEN ? AND ?", (tu, den)).fetchone()["n"]
    if chua_xet:
        dong += ["", f"(Còn {chua_xet} bài bị bỏ vì không ghi khu vực: bot chưa khởi động lại bằng cấu hình thử nghiệm, hoặc đã tắt thử nghiệm.)"]

    dong += ["", _khach(c, tu, den), "", _ket_luan(tn, bt, len(theo_ngay))]
    return "\n".join(dong)


def _phan_tram(a: int, b: int) -> str:
    return f"{round(100 * a / b)}%" if b else "—"


def _khach(c: sqlite3.Connection, tu: str, den: str) -> str:
    try:
        r = c.execute("SELECT loai, SUM(so_luong) AS n FROM khach WHERE ngay BETWEEN ? AND ? GROUP BY loai", (tu, den)).fetchall()
    except sqlite3.Error:
        return "Khách: chưa có bảng ghi khách (tab Công ty AI → Ghi kết quả khách)."
    if not r:
        return "Khách bạn đã ghi trong kỳ này: chưa có dòng nào — ghi khách mỗi tối ở tab Công ty AI để đánh giá thử nghiệm bằng khách thật."
    return "Khách bạn đã ghi trong kỳ này: " + ", ".join(f"{x['loai']} {x['n']}" for x in r)


def _ket_luan(tn, bt, so_ngay: int) -> str:
    """Gợi ý (không phải quyết định): thử nghiệm có thêm bài mà không làm tăng bình luận bị từ chối / mất không"""
    bl_tn, tc_tn, bai_tn, mat_tn = tn
    bl_bt, tc_bt, bai_bt, mat_bt = bt
    if not bai_tn:
        return "Gợi ý: chưa có bài thử nghiệm nào được bình luận — kiểm tra bot đã khởi động lại chưa."
    them = bai_tn / max(so_ngay, 1)
    xau_hon = (bl_tn >= 10 and bl_bt and tc_tn / bl_tn > 1.5 * max(tc_bt / bl_bt, 0.02)) \
        or (bai_tn >= 10 and bai_bt and mat_tn / bai_tn > 1.5 * max(mat_bt / bai_bt, 0.05))
    if xau_hon:
        return (f"Gợi ý: thêm khoảng {them:.1f} bài mỗi ngày NHƯNG bị từ chối / mất bình luận nhiều hơn hẳn bài bình thường — "
                "cân nhắc đặt REGION_REQUIRED_IN_NATIONAL_GROUPS = True để tắt thử nghiệm.")
    return (f"Gợi ý: thêm khoảng {them:.1f} bài mỗi ngày và tỷ lệ bị từ chối / mất bình luận không tệ hơn bài bình thường — "
            "có thể giữ; nhìn thêm khách thật bạn ghi được từ nhóm toàn quốc trước khi quyết định.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Xem kết quả thử nghiệm bài không ghi khu vực ở nhóm toàn quốc (chỉ đọc)")
    ap.add_argument("--tu", default=NGAY_BAT_DAU)
    ap.add_argument("--den", default=date.today().strftime("%Y-%m-%d"))
    ap.add_argument("--db", default=Config.DB_FILE)
    a = ap.parse_args()
    for ngay in (a.tu, a.den):
        datetime.strptime(ngay, "%Y-%m-%d")      # ngày sai thì báo lỗi rõ ràng ngay
    sys.stdout.reconfigure(encoding="utf-8")
    print(bao_cao(ket_noi(a.db), a.tu, a.den))


if __name__ == "__main__":
    main()
