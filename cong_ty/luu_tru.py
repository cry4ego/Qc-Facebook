"""
Kho lưu cuộc họp của công ty AI trong CSDL của bot:
  cuoc_hop — mỗi cuộc họp (ngày, trạng thái, nguồn AI đã dùng, tóm tắt của Giám đốc, bản chữ báo cáo sáng)
  ban_tin  — biên bản: lời của từng vai ở từng vòng
  de_xuat  — mỗi đề xuất và số phận của nó (chờ duyệt / bị chặn / hoãn / bạn duyệt / từ chối / đã làm)
Cờ "Họp ngay" từ web và ngày bắt đầu chế độ quan sát nằm trong bảng settings sẵn có.
"""
import sqlite3
from datetime import date, datetime, timedelta

from cong_ty.de_xuat import DeXuat
from modules.db import Database

DINH_DANG_GIO = "%Y-%m-%d %H:%M:%S"
MAX_ID = 2 ** 63 - 1     # id lớn hơn số này SQLite không nhận

# trạng thái cuộc họp
DANG_HOP, XONG, LOI = "dang_hop", "xong", "loi"
# trạng thái đề xuất
CHO_DUYET, HOAN, BI_CHAN = "cho_duyet", "hoan", "bi_chan"
DA_DUYET, TU_CHOI, DA_LAM = "da_duyet", "tu_choi", "da_lam"
DANG_LAM = "dang_lam"       # trạng thái tạm: công ty đang làm việc trong đề xuất (xem nhan_viec) — chủ shop không đổi được lúc này
QUYET_DINH_CHU_SHOP = (DA_DUYET, TU_CHOI, DA_LAM)
CHUYEN_DUOC = {CHO_DUYET: (DA_DUYET, TU_CHOI), DA_DUYET: (DA_LAM,)}   # chủ shop chỉ đi theo các bước này
KHONG_DE_XUAT_LAI = (CHO_DUYET, DA_DUYET, DA_LAM, TU_CHOI)           # đã nêu / đã quyết thì chưa đề xuất lại ngay

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS cuoc_hop (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        ngay       TEXT NOT NULL,                 -- YYYY-MM-DD
        bat_dau    TEXT NOT NULL,                 -- YYYY-MM-DD HH:MM:SS
        ket_thuc   TEXT,
        trang_thai TEXT NOT NULL,                 -- dang_hop / xong / loi
        nguon_ai   TEXT NOT NULL DEFAULT '',      -- vd "gemini"; trống = họp không có AI
        so_luot_ai INTEGER NOT NULL DEFAULT 0,
        tom_tat    TEXT NOT NULL DEFAULT '',      -- lời tóm tắt của Giám đốc cho chủ shop
        bao_cao    TEXT NOT NULL DEFAULT '',      -- bản chữ báo cáo sáng của ngày họp
        loi        TEXT NOT NULL DEFAULT ''
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cuoc_hop_ngay ON cuoc_hop(ngay)",
    """CREATE TABLE IF NOT EXISTS ban_tin (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        cuoc_hop_id INTEGER NOT NULL,
        vai         TEXT NOT NULL,
        vong        INTEGER NOT NULL DEFAULT 1,
        noi_dung    TEXT NOT NULL,
        tao_luc     TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS de_xuat (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        cuoc_hop_id      INTEGER NOT NULL,
        vai              TEXT NOT NULL,
        loai             TEXT NOT NULL,
        tieu_de          TEXT NOT NULL,
        noi_dung         TEXT NOT NULL,
        vi_sao           TEXT NOT NULL,
        ky_vong          TEXT NOT NULL DEFAULT '',
        rui_ro           TEXT NOT NULL DEFAULT '',
        ngay_do          TEXT NOT NULL,
        nguon            TEXT NOT NULL,           -- luat / ai
        trang_thai       TEXT NOT NULL,
        ly_do            TEXT NOT NULL DEFAULT '',   -- vì sao bị chặn / hoãn
        quyet_luc        TEXT,
        ghi_chu_chu_shop TEXT NOT NULL DEFAULT '',
        tao_luc          TEXT NOT NULL,
        tham_so          TEXT NOT NULL DEFAULT ''    -- JSON việc công ty tự làm được (chỉ do luật gắn); trống = làm tay
    )""",
    "CREATE INDEX IF NOT EXISTS idx_de_xuat_trang_thai ON de_xuat(trang_thai)",
)


