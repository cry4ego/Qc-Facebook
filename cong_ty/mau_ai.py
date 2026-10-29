"""
Mẫu bình luận do AI viết (Giai đoạn 5 — AI tự điều hành nội dung). Từ 26/10/2026 bình luận chỉ là một THẺ NGẮN theo yêu cầu chủ shop
(chữ dài làm khách khó nhớ, ít chú ý và nghĩ là spam): mã màn, thông số, công nghệ — rồi MỘT dòng liên hệ "Dũng-0902189751-64 Cầu Diễn"
(tên gọi - SĐT liền - số nhà + phố; 28/10 chủ shop bỏ họ tên đầy đủ vì Facebook gợi ý gắn thẻ nhầm người). Không lời chào, không giá,
không bảo hành, không "đã qua sử dụng" (giá / SĐT / địa chỉ đã in sẵn trong ảnh bán hàng đính kèm).

AI chỉ viết phần ĐẦU (tối đa 3 dòng thông số); dòng liên hệ cuối do CODE ghép từ sổ sự thật (noi_dung.lien_he_gon), AI không viết và
không sửa được. Dòng có SĐT nên bản không SĐT/địa chỉ (products.make_safe) bỏ nguyên dòng, chỉ còn thẻ thông số.

Mọi chữ AI viết phải qua kiem_tra_mo_dau() (bằng code, không dùng AI): đúng là thẻ thông số (có mã màn, ≥2 thông số, mọi từ nằm trong
mô tả thật của sản phẩm nên không viết được văn xuôi), không SĐT / link / emoji / giá / bảo hành / lời cam kết, không bịa thông số,
không trùng y hệt mẫu đang có. Giới hạn cứng: tối đa MAX_MAU_AI_MOI_NGAY mẫu mỗi ngày, MAX_MAU_AI_DANG_BAT mẫu AI đang bật (mẫu AI chỉ
là một phần nhỏ trong hàng trăm mẫu nên là "thử nghiệm" ở tỷ lệ nhỏ), mỗi sản phẩm tối đa MAX_MAU_AI_MOI_SAN_PHAM. Mẫu nào hay bị
Facebook từ chối thì luật có sẵn đề xuất tắt (hanh_dong.TAT_MAU); chủ shop hoàn tác việc thêm mẫu thì công ty nghỉ
NGAY_NGHI_SAU_HOAN_TAC ngày.

Riêng tư: gửi cho AI chỉ có tên sản phẩm và mô tả thông số đã bỏ các dòng liên hệ — không SĐT, địa chỉ, tên người bán, bài của khách.
"""
import json
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

from cong_ty import ai, rao_chan, su_that
from cong_ty.de_xuat import DeXuat, chuan_hoa
from modules import noi_dung, products
from modules.db import Database

THEM_MAU = "them_mau"
DO_DAI_MO_DAU = (25, 140)
SO_DONG_MO_DAU_TOI_DA = 3
MAX_MO_DAU_MOI_LAN = 3
MAX_MAU_AI_MOI_NGAY = 3
MAX_MAU_AI_DANG_BAT = 9
MAX_MAU_AI_MOI_SAN_PHAM = 3
NGAY_NGHI_SAU_HOAN_TAC = 7
NGUONG_GIONG = 0.95             # giống mẫu có sẵn từ ngần này (0..1) thì bỏ; thẻ thông số các kiểu trình bày vốn gần nhau nên chỉ loại bản y hệt
MAX_ID = 2 ** 63 - 1
DINH_DANG_GIO = "%Y-%m-%d %H:%M:%S"
MOC_PHAN_CUOI = re.compile(r"^(?:Người bán:|Lưu ý: đây là màn cũ)", re.MULTILINE)   # dòng đầu phần do code ghép của các khuôn CŨ (sáng 28/10 / 25/10)
DONG_LIEN_HE = re.compile(r"^\S+-\d{9,11}-.+$")       # dòng liên hệ hiện nay: "Dũng-0902189751-64 Cầu Diễn"
KIEU_TRINH_BAY = ("một dòng: mã màn – thông số – công nghệ, ngăn bằng dấu gạch ngang và dấu chấm giữa (·)",
                  "hai dòng: dòng 1 là mã màn và thông số, dòng 2 bắt đầu bằng “Công nghệ:”",
                  "ba dòng: “Mã màn: …”, “Thông số: …”, “Công nghệ: …”",
                  "một dòng, các mục ngăn bằng dấu gạch đứng |")

# Các mẫu dưới đây áp lên chữ ĐÃ BỎ DẤU (su_that.bo_dau) nên viết không dấu
_LIEN_HE = re.compile(r"\b(?:zalo|hotline|sdt|inbox|ib|pm|messenger|fanpage|website|nhan\s*tin|goi\s*(?:ngay|cho|dien)"
                      r"|goi\s*(?:em|anh|chi|minh|toi|shop|nhe)|nhan\s*(?:em|minh|shop|cho|nhe)|alo|lien\s*lac|ket\s*ban"
                      r"|theo\s*doi|add\s*(?:zalo|fb|face)|lien\s*he|so\s*dien\s*thoai|dia\s*chi)\b")
