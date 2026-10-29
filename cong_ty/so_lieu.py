"""
Số liệu cho báo cáo sáng: chỉ ĐỌC CSDL của bot (posts, comments, post_decisions, group_scans…), không ghi gì.

Mỗi hàm nhận `hom_nay` (date) = ngày của báo cáo: số liệu chỉ tính từ đầu kỳ tới HẾT ngày đó (báo cáo ngày đã qua không
lẫn dữ liệu của các ngày sau). `bay_gio` là thời điểm thật khi xem (mặc định = cuối ngày `hom_nay`, tức coi báo cáo là của
ngày hôm nay): ngày `hom_nay` chỉ "chưa hết" nếu bay_gio còn trong ngày đó.
"""
import re
from collections import Counter
from datetime import date, datetime, time, timedelta

from cong_ty import khach
from modules.db import BLOCKED, COMMENT, ERROR, REJECTED, SENT, SKIP, STOP_GIO_MAC_DINH, Database
from modules.intent import BUY

DA_BINH_LUAN = ("Hoàn tất", "Một phần")      # trạng thái bài đã bình luận
_DAU_CHAM = ", ".join("?" * len(DA_BINH_LUAN))
KHONG_GHI_LY_DO = "(không ghi lý do)"
DINH_DANG_GIO = "%Y-%m-%d %H:%M:%S"