def ensure_schema(db: Database) -> None:
    for sql in SCHEMA:
        db.execute(sql)
    # CSDL tạo từ Giai đoạn 2 chưa có cột tham_so
    if "tham_so" not in {c["name"] for c in db.query("PRAGMA table_info(de_xuat)")}:
        try:
            db.execute("ALTER TABLE de_xuat ADD COLUMN tham_so TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:     # tiến trình khác (web / cửa sổ họp) vừa thêm cột này
            if "tham_so" not in {c["name"] for c in db.query("PRAGMA table_info(de_xuat)")}:
                raise


def _gio(bay_gio: date | datetime) -> str:
    return bay_gio.strftime(DINH_DANG_GIO)


# ---------- cuộc họp ----------
def tao_cuoc_hop(db: Database, ngay: str, bay_gio: datetime) -> int:
    return db.execute("INSERT INTO cuoc_hop (ngay, bat_dau, trang_thai) VALUES (?, ?, ?)", (ngay, _gio(bay_gio), DANG_HOP))


def ket_thuc_cuoc_hop(db: Database, cuoc_id: int, trang_thai: str, nguon_ai: str, so_luot_ai: int, tom_tat: str,
                      bao_cao: str, bay_gio: datetime, loi: str = "") -> None:
    db.execute("UPDATE cuoc_hop SET trang_thai = ?, nguon_ai = ?, so_luot_ai = ?, tom_tat = ?, bao_cao = ?, "
               "ket_thuc = ?, loi = ? WHERE id = ?",
               (trang_thai, nguon_ai, so_luot_ai, tom_tat, bao_cao, _gio(bay_gio), loi, cuoc_id))


def dang_hop_gan_day(db: Database, bay_gio: datetime, phut: int) -> bool:
    """Có cuộc họp đang diễn ra (bắt đầu chưa quá `phut` phút trước)? Cuộc họp 'đang họp' cũ hơn coi là kẹt, không tính"""
    tu = (bay_gio - timedelta(minutes=phut)).strftime(DINH_DANG_GIO)
    return bool(db.query("SELECT 1 FROM cuoc_hop WHERE trang_thai = ? AND bat_dau >= ? LIMIT 1", (DANG_HOP, tu)))


def cuoc_hop_cua_ngay(db: Database, ngay: str) -> list[dict]:
    """Các cuộc họp của ngày `ngay`, mới nhất trước"""
    return db.query("SELECT * FROM cuoc_hop WHERE ngay = ? ORDER BY id DESC", (ngay,))


def cuoc_hop(db: Database, cuoc_id: int) -> dict | None:
    rows = db.query("SELECT * FROM cuoc_hop WHERE id = ?", (cuoc_id,))
    return rows[0] if rows else None


def cuoc_hop_gan_nhat(db: Database) -> dict | None:
    rows = db.query("SELECT * FROM cuoc_hop ORDER BY id DESC LIMIT 1")
    return rows[0] if rows else None


# ---------- biên bản ----------
def them_ban_tin(db: Database, cuoc_id: int, vai: str, vong: int, noi_dung: str, bay_gio: datetime) -> None:
    db.execute("INSERT INTO ban_tin (cuoc_hop_id, vai, vong, noi_dung, tao_luc) VALUES (?, ?, ?, ?, ?)",
               (cuoc_id, vai, vong, noi_dung, _gio(bay_gio)))


def ban_tin_cua(db: Database, cuoc_id: int) -> list[dict]:
    return db.query("SELECT * FROM ban_tin WHERE cuoc_hop_id = ? ORDER BY id", (cuoc_id,))


# ---------- đề xuất ----------
def them_de_xuat(db: Database, cuoc_id: int, dx: DeXuat, nguon: str, trang_thai: str, ly_do: str,
                 bay_gio: datetime) -> int:
    return db.execute(
        "INSERT INTO de_xuat (cuoc_hop_id, vai, loai, tieu_de, noi_dung, vi_sao, ky_vong, rui_ro, ngay_do, nguon, "
        "trang_thai, ly_do, tao_luc, tham_so) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cuoc_id, dx.vai, dx.loai, dx.tieu_de, dx.noi_dung, dx.vi_sao, dx.ky_vong, dx.rui_ro, dx.ngay_do, nguon,
         trang_thai, ly_do, _gio(bay_gio), dx.tham_so))