_CHINH_SACH = re.compile(r"bao\s*hanh|\bbh\b|doi\s*tra|loi\s*doi|1\s*doi\s*1|hoan\s*tien|giao\s*hang|\bship\b|free\s*ship|freeship"
                         r"|van\s*chuyen|thanh\s*toan|tra\s*gop|\bcod\b|dat\s*coc|dung\s*thu")
_CAM_KET = re.compile(r"cam\s*ket|chinh\s*hang|moi\s*100|\b(?:99|100)\s*%|re\s*nhat|uy\s*tin\s*nhat|\bso\s*1\b|duy\s*nhat"
                      r"|chi\s*con|con\s*duy|het\s*hang|sap\s*het|nhanh\s*tay|mua\s*ngay|hang\s*hiem|dam\s*bao"
                      r"|nhu\s*moi|like\s*new|ton\s*kho|so\s*luong\s*co\s*han|co\s*han\b|keo\s*lo|keo\s*het|nhanh\s*chan"
                      r"|hot\s*deal|\bdeal\b|chot\s*don|con\s*vai|vai\s*may")
_NGUOI_BAN = re.compile(r"\bnguoi\s*ban\b|\bban\s*boi\b")
# tên công nghệ / thương hiệu / thông số chỉ được nhắc khi có trong mô tả thật của sản phẩm (viết không dấu, đã hạ chữ thường)
_TU_KY_THUAT = ("freesync", "g-sync", "gsync", "hdr", "oled", "qled", "hdmi", "displayport", "usb-c", "type-c", "vesa", "pivot",
                "4k", "8k", "2k", "full hd", "fhd", "qhd", "uhd", "wqhd", "ips", "loa", "dell", "lg", "samsung", "asus", "acer",
                "aoc", "gigabyte", "viewsonic", "benq", "lenovo", "apple", "philips", "nvidia", "amd", "intel", "radeon",
                "geforce", "ps5", "xbox", "macbook", "iphone")
_SO = re.compile(r"\d+(?:[.,]\d+)?")
_SO_DON_VI = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ms|hz|inch|gb|tb|nits|fps|k|°)", re.IGNORECASE)   # số đi kèm đơn vị thông số
# số kèm đơn vị thời gian / tiền ("3 tháng", "7 ngày", "ba triệu") = lời hứa hoặc giá, không thuộc thẻ thông số
_SO_TIEN_THOI_GIAN = re.compile(r"\d+(?:[.,]\d+)?\s*(?:thang|nam|ngay|tuan|gio|phut|trieu|tr|cu|nghin|ngan|%)(?![a-z])"
                                r"|\b(?:mot|hai|ba|bon|sau|bay|tam|chin|muoi)\s+(?:thang|ngay|tuan|gio|phut|trieu|nghin|ngan|cu|chuc)\b")
_LINK_NGAN = re.compile(r"\b[a-z0-9][a-z0-9-]*\.(?:gl|ly|do|co|me|to|cc|tk|ml|ga|cf|gq|link|click|page|app|dev|tv|us|ws|vn|com|net"
                        r"|org|info|biz|xyz|shop|store|site|online|top|club)\b")
_CHU_HOA = re.compile(r"\b[A-ZĐ]{3,}\b")
_CHU_HOA_DUOC_PHEP = frozenset({"FPS", "LOL", "PUBG", "FIFA"})   # tên game / từ chung, không phải thông số máy
_TU_CHU = re.compile(r"[a-z]{3,}")
NHAN_TRINH_BAY = frozenset({"man", "thong", "cong", "nghe", "tam", "nen"})   # chữ của nhãn "Mã màn / Thông số / Công nghệ / tấm nền" (không dấu)

