"""
Từ khóa tìm nhóm do AI đề xuất (Giai đoạn 5 — AI tự mở rộng nguồn khách). Bot tìm nhóm mới trên Facebook theo danh sách từ khóa
(config.GROUP_SEARCH_QUERIES); công ty AI thêm các từ khóa MỚI (khu vực, đối tượng người mua, hình thức…) vào bảng settings
(khóa cong_ty_tu_khoa_nhom) và bot đọc thêm. Nhóm tìm được vẫn phải qua bộ lọc riêng của bot (đúng chủ đề màn hình, Hà Nội,
đủ thành viên) nên AI chỉ mở rộng lưới tìm, không tự chọn nhóm nào để tham gia.

Mỗi từ khóa AI viết phải qua kiem_tra_tu_khoa() (bằng code): 3–10 từ, chỉ chữ và dấu cách, tiếng Việt có dấu, có "màn hình" và
nhắm Hà Nội (hoặc quận / huyện của Hà Nội), không PC / laptop / linh kiện, không tỉnh khác, không chữ về giá / khuyến mãi, không
trùng từ khóa đang dùng. Hạn mức: tối đa MAX_TU_KHOA_MOI_NGAY từ khóa mỗi ngày, MAX_TU_KHOA_DANG_DUNG từ khóa AI đang dùng; chủ shop
hoàn tác thì nghỉ NGAY_NGHI_SAU_HOAN_TAC ngày. Gửi AI chỉ có các từ khóa tìm kiếm công khai.
"""
import json
import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

from cong_ty import ai, su_that
from cong_ty.de_xuat import DeXuat, chuan_hoa
from modules.db import Database

THEM_TU_KHOA = "them_tu_khoa"
SETTING = "cong_ty_tu_khoa_nhom"
SO_TU = (3, 10)
MAX_TU_KHOA_MOI_LAN = 3
MAX_TU_KHOA_MOI_NGAY = 3
MAX_TU_KHOA_DANG_DUNG = 12
NGAY_NGHI_SAU_HOAN_TAC = 7
DINH_DANG_GIO = "%Y-%m-%d %H:%M:%S"
QUAN_HUYEN = ("Cầu Giấy", "Đống Đa", "Thanh Xuân", "Hà Đông", "Nam Từ Liêm", "Bắc Từ Liêm", "Hoàng Mai", "Long Biên",
              "Hai Bà Trưng", "Ba Đình", "Tây Hồ", "Hoàn Kiếm", "Gia Lâm", "Đông Anh", "Thanh Trì", "Hoài Đức")

# Các mẫu dưới đây áp lên chữ ĐÃ BỎ DẤU (su_that.bo_dau) nên viết không dấu
_HA_NOI = re.compile(r"\bha\s*noi\b|\bhanoi\b|\bhn\b|cau\s*giay|dong\s*da|thanh\s*xuan|ha\s*dong|nam\s*tu\s*liem|bac\s*tu\s*liem"
                     r"|hoang\s*mai|long\s*bien|hai\s*ba\s*trung|ba\s*dinh|tay\s*ho|hoan\s*kiem|gia\s*lam|dong\s*anh|thanh\s*tri"
                     r"|hoai\s*duc")
_TINH_KHAC = re.compile(r"\b(?:hcm|tphcm|sg|vinh)\b|sai\s*gon|saigon|ho\s*chi\s*minh|da\s*nang|binh\s*duong|dong\s*nai|can\s*tho"
                        r"|bien\s*hoa|thu\s*duc|nha\s*trang|hai\s*phong|quang\s*ninh|nghe\s*an|\bhue\b|quang\s*nam|phu\s*yen"
                        r"|dak\s*lak|gia\s*lai|khanh\s*hoa|thanh\s*hoa|bac\s*ninh|bac\s*giang|thai\s*nguyen|nam\s*dinh"
                        r"|hai\s*duong|vung\s*tau|long\s*an|tay\s*ninh|mien\s*nam|mien\s*trung|ha\s*nam|hung\s*yen|vinh\s*phuc"
                        r"|phu\s*tho|hoa\s*binh|ninh\s*binh|thai\s*binh|lang\s*son|cao\s*bang|lao\s*cai|yen\s*bai|tuyen\s*quang"
                        r"|bac\s*kan|ha\s*giang|son\s*la|dien\s*bien|lai\s*chau")