def _ngay(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _tu_ngay(hom_nay: date, so_ngay: int) -> date:
    return hom_nay - timedelta(days=so_ngay - 1)


def _den_ngay(hom_nay: date) -> str:
    """Giới hạn trên (không gồm) của kỳ báo cáo: đầu ngày hôm sau"""
    return _ngay(hom_nay + timedelta(days=1))


def _bay_gio(hom_nay: date, bay_gio: datetime | None) -> datetime:
    return bay_gio or datetime.combine(hom_nay, time(23, 59, 59))


def _theo_ngay(db: Database, sql: str, params: tuple) -> dict[str, dict]:
    """Chạy truy vấn có cột `d` (YYYY-MM-DD) và trả về {ngày: dòng}"""
    return {r["d"]: r for r in db.query(sql, params)}


def chuoi_ngay(db: Database, so_ngay: int, hom_nay: date, bay_gio: datetime | None = None) -> list[dict]:
    """Số liệu từng ngày (cũ -> mới) trong `so_ngay` ngày tới hết `hom_nay`; `chua_het` = ngày đó chưa qua tại `bay_gio`.
    quet / nhom_quet: lần quét bảng tin · bai_thay: bài bot xem · bai_mua: bài ý định MUA · dat_loc: bài đạt mọi bộ lọc
    · bai_binh_luan / binh_luan_gui: bài đã bình luận / bình luận đã đăng · goi, nhan, mua, so_tien: sổ ghi khách"""
    dau, den = _tu_ngay(hom_nay, so_ngay), _den_ngay(hom_nay)
    tu, hien_nay = _ngay(dau), _bay_gio(hom_nay, bay_gio).date()
    quet = _theo_ngay(db, "SELECT substr(scanned_at, 1, 10) AS d, COUNT(*) AS quet, COUNT(DISTINCT group_url) AS nhom "
                          "FROM group_scans WHERE scanned_at >= ? AND scanned_at < ? GROUP BY d", (tu, den))
    quyet_dinh = _theo_ngay(db, "SELECT substr(first_seen, 1, 10) AS d, COUNT(*) AS bai_thay, "
                                "SUM(intent = ?) AS bai_mua, SUM(decision = ?) AS dat_loc FROM post_decisions "
                                "WHERE first_seen >= ? AND first_seen < ? GROUP BY d", (BUY, COMMENT, tu, den))
    bai = _theo_ngay(db, "SELECT substr(found_at, 1, 10) AS d, COUNT(*) AS bai FROM posts WHERE found_at >= ? "
                         f"AND found_at < ? AND status IN ({_DAU_CHAM}) GROUP BY d", (tu, den, *DA_BINH_LUAN))
    gui = _theo_ngay(db, "SELECT substr(sent_at, 1, 10) AS d, COUNT(*) AS gui FROM comments "
                         "WHERE sent_at >= ? AND sent_at < ? AND status = ? GROUP BY d", (tu, den, SENT))
    khach_ngay = khach.tong_theo_ngay(db, tu, den)
    chuoi = []
    for i in range(so_ngay):
        d = dau + timedelta(days=i)
        k = _ngay(d)
        qd, kh = quyet_dinh.get(k, {}), khach_ngay.get(k, {})
        chuoi.append({
            "ngay": k, "chua_het": d >= hien_nay,
            "quet": quet.get(k, {}).get("quet", 0), "nhom_quet": quet.get(k, {}).get("nhom", 0),
            "bai_thay": qd.get("bai_thay", 0), "bai_mua": qd.get("bai_mua") or 0, "dat_loc": qd.get("dat_loc") or 0,
            "bai_binh_luan": bai.get(k, {}).get("bai", 0), "binh_luan_gui": gui.get(k, {}).get("gui", 0),
            "goi": kh.get("Gọi", 0), "nhan": kh.get("Nhắn", 0), "mua": kh.get("Mua", 0), "so_tien": kh.get("so_tien", 0)})
    return chuoi


def _ten_nhom_du_phong(db: Database) -> dict[str, str]:
    """Tên nhóm khi bài chưa có tên: bảng group_names rồi group_stats (cái sau đè)"""
    ten = {r["group_url"]: r["group_name"] for r in db.query("SELECT group_url, group_name FROM group_names")}
    ten.update({r["group_url"]: r["group_name"] for r in db.query(
        "SELECT group_url, group_name FROM group_stats WHERE group_name IS NOT NULL AND group_name != ''")})
    return ten


def _nhom_nhan_khach(hang: list[dict]) -> dict[str, str]:
    """{tên nhóm: link nhóm được ghi nhận khách}. Hai nhóm trùng tên: số khách ghi theo tên chỉ tính cho nhóm có nhiều
    bài đạt lọc nhất (không tính đôi)"""
    tot_nhat: dict[str, dict] = {}
    for r in hang:
        cu = tot_nhat.get(r["ten"])
        if cu is None or (r["dat_loc"], r["quet"]) > (cu["dat_loc"], cu["quet"]):
            tot_nhat[r["ten"]] = r
    return {ten: r["group_url"] for ten, r in tot_nhat.items()}


def xep_hang_nhom(db: Database, so_ngay: int, hom_nay: date) -> list[dict]:
    """Từng nhóm trong `so_ngay` ngày: số lần quét, bài MUA, bài đạt lọc, bài đã bình luận, khách (khớp sổ ghi khách theo
    tên nhóm). Xếp: nhiều khách nhất -> nhiều bài đạt lọc -> nhiều bài MUA"""
    tu, den = _ngay(_tu_ngay(hom_nay, so_ngay)), _den_ngay(hom_nay)
    quet = {r["group_url"]: r["n"] for r in db.query(
        "SELECT group_url, COUNT(*) AS n FROM group_scans WHERE scanned_at >= ? AND scanned_at < ? GROUP BY group_url",
        (tu, den))}
    quyet_dinh = {r["group_url"]: r for r in db.query(
        "SELECT group_url, MAX(group_name) AS ten, SUM(intent = ?) AS mua, SUM(decision = ?) AS dat_loc "
        "FROM post_decisions WHERE first_seen >= ? AND first_seen < ? GROUP BY group_url", (BUY, COMMENT, tu, den))}
    bai = {r["group_url"]: r["n"] for r in db.query(
        "SELECT group_url, COUNT(*) AS n FROM posts WHERE found_at >= ? AND found_at < ? "
        f"AND status IN ({_DAU_CHAM}) GROUP BY group_url", (tu, den, *DA_BINH_LUAN))}
    ten_du_phong, theo_nguon = _ten_nhom_du_phong(db), khach.tong_theo_nguon(db, tu, den)
    hang = []
    for url in sorted({*quet, *quyet_dinh, *bai}):
        qd = quyet_dinh.get(url, {})
        hang.append({"group_url": url, "ten": qd.get("ten") or ten_du_phong.get(url) or url, "quet": quet.get(url, 0),
                     "mua": qd.get("mua") or 0, "dat_loc": qd.get("dat_loc") or 0, "bai_binh_luan": bai.get(url, 0),
                     "khach": 0})
    nhan_khach = _nhom_nhan_khach(hang)
    hang = [{**r, "khach": sum(theo_nguon.get(r["ten"], {}).get(loai, 0) for loai in khach.LOAI)
             if nhan_khach[r["ten"]] == r["group_url"] else 0} for r in hang]
    return sorted(hang, key=lambda r: (-r["khach"], -r["dat_loc"], -r["mua"], -r["quet"], r["ten"]))


def _gom_ly_do(ly_do: str) -> str:
    """'khách ở xa (HCM) — chỉ bình luận…' -> 'khách ở xa' để gom các nơi khác nhau về một lý do"""
    return re.split(r" \(| — ", ly_do or "", maxsplit=1)[0].strip() or KHONG_GHI_LY_DO


def ly_do_bo_qua_bai_mua(db: Database, so_ngay: int, hom_nay: date, top: int = 5) -> list[dict]:
    """Bài người cần MUA nhưng bị bỏ qua: lý do nào nhiều nhất (gom theo lý do chính)"""
    tu, den = _ngay(_tu_ngay(hom_nay, so_ngay)), _den_ngay(hom_nay)
    dem = Counter()
    for r in db.query("SELECT reason, COUNT(*) AS n FROM post_decisions WHERE first_seen >= ? AND first_seen < ? "
                      "AND intent = ? AND decision = ? GROUP BY reason", (tu, den, BUY, SKIP)):
        dem[_gom_ly_do(r["reason"])] += r["n"]
    xep = sorted(dem.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
    return [{"ly_do": ly_do, "so_bai": n} for ly_do, n in xep]


def mau_binh_luan(db: Database, so_ngay: int, hom_nay: date) -> list[dict]:
    """Từng mẫu bình luận trong `so_ngay` ngày: đã đăng, bị chặn / từ chối, lỗi, số bài sau kiểm tra lại không còn bình luận"""
    tu, den = _ngay(_tu_ngay(hom_nay, so_ngay)), _den_ngay(hom_nay)
    rows = db.query(
        "SELECT v.id, v.active, p.name AS san_pham, "
        "SUM(c.status = ?) AS da_gui, SUM(c.status = ? OR c.status LIKE ?) AS bi_tu_choi, SUM(c.status = ?) AS loi, "
        "COUNT(DISTINCT CASE WHEN po.verify_result LIKE 'Không thấy%' OR po.verify_result LIKE 'Chỉ còn%' "
        "THEN po.id END) AS bai_mat "
        "FROM comment_variants v LEFT JOIN products p ON p.id = v.product_id "
        "LEFT JOIN comments c ON c.variant_id = v.id AND c.sent_at >= ? AND c.sent_at < ? "
        "LEFT JOIN posts po ON po.id = c.post_id GROUP BY v.id", (SENT, BLOCKED, REJECTED + "%", ERROR, tu, den))
    mau = [{"id": r["id"], "bat": bool(r["active"]), "san_pham": r["san_pham"] or "?", "da_gui": r["da_gui"] or 0,
            "bi_tu_choi": r["bi_tu_choi"] or 0, "loi": r["loi"] or 0, "bai_mat": r["bai_mat"]} for r in rows]
    return sorted(mau, key=lambda m: (-m["da_gui"], m["id"]))


def _safe_all_hieu_luc(ly_do: str, hom_nay: date, dang_bat: bool) -> bool:
    """Bản không SĐT đang bật cho mọi nhóm — nhưng báo cáo của ngày TRƯỚC khi bật (ngày ghi ở đầu lý do) thì không tính"""
    if not dang_bat:
        return False
    try:
        tu_khi = datetime.strptime(ly_do[:10], "%Y-%m-%d").date()
    except ValueError:
        return True
    return tu_khi <= hom_nay


def _con_chan(chan_den: str | None, hom_nay: date, bay_gio: datetime) -> str | None:
    """Thời điểm hết chặn nếu bây giờ CÒN bị chặn; báo cáo của ngày đã qua không nói về trạng thái hiện tại"""
    if hom_nay < bay_gio.date():
        return None
    try:
        het = datetime.strptime(chan_den or "", DINH_DANG_GIO)
    except ValueError:
        return None
    return chan_den if het > bay_gio else None


def rui_ro(db: Database, tran: int, hom_nay: date, so_ngay: int, bay_gio: datetime | None = None) -> dict:
    """Tín hiệu rủi ro tài khoản: đang dùng bản không SĐT cho mọi nhóm, bình luận bị chặn / từ chối, đang bị chặn,
    số bài hôm nay so với trần"""
    tu, den = _ngay(_tu_ngay(hom_nay, so_ngay)), _den_ngay(hom_nay)
    bay_gio = _bay_gio(hom_nay, bay_gio)

    def dem_binh_luan(dieu_kien: str, *params) -> int:
        # dieu_kien là chuỗi cố định do code này viết (không bao giờ lấy từ người dùng); giá trị đi qua `params`
        return db.query(f"SELECT COUNT(*) AS n FROM comments WHERE sent_at >= ? AND sent_at < ? AND {dieu_kien}",
                        (tu, den, *params))[0]["n"]

    ly_do = db.get_setting("safe_all_reason", "") or ""
    # nhóm ĐANG tạm ngừng (chưa hết hạn) — nhóm ngừng đã hết hạn thì bot đã bình luận lại
    nhom_ngung = db.query(f"SELECT COUNT(*) AS n FROM safe_groups WHERE stop = 1 AND COALESCE(stop_until, "
                          f"datetime(since, '+{STOP_GIO_MAC_DINH} hours')) > ?", (bay_gio.strftime("%Y-%m-%d %H:%M:%S"),))[0]["n"]
    return {
        "safe_all": _safe_all_hieu_luc(ly_do, hom_nay, db.get_setting("safe_all", "0") == "1"),
        "safe_all_ly_do": ly_do,
        "nhom_an_toan": db.query("SELECT COUNT(*) AS n FROM safe_groups")[0]["n"] - nhom_ngung,
        "nhom_ngung": nhom_ngung,
        "bi_chan": dem_binh_luan("status = ?", BLOCKED),
        "bi_tu_choi": dem_binh_luan("status LIKE ?", REJECTED + "%"),
        "bai_hom_nay": db.query(f"SELECT COUNT(*) AS n FROM posts WHERE found_at LIKE ? AND status IN ({_DAU_CHAM})",
                                (_ngay(hom_nay) + "%", *DA_BINH_LUAN))[0]["n"],
        "tran": tran,
        "chan_den": _con_chan(db.get_setting("blocked_until"), hom_nay, bay_gio),
    }