HE_THONG = """Bạn là TRƯỞNG PHÒNG NỘI DUNG của shop bán màn hình MSI cũ ở Hà Nội (bán qua Facebook; bình luận vào bài của người đang tìm mua màn hình).
Nhiệm vụ: viết THẺ THÔNG SỐ NGẮN cho bình luận. Khách đọc rất nhanh và hay nghĩ bình luận dài là spam, nên chỉ ghi ĐÚNG 3 thứ: mã màn hình, thông số màn, công nghệ màn. Hệ thống tự ghép MỘT dòng liên hệ ở cuối — bạn KHÔNG viết dòng liên hệ, tên, số điện thoại hay địa chỉ.
Quy tắc bắt buộc:
- KHÔNG lời chào, KHÔNG câu văn, KHÔNG khen, KHÔNG so sánh: chỉ liệt kê. Mỗi bản từ %d đến %d ký tự, tối đa %d dòng, không emoji, không dấu chấm than.
- Phải có mã màn hình đúng như "san_pham.ma_man" (nên ghi cả tên "san_pham.ten") và ít nhất 2 thông số có số (cỡ màn, độ phân giải, Hz, ms…).
- Chỉ dùng thông số và công nghệ có trong "thong_so_co_that", chép đúng như trong đó; không bịa, không nhắc hãng khác.
- KHÔNG viết: giá hay số tiền, bảo hành, tình trạng máy (cũ hay mới), đổi trả, giao hàng, thanh toán, số điện thoại, Zalo, địa chỉ, tên người bán, link, kêu gọi nhắn tin hay inbox, lời cam kết, "chính hãng", "như mới", "rẻ nhất", lời thúc ép.
- Mỗi bản dùng MỘT kiểu trình bày khác nhau (xem "kieu_trinh_bay") và không giống các bản trong "mo_dau_da_co".
Trả lời DUY NHẤT một đối tượng JSON, không thêm chữ nào ngoài JSON: {"mo_dau": ["bản 1", "bản 2"]}""" % (*DO_DAI_MO_DAU, SO_DONG_MO_DAU_TOI_DA)


class LoiMau(ValueError):
    """Không soạn / thêm được mẫu — thông báo tiếng Việt"""


class ThieuSoSuThat(LoiMau):
    """Sổ sự thật chưa điền người bán, SĐT hoặc địa chỉ nên không ghép được dòng liên hệ"""


@dataclass(frozen=True)
class KetQuaSoan:
    san_pham: dict | None = None
    mo_dau: tuple = ()          # các thẻ thông số đã qua kiểm tra
    bi_loai: tuple = ()         # ((chữ, (lý do, ...)), ...)
    nguon: str = ""             # nguồn AI đã trả lời
    ghi_chu: str = ""           # câu cho biên bản họp
    so_mau_nguoi_viet: int = 0
    so_mau_ai_dang_bat: int = 0


# ---------- phần cố định do code ghép ----------
def _ma_may(ten: str) -> str:
    """Mã máy trong tên sản phẩm, vd 'MSI G274QPF E2 27"' -> 'G274QPF'"""
    return next((w for w in re.findall(r"[A-Za-z0-9-]+", ten or "") if len(w) >= 5 and re.search(r"\d", w)
                 and re.search(r"[A-Za-z]", w)), "")


def khung_co_dinh(so: su_that.SuThat) -> str:
    """Phần cuối của bình luận: MỘT dòng liên hệ "Dũng-0902189751-64 Cầu Diễn" (tên gọi - SĐT liền - số nhà + phố) dựng từ sổ sự thật.
    Chủ shop 26/10/2026 bỏ họ tên đầy đủ vì Facebook gợi ý gắn thẻ nhầm người. Dòng có SĐT nên bản không SĐT/địa chỉ
    (products.make_safe) bỏ nguyên dòng này"""
    nguoi_ban, sdt, dia_chi = so.lay("Người bán"), so.lay("Số điện thoại"), so.lay("Địa chỉ")
    thieu = [ten for ten, gia_tri in (("Người bán", nguoi_ban), ("Số điện thoại", sdt), ("Địa chỉ", dia_chi)) if not gia_tri]
    if thieu:
        raise ThieuSoSuThat(f"Sổ sự thật chưa điền: {', '.join(thieu)} — chưa ghép được dòng liên hệ của bình luận")
    dong = noi_dung.lien_he_gon(nguoi_ban, sdt, dia_chi)
    if not dong:
        raise ThieuSoSuThat("Sổ sự thật: Số điện thoại phải có chữ số, Người bán và Địa chỉ không được rỗng — chưa ghép được dòng liên hệ")
    return dong


def lam_sach_mo_dau(chu: str) -> str:
    """Dạng CHUẨN của phần mở đầu: NFKC (ligature / số vòng / chữ toàn chiều rộng thành chữ thường), bỏ mọi ký tự định dạng vô hình
    (zero-width, đảo chiều chữ, thẻ…), \\r\\n thành \\n, bỏ khoảng trắng hai đầu. Chữ được kiểm tra, lưu và đăng đều là dạng này
    — không bao giờ đăng thứ khác với thứ đã kiểm tra"""
    return su_that.lam_sach(chu).replace("\r\n", "\n").strip()


def mo_dau_cua(text: str) -> str:
    """Phần mở đầu (thẻ thông số) của một bình luận do công ty ghép — bỏ dòng liên hệ cuối "Tên-SĐT-địa chỉ" (hoặc phần cuối của các
    khuôn cũ: từ dòng "Người bán:" / "Lưu ý: đây là màn cũ") — để chủ shop đọc lại"""
    chu = text or ""
    m = MOC_PHAN_CUOI.search(chu)
    if m:
        return chu[:m.start()].strip()
    dong = chu.rstrip().splitlines()
    if len(dong) > 1 and DONG_LIEN_HE.match(dong[-1].strip()):
        return "\n".join(dong[:-1]).strip()
    return chu.strip()