def de_xuat_theo_id(db: Database, de_xuat_id: int) -> dict | None:
    rows = db.query("SELECT * FROM de_xuat WHERE id = ?", (de_xuat_id,)) if 0 < de_xuat_id <= MAX_ID else []
    return rows[0] if rows else None


def nhan_viec(db: Database, de_xuat_id: int, bay_gio: date | datetime) -> str | None:
    """NHẬN việc của đề xuất trước khi làm: đang chờ duyệt / đã duyệt -> DANG_LAM (chỉ MỘT bên nhận được: bấm tay hay cuộc họp
    tự làm không thể cùng làm một việc). Trả về trạng thái cũ (để trả lại nếu làm hỏng), None nếu không nhận được"""
    cu = (db.query("SELECT trang_thai FROM de_xuat WHERE id = ?", (de_xuat_id,)) or [{}])[0].get("trang_thai")
    if cu not in (CHO_DUYET, DA_DUYET):
        return None
    nhan = db.query("UPDATE de_xuat SET trang_thai = ?, quyet_luc = ? WHERE id = ? AND trang_thai = ? RETURNING id",
                    (DANG_LAM, _gio(bay_gio), de_xuat_id, cu))
    return cu if nhan else None


def tra_viec(db: Database, de_xuat_id: int, trang_thai_cu: str) -> None:
    """Làm không được (hoặc hỏng giữa chừng): trả đề xuất về trạng thái cũ để chủ shop vẫn thấy và xử lý"""
    db.execute("UPDATE de_xuat SET trang_thai = ? WHERE id = ? AND trang_thai = ?", (trang_thai_cu, de_xuat_id, DANG_LAM))


def hoan_tat_viec(db: Database, de_xuat_id: int, ghi_chu: str, bay_gio: date | datetime) -> bool:
    """Việc đã làm xong: DANG_LAM -> DA_LAM. False nếu đề xuất không còn ở trạng thái đang làm"""
    return bool(db.query(
        "UPDATE de_xuat SET trang_thai = ?, ghi_chu_chu_shop = ?, quyet_luc = ? WHERE id = ? AND trang_thai = ? RETURNING id",
        (DA_LAM, ghi_chu, _gio(bay_gio), de_xuat_id, DANG_LAM)))


def liet_ke_de_xuat(db: Database, trang_thai: str | None = None, cuoc_hop_id: int | None = None,
                    limit: int = 100) -> list[dict]:
    """Đề xuất mới nhất trước, lọc theo trạng thái / cuộc họp"""
    dieu_kien, tham_so = ["1 = 1"], []
    if trang_thai:
        dieu_kien.append("trang_thai = ?")
        tham_so.append(trang_thai)
    if cuoc_hop_id is not None:
        dieu_kien.append("cuoc_hop_id = ?")
        tham_so.append(cuoc_hop_id)
    return db.query(f"SELECT * FROM de_xuat WHERE {' AND '.join(dieu_kien)} ORDER BY id DESC LIMIT ?",
                    (*tham_so, limit))


def dem_cho_duyet(db: Database) -> int:
    return db.query("SELECT COUNT(*) AS n FROM de_xuat WHERE trang_thai = ?", (CHO_DUYET,))[0]["n"]


def da_de_xuat_gan_day(db: Database, dx: DeXuat, tu_ngay: str, bo_qua_cuoc_hop: int | None = None) -> bool:
    """Đề xuất cùng loại + tiêu đề đang chờ duyệt / đã duyệt / đã làm / bị từ chối kể từ ngày `tu_ngay` (không tính cuộc
    họp `bo_qua_cuoc_hop`). Đề xuất bị chặn hoặc hoãn không tính — mai được đề xuất lại"""
    dau_cham = ", ".join("?" * len(KHONG_DE_XUAT_LAI))
    return bool(db.query(
        f"SELECT 1 FROM de_xuat WHERE loai = ? AND tieu_de = ? AND tao_luc >= ? AND trang_thai IN ({dau_cham}) "
        "AND cuoc_hop_id != ? LIMIT 1", (dx.loai, dx.tieu_de, tu_ngay, *KHONG_DE_XUAT_LAI, bo_qua_cuoc_hop or 0)))