_KHONG_PHAI_MAN_HINH = re.compile(r"\b(?:laptop|pc|vga|ssd|cpu|macbook|ram|case)\b|linh\s*kien|dien\s*thoai|may\s*tinh\s*bo")
_NOI_GIA = re.compile(r"khuyen\s*mai|giam\s*gia|gia\s*soc|re\s*nhat|mien\s*phi|\bsale\b|uu\s*dai|\bgia\b|\bre\b")
_CHI_CHU = re.compile(r"[^\W\d_]+(?: [^\W\d_]+)*")

HE_THONG = """Bạn là TRƯỞNG PHÒNG SĂN KHÁCH của shop bán màn hình MSI cũ ở Hà Nội (bán qua Facebook). Nhiệm vụ: đề xuất thêm TỪ KHÓA để tìm các nhóm Facebook mà người đang tìm mua màn hình máy tính hay tham gia.
Quy tắc bắt buộc:
- Tiếng Việt CÓ DẤU; mỗi từ khóa từ %d đến %d từ, chỉ gồm chữ và dấu cách (không số, không dấu câu, không link).
- Phải có "màn hình" và nhắm Hà Nội (ghi "Hà Nội" hoặc tên quận / huyện của Hà Nội như trong "quan_huyen_goi_y").
- KHÔNG PC, laptop, linh kiện, điện thoại; KHÔNG nhắc tỉnh khác; KHÔNG nói giá hay khuyến mãi.
- Khác hẳn các từ khóa trong "tu_khoa_hien_co": đổi góc nhìn (khu vực cụ thể, đối tượng người mua như sinh viên / dân văn phòng / game thủ, hình thức như thanh lý / mua bán / trao đổi).
Trả lời DUY NHẤT một đối tượng JSON, không thêm chữ nào ngoài JSON: {"tu_khoa": ["từ khóa 1", "từ khóa 2"]}""" % SO_TU


class LoiTuKhoa(ValueError):
    """Không soạn / thêm được từ khóa — thông báo tiếng Việt"""


@dataclass(frozen=True)
class KetQuaTuKhoa:
    tu_khoa: tuple = ()        # các từ khóa đã qua kiểm tra
    bi_loai: tuple = ()        # ((từ khóa, (lý do, ...)), ...)
    nguon: str = ""
    ghi_chu: str = ""          # câu cho biên bản họp
    so_dang_dung: int = 0      # số từ khóa tìm nhóm đang dùng (gốc + AI) lúc đề xuất


# ---------- cài đặt mà bot đọc ----------
def tu_khoa_dang_dung(db: Database) -> list[str]:
    """Các từ khóa do công ty AI thêm (bot đọc thêm khi tìm nhóm). Cài đặt hỏng thì coi như rỗng — không bao giờ làm bot lỗi"""
    try:
        data = json.loads(db.get_setting(SETTING, "[]") or "[]")
    except ValueError:
        return []
    return [x for x in data if isinstance(x, str) and x.strip()] if isinstance(data, list) else []


def _luu(db: Database, tu_khoa: list[str]) -> None:
    db.set_setting(SETTING, json.dumps(tu_khoa, ensure_ascii=False))


def them_vao_setting(db: Database, tu_khoa: list[str]) -> None:
    _luu(db, list(dict.fromkeys([*tu_khoa_dang_dung(db), *tu_khoa])))


def bo_khoi_setting(db: Database, tu_khoa: list[str]) -> None:
    bo = set(tu_khoa)
    _luu(db, [x for x in tu_khoa_dang_dung(db) if x not in bo])


# ---------- hạn mức ----------
def da_them_trong_ngay(db: Database, ngay: str) -> int:
    rows = db.query("SELECT doi_tuong FROM nhat_ky_hanh_dong WHERE hanh_dong = ? AND luc LIKE ? AND hoan_tac_luc IS NULL",
                    (THEM_TU_KHOA, ngay + "%"))
    return sum(len(json.loads(r["doi_tuong"]).get("tu_khoa", [])) for r in rows)


def dang_nghi(db: Database, bay_gio: datetime) -> str:
    tu = (bay_gio - timedelta(days=NGAY_NGHI_SAU_HOAN_TAC)).strftime(DINH_DANG_GIO)
    if db.query("SELECT 1 FROM nhat_ky_hanh_dong WHERE hanh_dong = ? AND hoan_tac_luc >= ? LIMIT 1", (THEM_TU_KHOA, tu)):
        return (f"Bạn vừa hoàn tác từ khóa tìm nhóm do AI thêm — công ty nghỉ {NGAY_NGHI_SAU_HOAN_TAC} ngày "
                "để bạn quyết định có muốn tiếp tục không.")
    return ""