def ghep_mau(mo_dau: str, so: su_that.SuThat) -> str:
    """Bình luận đầy đủ = thẻ thông số do AI viết + một dòng liên hệ do code ghép (bản không SĐT tự bỏ nguyên dòng liên hệ)"""
    return f"{lam_sach_mo_dau(mo_dau)}\n{khung_co_dinh(so)}"


# ---------- mẫu do công ty viết: đếm, hạn mức ----------
def _ids_trong_nhat_ky(db: Database, ke_ca_da_hoan_tac: bool) -> set[int]:
    sql = "SELECT doi_tuong FROM nhat_ky_hanh_dong WHERE hanh_dong = ?" + ("" if ke_ca_da_hoan_tac else " AND hoan_tac_luc IS NULL")
    return {i for r in db.query(sql, (THEM_MAU,)) for i in json.loads(r["doi_tuong"])["variant_ids"]}


def mau_ai_dang_bat(db: Database) -> dict[int, int]:
    """{id sản phẩm: số mẫu AI đang bật} — mẫu đã tắt hoặc đã hoàn tác không tính"""
    ids = _ids_trong_nhat_ky(db, ke_ca_da_hoan_tac=False)
    dem: dict[int, int] = {}
    for v in db.variants(active_only=True):
        if v["id"] in ids:
            dem[v["product_id"]] = dem.get(v["product_id"], 0) + 1
    return dem


def da_them_trong_ngay(db: Database, ngay: str) -> int:
    rows = db.query("SELECT doi_tuong FROM nhat_ky_hanh_dong WHERE hanh_dong = ? AND luc LIKE ? AND hoan_tac_luc IS NULL",
                    (THEM_MAU, ngay + "%"))
    return sum(len(json.loads(r["doi_tuong"])["variant_ids"]) for r in rows)


def dang_nghi(db: Database, bay_gio: datetime) -> str:
    """Chủ shop vừa hoàn tác việc thêm mẫu AI thì nghỉ NGAY_NGHI_SAU_HOAN_TAC ngày: trả lý do, rỗng = được làm"""
    tu = (bay_gio - timedelta(days=NGAY_NGHI_SAU_HOAN_TAC)).strftime(DINH_DANG_GIO)
    if db.query("SELECT 1 FROM nhat_ky_hanh_dong WHERE hanh_dong = ? AND hoan_tac_luc >= ? LIMIT 1", (THEM_MAU, tu)):
        return (f"Bạn vừa hoàn tác mẫu AI viết — công ty nghỉ viết mẫu mới {NGAY_NGHI_SAU_HOAN_TAC} ngày "
                "để bạn quyết định có muốn tiếp tục không.")
    return ""


def _mau_nguoi_viet(db: Database, san_pham_id: int) -> list[dict]:
    do_ai = _ids_trong_nhat_ky(db, ke_ca_da_hoan_tac=True)
    return [v for v in db.variants(san_pham_id) if v["id"] not in do_ai]


def _mau_dang_dung(db: Database, san_pham_id: int) -> list[dict]:
    """Mẫu do người viết mà chủ shop đang bật (mẫu cũ dài đã tắt không còn là "thông số thật"); tắt hết thì dùng tất cả mẫu người viết"""
    nguoi_viet = _mau_nguoi_viet(db, san_pham_id)
    return [v for v in nguoi_viet if v["active"]] or nguoi_viet


def chon_san_pham(db: Database) -> dict | None:
    """Sản phẩm đang bật có ÍT mẫu AI nhất và còn chỗ (đã có mẫu do người viết để lấy thông số thật, và tên có mã màn để đối chiếu);
    None nếu hết chỗ"""
    dem = mau_ai_dang_bat(db)
    if sum(dem.values()) >= MAX_MAU_AI_DANG_BAT:
        return None
    ung_vien = [(dem.get(p["id"], 0), p["id"], p) for p in db.products(active_only=True)
                if dem.get(p["id"], 0) < MAX_MAU_AI_MOI_SAN_PHAM and _ma_may(p["name"]) and _mau_nguoi_viet(db, p["id"])]
    return min(ung_vien, key=lambda x: x[:2])[2] if ung_vien else None


def _chi_thong_so(text: str, ten_nguoi_ban: str = "") -> str:
    """Chỉ các dòng thông số của một mẫu: bỏ dòng có SĐT / địa chỉ / Zalo, dòng "Người bán…" và dòng có tên người bán"""
    ten = su_that.bo_dau(ten_nguoi_ban)
    giu = [d for d in (text or "").splitlines() if not products.CONTACT_RE.search(d)
           and not su_that.bo_dau(d).startswith("nguoi ban") and not (ten and ten in su_that.bo_dau(d))]
    return "\n".join(giu).strip()