def quyet_dinh(db: Database, de_xuat_id: int, quyet: str, ghi_chu: str, bay_gio: date | datetime) -> None:
    """Chủ shop duyệt / từ chối / đánh dấu đã làm. LookupError nếu không có đề xuất; ValueError nếu quyết định hoặc bước
    chuyển không hợp lệ (vd duyệt đề xuất đã bị Kiểm soát rủi ro chặn)"""
    rows = db.query("SELECT trang_thai FROM de_xuat WHERE id = ?", (de_xuat_id,)) if 0 < de_xuat_id <= MAX_ID else []
    if not rows:
        raise LookupError("Không tìm thấy đề xuất này")
    if quyet not in QUYET_DINH_CHU_SHOP:
        raise ValueError(f"Quyết định phải là một trong: {', '.join(QUYET_DINH_CHU_SHOP)}")
    hien_tai = rows[0]["trang_thai"]
    if quyet not in CHUYEN_DUOC.get(hien_tai, ()):
        raise ValueError(f"Không thể chuyển đề xuất từ “{hien_tai}” sang “{quyet}”")
    # chỉ đổi nếu trạng thái VẪN là `hien_tai`: hai yêu cầu cùng lúc thì yêu cầu chậm hơn bị từ chối, không ghi đè
    da_doi = db.query("UPDATE de_xuat SET trang_thai = ?, ghi_chu_chu_shop = ?, quyet_luc = ? WHERE id = ? "
                      "AND trang_thai = ? RETURNING id", (quyet, ghi_chu, _gio(bay_gio), de_xuat_id, hien_tai))
    if not da_doi:
        raise ValueError("Đề xuất vừa được đổi trạng thái ở nơi khác — tải lại trang rồi thử lại")


# ---------- cờ "Họp ngay" và chế độ quan sát ----------
def yeu_cau_hop(db: Database) -> None:
    db.set_setting("cong_ty_hop_yeu_cau", "1")


def dang_cho_hop(db: Database) -> bool:
    return db.get_setting("cong_ty_hop_yeu_cau", "0") == "1"


def xoa_yeu_cau_hop(db: Database) -> None:
    db.set_setting("cong_ty_hop_yeu_cau", "0")


def ghi_bat_dau_quan_sat(db: Database, ngay: str) -> None:
    """Ghi ngày họp đầu tiên làm ngày bắt đầu chế độ quan sát (chỉ ghi một lần)"""
    if not db.get_setting("cong_ty_bat_dau"):
        db.set_setting("cong_ty_bat_dau", ngay)


def tu_lam_dang_bat(db: Database) -> bool:
    """Công tắc "công ty tự làm" (mặc định TẮT). Bật chưa đủ: còn phải hết chế độ quan sát — xem duoc_tu_lam()"""
    return db.get_setting("cong_ty_tu_lam", "0") == "1"


def dat_tu_lam(db: Database, bat: bool) -> None:
    db.set_setting("cong_ty_tu_lam", "1" if bat else "0")


def duoc_tu_lam(db: Database, hom_nay: date, tong_ngay_quan_sat: int) -> bool:
    """Công ty được tự làm việc do luật đề xuất khi: công tắc bật VÀ đã hết `tong_ngay_quan_sat` ngày quan sát"""
    return tu_lam_dang_bat(db) and che_do(db, hom_nay, tong_ngay_quan_sat)["xong"]


def che_do(db: Database, hom_nay: date, tong_ngay: int) -> dict:
    """Chế độ quan sát: công ty chỉ họp và đề xuất, chưa tự làm gì. ngay = đang ở ngày thứ mấy (0 = chưa họp lần nào)"""
    bat_dau = db.get_setting("cong_ty_bat_dau")
    ngay = max((hom_nay - datetime.strptime(bat_dau, "%Y-%m-%d").date()).days + 1, 0) if bat_dau else 0
    return {"ten": "quan_sat", "ngay": ngay, "tong": tong_ngay, "xong": ngay >= tong_ngay}