# ---------- rào chắn cho từng từ khóa ----------
def kiem_tra_tu_khoa(tu_khoa: str, da_co: list[str]) -> tuple[str, ...]:
    """Các vấn đề của một từ khóa tìm nhóm do AI viết (rỗng = dùng được). da_co: các từ khóa đã có (gốc + AI)"""
    chu = " ".join(su_that.lam_sach(tu_khoa).split())
    khong_dau = su_that.bo_dau(chu)
    van_de = []
    if not _CHI_CHU.fullmatch(chu):
        van_de.append("chỉ được gồm chữ và dấu cách (không số, dấu câu, đường link)")
    so_tu = len(chu.split())
    if not SO_TU[0] <= so_tu <= SO_TU[1]:
        van_de.append(f"cần từ {SO_TU[0]} đến {SO_TU[1]} từ (đang có {so_tu})")
    if not any(ord(c) > 127 for c in chu):
        van_de.append("thiếu dấu tiếng Việt (phải viết có dấu)")
    if "man hinh" not in khong_dau:
        van_de.append("phải có “màn hình”")
    if not _HA_NOI.search(khong_dau):
        van_de.append("phải nhắm khách ở Hà Nội (ghi “Hà Nội” hoặc tên quận / huyện của Hà Nội)")
    m = _TINH_KHAC.search(khong_dau)
    if m:
        van_de.append(f"nhắm tỉnh khác (“{m.group(0)}”) — shop chỉ bán Hà Nội và lân cận")
    if _KHONG_PHAI_MAN_HINH.search(khong_dau):
        van_de.append("nhắm sang PC / laptop / linh kiện / điện thoại — chỉ tìm nhóm màn hình")
    if _NOI_GIA.search(khong_dau):
        van_de.append("có chữ về giá / khuyến mãi (cấm cứng)")
    if khong_dau in {su_that.bo_dau(x) for x in da_co}:
        van_de.append("trùng với một từ khóa đang có")
    return tuple(van_de)


# ---------- soạn từ khóa bằng AI ----------
def _doc_tra_loi(kq: ai.KetQuaAI | None) -> tuple[list[str], str]:
    if kq is None:
        return [], "AI không trả lời (hết lượt hoặc lỗi mạng)"
    try:
        data = ai.doc_json(kq.van_ban)
    except ValueError:
        return [], "không đọc được câu trả lời của AI (không phải JSON hợp lệ)"
    ds = data.get("tu_khoa") if isinstance(data, dict) else None
    chu = [x.strip() for x in ds if isinstance(x, str) and x.strip()] if isinstance(ds, list) else []
    return chu, "" if chu else "AI không đề xuất được từ khóa nào"


def soan_tu_khoa(db: Database, truy_van_goc: tuple[str, ...], bo_ai, bay_gio: datetime) -> KetQuaTuKhoa:
    """Nhờ AI đề xuất từ khóa tìm nhóm MỚI; chỉ giữ từ khóa qua rào chắn. Không đủ điều kiện (hết lượt AI, đang nghỉ, hết hạn mức)
    thì KHÔNG gọi AI"""
    dang_dung = tu_khoa_dang_dung(db)
    tong = len(truy_van_goc) + len(dang_dung)
    if not bo_ai.con_luot():
        return KetQuaTuKhoa(ghi_chu="Hết lượt AI miễn phí — hôm nay không đề xuất từ khóa tìm nhóm.", so_dang_dung=tong)
    nghi = dang_nghi(db, bay_gio)
    if nghi:
        return KetQuaTuKhoa(ghi_chu=nghi, so_dang_dung=tong)
    con_hom_nay = MAX_TU_KHOA_MOI_NGAY - da_them_trong_ngay(db, bay_gio.strftime("%Y-%m-%d"))
    if con_hom_nay <= 0:
        return KetQuaTuKhoa(ghi_chu=f"Hôm nay đã thêm đủ {MAX_TU_KHOA_MOI_NGAY} từ khóa tìm nhóm — để mai.", so_dang_dung=tong)
    con_cho = MAX_TU_KHOA_DANG_DUNG - len(dang_dung)
    if con_cho <= 0:
        return KetQuaTuKhoa(ghi_chu=f"Đã có tối đa {MAX_TU_KHOA_DANG_DUNG} từ khóa tìm nhóm do AI thêm.", so_dang_dung=tong)
    so_luong = min(MAX_TU_KHOA_MOI_LAN, con_hom_nay, con_cho)
    da_co = [*truy_van_goc, *dang_dung]
    nguoi_dung = json.dumps({"tu_khoa_hien_co": da_co, "so_luong": so_luong, "quan_huyen_goi_y": list(QUAN_HUYEN)},
                            ensure_ascii=False)
    kq = bo_ai.hoi(HE_THONG, nguoi_dung, nhan="tim_nhom")
    nguon = kq.nguon if kq else ""
    ung_vien, loi = _doc_tra_loi(kq)
    if loi:
        return KetQuaTuKhoa(nguon=nguon, ghi_chu=f"Chưa có từ khóa mới: {loi}.", so_dang_dung=tong)
    giu, bi_loai = [], []
    for chu in ung_vien:
        if len(giu) >= so_luong:
            break
        van_de = kiem_tra_tu_khoa(chu, [*da_co, *giu])
        if van_de:
            bi_loai.append((chu, van_de))
        else:
            giu.append(" ".join(su_that.lam_sach(chu).split()))
    ghi_chu = f"Đã chọn {len(giu)} từ khóa tìm nhóm mới"
    if bi_loai:
        ghi_chu += f", loại {len(bi_loai)} từ khóa không đạt: " + " | ".join("; ".join(v[:2]) for _, v in bi_loai[:3])
    return KetQuaTuKhoa(tuple(giu), tuple(bi_loai), nguon, ghi_chu + ".", tong)