def thong_so_san_pham(db: Database, san_pham: dict) -> str:
    """Chữ mô tả THẬT của sản phẩm (tên + dòng thông số của các mẫu do người viết đang bật) — thông số trong thẻ AI phải có ở đây"""
    return "\n".join([san_pham["name"], *(_chi_thong_so(v["text"] or "") for v in _mau_dang_dung(db, san_pham["id"]))])


# ---------- rào chắn cho thẻ thông số ----------
def _so_la(chu: str, thong_so: str) -> list[str]:
    """Số từ 2 chữ số trở lên (hoặc có phần thập phân), tên viết hoa ≥3 chữ và tên công nghệ KHÔNG có trong mô tả thật"""
    chuan = lambda s: s.replace(",", ".")                                              # noqa: E731
    co_that = {chuan(x) for x in _SO.findall(thong_so)}
    thong_so_thuong, chu_khong_dau, thong_so_khong_dau = thong_so.lower(), su_that.bo_dau(chu), su_that.bo_dau(thong_so)
    la = [x for x in dict.fromkeys(_SO.findall(chu)) if len(re.sub(r"\D", "", x)) >= 2 and chuan(x) not in co_that]
    for so_, don_vi in dict.fromkeys(_SO_DON_VI.findall(chu)):     # "5ms", "2K": cả số lẫn đơn vị phải có trong mô tả thật
        if not (chuan(so_) in co_that and re.search(rf"\d\s*{re.escape(don_vi)}", thong_so, re.IGNORECASE)):
            la.append(f"{so_}{don_vi}")
    la += [t for t in dict.fromkeys(_CHU_HOA.findall(chu)) if t not in _CHU_HOA_DUOC_PHEP and t.lower() not in thong_so_thuong]
    da_co = {x.lower() for x in la}
    for t in _TU_KY_THUAT:
        mau = rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])"
        if t not in da_co and re.search(mau, chu_khong_dau) and not re.search(mau, thong_so_khong_dau):
            la.append(t)
    return la


def _tu_ngoai_mo_ta(chu: str, thong_so: str) -> list[str]:
    """Chữ (≥3 chữ cái, đã bỏ dấu) KHÔNG nằm trong mô tả thật của sản phẩm và không phải nhãn Mã màn / Thông số / Công nghệ — thẻ thông số
    không có chữ nào ngoài đó, nên AI không viết được câu chào mời hay lời khen"""
    co_that = set(_TU_CHU.findall(su_that.bo_dau(thong_so))) | NHAN_TRINH_BAY
    return list(dict.fromkeys(t for t in _TU_CHU.findall(su_that.bo_dau(chu)) if t not in co_that))


def _giong(chu: str, da_co: list[str]) -> bool:
    """Thẻ giống y hệt phần thông số của một bình luận đã có (bỏ dòng liên hệ và người bán của bình luận đó; có prefilter cho nhanh)"""
    a = su_that.bo_dau(chu)
    for mau in da_co:
        sm = SequenceMatcher(None, a, su_that.bo_dau(_chi_thong_so(mau)), autojunk=False)
        if sm.real_quick_ratio() >= NGUONG_GIONG and sm.quick_ratio() >= NGUONG_GIONG and sm.ratio() >= NGUONG_GIONG:
            return True
    return False


