"""
Sổ ghi khách — "kết quả" mà bot không tự biết: mỗi dòng là một lượt khách Gọi / Nhắn / Mua kèm nguồn (nhóm nào).

Chủ shop ghi tay trên web (tab Công ty AI), khoảng 1 phút mỗi tối. Báo cáo sáng dùng số này để biết nhóm nào ra khách.
Mọi dữ liệu nhập đi qua chuan_hoa(): sai thì ném ValueError kèm lý do tiếng Việt để web báo lại cho người nhập.
"""
from dataclasses import dataclass
from datetime import date, datetime

from modules.db import Database, now_str

LOAI = ("Gọi", "Nhắn", "Mua")
KHONG_RO = "Không rõ"       # lượt khách chưa biết nguồn
KHONG_GIOI_HAN_NGAY = "9999-12-31"   # cận trên (không gồm) khi không giới hạn ngày
MAX_ID = 2 ** 63 - 1        # id lớn hơn số này SQLite không nhận
MAX_SO_LUONG = 500
MAX_SO_TIEN = 10_000_000_000
MAX_NGUON, MAX_SAN_PHAM, MAX_GHI_CHU = 200, 200, 500
MAX_DONG = 500              # liet_ke() trả tối đa ... dòng

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS khach (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        ngay       TEXT NOT NULL,             -- YYYY-MM-DD, ngày khách liên hệ
        loai       TEXT NOT NULL,             -- Gọi / Nhắn / Mua
        so_luong   INTEGER NOT NULL DEFAULT 1,
        nguon      TEXT NOT NULL DEFAULT '',  -- tên nhóm / nơi khách biết shop ('' = chưa rõ)
        san_pham   TEXT NOT NULL DEFAULT '',
        so_tien    INTEGER,                   -- VND, thường chỉ ghi khi Mua
        ghi_chu    TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_khach_ngay ON khach(ngay)",
)
# Biểu thức SQL cố định do module này chọn (không bao giờ nhận từ người dùng) để gom theo ngày / theo nguồn
_COT_NGAY = "ngay"
_COT_NGUON = f"CASE WHEN nguon = '' THEN '{KHONG_RO}' ELSE nguon END"


@dataclass(frozen=True)
class Khach:
    ngay: str
    loai: str
    so_luong: int
    nguon: str
    san_pham: str
    so_tien: int | None
    ghi_chu: str


def ensure_schema(db: Database) -> None:
    for sql in SCHEMA:
        db.execute(sql)


def _so_nguyen(gia_tri, ten: str, thap: int, cao: int, bo_dau_cach: bool = False) -> int:
    chu = str(gia_tri).strip()
    if bo_dau_cach:  # "2.500.000" / "2,500,000" / "2 500 000"
        chu = chu.replace(".", "").replace(",", "").replace(" ", "")
    try:
        so = int(chu)
    except ValueError:
        raise ValueError(f"{ten} phải là số nguyên") from None
    if not thap <= so <= cao:
        raise ValueError(f"{ten} phải từ {thap} đến {cao}")
    return so


def _chu(gia_tri, ten: str, toi_da: int) -> str:
    chu = ("" if gia_tri is None else str(gia_tri)).strip()
    if len(chu) > toi_da:
        raise ValueError(f"{ten} dài tối đa {toi_da} ký tự")
    return chu


def chuan_hoa(ngay, loai, so_luong=1, nguon="", san_pham="", so_tien=None, ghi_chu="",
              hom_nay: date | None = None) -> Khach:
    """Kiểm tra + chuẩn hóa 1 dòng nhập từ web; sai thì ValueError với lý do tiếng Việt"""
    try:
        ngay_thuc = datetime.strptime(str(ngay).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Ngày phải có dạng năm-tháng-ngày, ví dụ 2026-10-24") from None
    if ngay_thuc > (hom_nay or date.today()):
        raise ValueError("Ngày không được ở tương lai")
    loai = str(loai).strip()
    if loai not in LOAI:
        raise ValueError(f"Loại phải là một trong: {', '.join(LOAI)}")
    tien = None if so_tien in (None, "") else _so_nguyen(so_tien, "Số tiền", 0, MAX_SO_TIEN, bo_dau_cach=True)
    return Khach(ngay=ngay_thuc.strftime("%Y-%m-%d"), loai=loai,
                 so_luong=_so_nguyen(so_luong, "Số lượng", 1, MAX_SO_LUONG),
                 nguon=_chu(nguon, "Nguồn", MAX_NGUON), san_pham=_chu(san_pham, "Sản phẩm", MAX_SAN_PHAM),
                 so_tien=tien, ghi_chu=_chu(ghi_chu, "Ghi chú", MAX_GHI_CHU))


def them(db: Database, k: Khach) -> int:
    return db.execute(
        "INSERT INTO khach (ngay, loai, so_luong, nguon, san_pham, so_tien, ghi_chu, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (k.ngay, k.loai, k.so_luong, k.nguon, k.san_pham, k.so_tien, k.ghi_chu, now_str()))


def liet_ke(db: Database, tu_ngay: str) -> list[dict]:
    """Các dòng từ ngày ... trở đi, mới nhất trước (tối đa MAX_DONG dòng)"""
    return db.query("SELECT * FROM khach WHERE ngay >= ? ORDER BY ngay DESC, id DESC LIMIT ?", (tu_ngay, MAX_DONG))


def xoa(db: Database, khach_id: int) -> bool:
    """Xóa 1 dòng ghi nhầm. False nếu không có dòng đó (kể cả id không thể tồn tại)"""
    if not 0 < khach_id <= MAX_ID or not db.query("SELECT 1 FROM khach WHERE id = ?", (khach_id,)):
        return False
    db.execute("DELETE FROM khach WHERE id = ?", (khach_id,))
    return True


def _tong(db: Database, tu_ngay: str, den_ngay: str, cot: str) -> dict[str, dict[str, int]]:
    tong: dict[str, dict[str, int]] = {}
    for r in db.query(f"SELECT {cot} AS khoa, loai, SUM(so_luong) AS n, SUM(COALESCE(so_tien, 0)) AS tien "
                      "FROM khach WHERE ngay >= ? AND ngay < ? GROUP BY khoa, loai", (tu_ngay, den_ngay)):
        dong = tong.setdefault(r["khoa"], {**{loai: 0 for loai in LOAI}, "so_tien": 0})
        dong[r["loai"]] = r["n"]
        dong["so_tien"] += r["tien"]
    return tong


def tong_theo_ngay(db: Database, tu_ngay: str, den_ngay: str = KHONG_GIOI_HAN_NGAY) -> dict[str, dict[str, int]]:
    """{ngày: {'Gọi': n, 'Nhắn': n, 'Mua': n, 'so_tien': VND}} từ ngày `tu_ngay` tới trước ngày `den_ngay`"""
    return _tong(db, tu_ngay, den_ngay, _COT_NGAY)


def tong_theo_nguon(db: Database, tu_ngay: str, den_ngay: str = KHONG_GIOI_HAN_NGAY) -> dict[str, dict[str, int]]:
    """Như tong_theo_ngay nhưng gom theo nguồn (nhóm); nguồn trống = 'Không rõ'"""
    return _tong(db, tu_ngay, den_ngay, _COT_NGUON)