def de_xuat_tu_ket_qua(kq: KetQuaTuKhoa, hom_nay: date) -> DeXuat:
    """Đề xuất do CODE dựng từ các từ khóa AI đã viết; việc cần làm (tham_so) do code ghi, AI không chạm vào"""
    dx = chuan_hoa("san_khach", {
        "loai": "nhom_moi", "tieu_de": f"Tìm nhóm bằng {len(kq.tu_khoa)} từ khóa mới do AI đề xuất",
        "noi_dung": ("Tìm và tham gia thêm nhóm Facebook mua bán màn hình ở Hà Nội bằng các từ khóa: "
                     + "; ".join(kq.tu_khoa)),
        "vi_sao": (f"Hiện công ty đang tìm nhóm bằng {kq.so_dang_dung} từ khóa; từ khóa mới giúp thấy thêm nhóm ngoài danh sách. "
                   "Nhóm tìm được vẫn phải qua bộ lọc của bot (đúng chủ đề màn hình, ở Hà Nội, đủ thành viên)."),
        "ky_vong": "thêm nhóm có người đang tìm mua màn hình, tăng số bài MUA thấy được mỗi ngày",
        "rui_ro": "tìm nhiều hơn thì bot mở Facebook tìm kiếm nhiều hơn; từ khóa không hiệu quả có thể hoàn tác", "ngay_do": 7},
        hom_nay)
    return replace(dx, tham_so=json.dumps({"hanh_dong": THEM_TU_KHOA, "tu_khoa": list(kq.tu_khoa)}, ensure_ascii=False))


# ---------- thực hiện (hanh_dong.thuc_hien gọi) ----------
def chuan_bi_them(db: Database, du_lieu: dict, truy_van_goc: tuple[str, ...], bay_gio: datetime) -> list[str]:
    """Kiểm tra LẠI mọi thứ ở thời điểm thực hiện rồi trả về các từ khóa sẽ thêm. Sai thì LoiTuKhoa và chưa sửa gì"""
    tu_khoa = du_lieu.get("tu_khoa")
    if not isinstance(tu_khoa, list) or not 1 <= len(tu_khoa) <= MAX_TU_KHOA_MOI_LAN \
            or not all(isinstance(x, str) for x in tu_khoa):
        raise LoiTuKhoa(f"Việc thêm từ khóa phải có từ 1 đến {MAX_TU_KHOA_MOI_LAN} từ khóa")
    dang_dung = tu_khoa_dang_dung(db)
    con_ngay = MAX_TU_KHOA_MOI_NGAY - da_them_trong_ngay(db, bay_gio.strftime("%Y-%m-%d"))
    if len(tu_khoa) > con_ngay:
        raise LoiTuKhoa(f"Hôm nay chỉ còn thêm được {max(con_ngay, 0)} từ khóa (tối đa {MAX_TU_KHOA_MOI_NGAY} mỗi ngày)")
    if len(dang_dung) + len(tu_khoa) > MAX_TU_KHOA_DANG_DUNG:
        raise LoiTuKhoa(f"Quá hạn mức: tối đa {MAX_TU_KHOA_DANG_DUNG} từ khóa do AI thêm đang dùng")
    da_co, giu = [*truy_van_goc, *dang_dung], []
    for chu in tu_khoa:
        van_de = kiem_tra_tu_khoa(chu, [*da_co, *giu])
        if van_de:
            raise LoiTuKhoa(f"Từ khóa không đạt kiểm tra: {'; '.join(van_de[:3])}")
        giu.append(" ".join(su_that.lam_sach(chu).split()))
    return giu