def kiem_tra_mo_dau(mo_dau: str, thong_so: str, da_co: list[str], so: su_that.SuThat, gia_hop_le: frozenset,
                    ma_man: str) -> tuple[str, ...]:
    """Các vấn đề của thẻ thông số do AI viết (rỗng = dùng được). thong_so: mô tả thật của sản phẩm; da_co: các bình luận đã có;
    ma_man: mã màn phải có trong thẻ (vd G274QPF)"""
    chu = lam_sach_mo_dau(mo_dau)
    khong_dau = su_that.bo_dau(chu)
    van_de = []
    if len(chu) < DO_DAI_MO_DAU[0]:
        van_de.append(f"quá ngắn (cần từ {DO_DAI_MO_DAU[0]} ký tự)")
    if len(chu) > DO_DAI_MO_DAU[1] or chu.count("\n") >= SO_DONG_MO_DAU_TOI_DA:
        van_de.append(f"quá dài (tối đa {DO_DAI_MO_DAU[1]} ký tự, {SO_DONG_MO_DAU_TOI_DA} dòng — bình luận phải ngắn gọn)")
    if "{" in chu or "}" in chu:
        van_de.append("không được dùng chỗ trống {…}")
    if any(ord(c) >= 0x2190 for c in chu):
        van_de.append("có emoji hoặc ký hiệu lạ (bot gõ lỗi với emoji)")
    if any(unicodedata.category(c) in ("Cc", "Zl", "Zp") and c != "\n" for c in chu):
        van_de.append("có ký tự điều khiển / ngắt dòng lạ")
    khong_latin = sorted({c for c in chu if c.isalpha() and not unicodedata.name(c, "").startswith("LATIN")})
    if khong_latin:
        van_de.append(f"có ký tự không phải chữ Latin ({', '.join(khong_latin[:5])}) — nghi viết giả chữ để lách kiểm tra")
    if _SO_TIEN_THOI_GIAN.search(khong_dau):
        van_de.append("nhắc con số kèm đơn vị thời gian / tiền (dễ thành lời hứa hay giá không kiểm chứng được)")
    if _LINK_NGAN.search(khong_dau):
        van_de.append("có đường link / tên miền (kể cả link rút gọn)")
    if "!" in chu:
        van_de.append("có dấu chấm than (thẻ thông số không cần)")
    if re.search(r"(?<!\d)(?:\d[ .\-]){8,}\d(?!\d)", chu):       # "0 9 0 2 1 8 9 7 5 1": bộ đánh giá 29/10 thấy kiểu này từng lọt qua
        van_de.append("chữ số viết tách rời từng số (nghi che số điện thoại)")
    if su_that.tim_gia(chu):
        van_de.append("nhắc giá tiền (thẻ thông số không ghi giá)")
    ten_nguoi_ban = su_that.bo_dau(so.lay("Người bán"))
    ten_goi = (so.lay("Người bán").split() or [""])[-1].lower()            # "Dũng" — chính chữ dòng liên hệ cuối sẽ ghi
    if (_NGUOI_BAN.search(khong_dau) or (ten_nguoi_ban and ten_nguoi_ban in khong_dau)
            or (ten_goi and re.search(rf"(?<!\w){re.escape(ten_goi)}(?!\w)", chu.lower()))):
        van_de.append("nhắc người bán (tên gọi do hệ thống ghép ở dòng liên hệ cuối)")
    for mau, nhan in ((_LIEN_HE, "mời liên hệ / nhắn tin / nhắc địa chỉ (hệ thống tự ghép phần liên hệ)"),
                      (_CHINH_SACH, "nhắc bảo hành / đổi trả / giao hàng / thanh toán (thẻ thông số không nói chính sách)"),
                      (_CAM_KET, "có lời cam kết / thúc ép / khoe quá mức không kiểm chứng được")):
        m = mau.search(khong_dau)
        if m:
            van_de.append(f"{nhan}: “{m.group(0)}”")
    if not ma_man:
        van_de.append("tên sản phẩm không có mã màn để đối chiếu")
    elif su_that.bo_dau(ma_man).replace(" ", "") not in re.sub(r"[\s-]", "", khong_dau):
        van_de.append(f"thiếu mã màn {ma_man}")
    con_lai = re.sub(re.escape(ma_man), " ", chu, flags=re.IGNORECASE) if ma_man else chu
    if len(re.findall(r"\S*\d\S*", con_lai)) < 2:
        van_de.append("thiếu thông số (cần mã màn kèm ít nhất 2 thông số có số, ví dụ 27 inch, 180Hz)")
    la = _so_la(chu, thong_so)
    if la:
        van_de.append(f"thông số không có trong mô tả thật của sản phẩm: {', '.join(la)}")
    ngoai = _tu_ngoai_mo_ta(chu, thong_so)
    if ngoai:
        van_de.append(f"có chữ không nằm trong mô tả thật của sản phẩm (thẻ chỉ gồm mã màn, thông số, công nghệ): {', '.join(ngoai[:8])}")
    if _giong(chu, da_co):
        van_de.append("giống y hệt một bình luận đã có (cần cách trình bày khác)")
    van_de += rao_chan.kiem_tra_noi_dung(chu, so, gia_hop_le)
    return tuple(dict.fromkeys(van_de))


# ---------- soạn mẫu bằng AI ----------
def _mo_ta_cho_ai(db: Database, san_pham: dict, so: su_that.SuThat) -> str:
    """Mô tả thông số gửi AI: vài mẫu do người viết đang bật, chỉ giữ dòng thông số — bỏ mọi dòng liên hệ (SĐT, địa chỉ, Zalo…) và
    mọi dòng có tên người bán"""
    ten = so.lay("Người bán")
    doan = [_chi_thong_so(v["text"] or "", ten)[:700] for v in _mau_dang_dung(db, san_pham["id"])[:3]]
    return su_that.lam_sach("\n---\n".join(d for d in doan if d))


def _doc_tra_loi(kq: ai.KetQuaAI | None) -> tuple[list[str], str]:
    """(danh sách chữ AI viết, lý do nếu không đọc được)"""
    if kq is None:
        return [], "AI không trả lời (hết lượt hoặc lỗi mạng)"
    try:
        data = ai.doc_json(kq.van_ban)
    except ValueError:
        return [], "không đọc được câu trả lời của AI (không phải JSON hợp lệ)"
    ds = data.get("mo_dau") if isinstance(data, dict) else None
    chu = [x.strip() for x in ds if isinstance(x, str) and x.strip()] if isinstance(ds, list) else []
    return chu, "" if chu else "AI không viết được thẻ thông số nào"


def soan_mau(db: Database, so: su_that.SuThat, gia_hop_le: frozenset, bo_ai, bay_gio: datetime) -> KetQuaSoan:
    """Nhờ AI viết thêm thẻ thông số cho sản phẩm đang có ít mẫu AI nhất; chỉ giữ bản qua rào chắn. Không đủ điều kiện (hết lượt
    AI, đang nghỉ, hết hạn mức hôm nay, hết chỗ) thì KHÔNG gọi AI"""
    if not bo_ai.con_luot():
        return KetQuaSoan(ghi_chu="Hết lượt AI miễn phí — hôm nay không viết thêm mẫu.")
    nghi = dang_nghi(db, bay_gio)
    if nghi:
        return KetQuaSoan(ghi_chu=nghi)
    con_hom_nay = MAX_MAU_AI_MOI_NGAY - da_them_trong_ngay(db, bay_gio.strftime("%Y-%m-%d"))
    if con_hom_nay <= 0:
        return KetQuaSoan(ghi_chu=f"Hôm nay đã thêm đủ {MAX_MAU_AI_MOI_NGAY} mẫu AI — để mai.")
    san_pham = chon_san_pham(db)
    if san_pham is None:
        return KetQuaSoan(ghi_chu=f"Không còn chỗ cho mẫu AI (tối đa {MAX_MAU_AI_DANG_BAT} mẫu đang bật, "
                                  f"{MAX_MAU_AI_MOI_SAN_PHAM} mẫu mỗi sản phẩm).")
    dem = mau_ai_dang_bat(db)
    xoay, tong_ai = dem.get(san_pham["id"], 0), sum(dem.values())
    so_luong = min(MAX_MO_DAU_MOI_LAN, con_hom_nay, MAX_MAU_AI_MOI_SAN_PHAM - xoay, MAX_MAU_AI_DANG_BAT - tong_ai)
    thong_so, ma_man = thong_so_san_pham(db, san_pham), _ma_may(san_pham["name"])
    da_co = [v["text"] or "" for v in db.variants(san_pham["id"])]
    nguoi_dung = json.dumps({
        "san_pham": {"ten": san_pham["name"], "ma_man": ma_man}, "thong_so_co_that": _mo_ta_cho_ai(db, san_pham, so),
        "mo_dau_da_co": [d.splitlines()[0][:160] for d in map(products.make_safe, da_co[:8]) if d.strip()], "so_luong": so_luong,
        "kieu_trinh_bay": [KIEU_TRINH_BAY[(xoay + i) % len(KIEU_TRINH_BAY)] for i in range(so_luong)]}, ensure_ascii=False)
    kq = bo_ai.hoi(HE_THONG, nguoi_dung, nhan="viet_mau")
    nguon = kq.nguon if kq else ""
    ung_vien, loi = _doc_tra_loi(kq)
    so_nguoi_viet = len(_mau_nguoi_viet(db, san_pham["id"]))
    if loi:
        return KetQuaSoan(san_pham, nguon=nguon, ghi_chu=f"Chưa có mẫu mới cho “{san_pham['name']}”: {loi}.",
                          so_mau_nguoi_viet=so_nguoi_viet, so_mau_ai_dang_bat=tong_ai)
    giu, bi_loai = [], []
    for chu in ung_vien:
        if len(giu) >= so_luong:
            break
        sach = lam_sach_mo_dau(chu)      # kiểm tra và LƯU đúng một dạng chữ
        van_de = kiem_tra_mo_dau(sach, thong_so, [*da_co, *giu], so, gia_hop_le, ma_man)
        if van_de:
            bi_loai.append((chu, van_de))
        else:
            giu.append(sach)
    ghi_chu = f"Đã viết {len(giu)} thẻ thông số mới cho “{san_pham['name']}”"
    if bi_loai:
        ghi_chu += f", loại {len(bi_loai)} bản không đạt: " + " | ".join("; ".join(v[:2]) for _, v in bi_loai[:3])
    return KetQuaSoan(san_pham, tuple(giu), tuple(bi_loai), nguon, ghi_chu + ".", so_nguoi_viet, tong_ai)


def de_xuat_tu_ket_qua(kq: KetQuaSoan, hom_nay: date) -> DeXuat:
    """Đề xuất do CODE dựng từ phần AI đã viết: chữ hiển thị chỉ gồm các thẻ thông số; việc cần làm (tham_so) do code ghi, AI không
    chạm vào. Chủ shop bấm "Đồng ý và làm luôn", hoặc công tắc tự làm sẽ làm khi hết thời gian quan sát"""
    p = kq.san_pham
    bang = "\n".join(f"{i}) {m}" for i, m in enumerate(kq.mo_dau, 1))
    dx = chuan_hoa("noi_dung", {
        "loai": "mau_moi", "tieu_de": f"Thêm {len(kq.mo_dau)} mẫu bình luận ngắn do AI viết cho {p['name']}"[:120],
        "noi_dung": ("Thẻ thông số ngắn do AI viết (hệ thống tự ghép một dòng liên hệ dạng “Tên-SĐT-địa chỉ” của shop "
                     f"ở cuối):\n{bang}"),
        "vi_sao": (f"Sản phẩm này có {kq.so_mau_nguoi_viet} mẫu viết tay; mẫu AI đang bật {kq.so_mau_ai_dang_bat}/"
                   f"{MAX_MAU_AI_DANG_BAT}. Mẫu mới chỉ chiếm phần nhỏ trong tất cả các mẫu nên Facebook từ chối thì tắt được ngay."),
        "ky_vong": "bình luận ngắn gọn, dễ nhớ, đổi cách trình bày để ít bị nhận ra là bình luận lặp lại",
        "rui_ro": "Facebook có thể từ chối mẫu mới; mẫu hay bị từ chối sẽ được đề xuất tắt", "ngay_do": 7}, hom_nay)
    return replace(dx, tham_so=json.dumps({"hanh_dong": THEM_MAU, "san_pham_id": p["id"], "mo_dau": list(kq.mo_dau)},
                                          ensure_ascii=False))


# ---------- thực hiện (hanh_dong.thuc_hien gọi) ----------
def chuan_bi_them_mau(db: Database, du_lieu: dict, so: su_that.SuThat, gia_hop_le: frozenset,
                      bay_gio: datetime) -> tuple[dict, list[str]]:
    """Kiểm tra LẠI mọi thứ ở thời điểm thực hiện (sổ sự thật / hạn mức có thể đã đổi từ lúc đề xuất) rồi trả về (sản phẩm,
    các bình luận đầy đủ sẽ thêm). Sai thì LoiMau và chưa sửa gì"""
    san_pham_id, mo_dau = du_lieu.get("san_pham_id"), du_lieu.get("mo_dau")
    if type(san_pham_id) is not int or not isinstance(mo_dau, list) or not 1 <= len(mo_dau) <= MAX_MO_DAU_MOI_LAN \
            or not all(isinstance(m, str) for m in mo_dau):
        raise LoiMau(f"Việc thêm mẫu phải có sản phẩm và từ 1 đến {MAX_MO_DAU_MOI_LAN} thẻ thông số")
    san_pham = db.get_product(san_pham_id) if 0 < san_pham_id <= MAX_ID else None
    if not san_pham or not san_pham["active"]:
        raise LoiMau("Sản phẩm này không còn (hoặc đang tắt) nên không thêm mẫu được")
    con_ngay = MAX_MAU_AI_MOI_NGAY - da_them_trong_ngay(db, bay_gio.strftime("%Y-%m-%d"))
    dem = mau_ai_dang_bat(db)
    if len(mo_dau) > con_ngay:
        raise LoiMau(f"Hôm nay chỉ còn thêm được {max(con_ngay, 0)} mẫu AI (tối đa {MAX_MAU_AI_MOI_NGAY} mẫu mỗi ngày)")
    if sum(dem.values()) + len(mo_dau) > MAX_MAU_AI_DANG_BAT or dem.get(san_pham_id, 0) + len(mo_dau) > MAX_MAU_AI_MOI_SAN_PHAM:
        raise LoiMau(f"Quá hạn mức mẫu AI đang bật (tối đa {MAX_MAU_AI_DANG_BAT} mẫu, {MAX_MAU_AI_MOI_SAN_PHAM} mẫu mỗi sản phẩm)")
    if not _mau_nguoi_viet(db, san_pham_id):
        raise LoiMau("Sản phẩm chưa có mẫu do người viết nên không có thông số thật để đối chiếu")
    thong_so, ma_man = thong_so_san_pham(db, san_pham), _ma_may(san_pham["name"])
    da_co = [v["text"] or "" for v in db.variants(san_pham_id)]
    day_du, da_xong = [], []
    for chu in mo_dau:
        sach = lam_sach_mo_dau(chu)
        van_de = kiem_tra_mo_dau(sach, thong_so, [*da_co, *da_xong], so, gia_hop_le, ma_man)
        if van_de:
            raise LoiMau(f"Thẻ thông số không đạt kiểm tra: {'; '.join(van_de[:3])}")
        da_xong.append(sach)
        day_du.append(ghep_mau(sach, so))      # ThieuSoSuThat (là LoiMau) nếu sổ sự thật thiếu người bán / SĐT / địa chỉ để ghép dòng liên hệ
    return san_pham, day_du
