"""
Kiểm soát rủi ro — chốt chặn bằng CODE, không bằng AI (AI có thể bị dẫn dắt hoặc bịa). Mọi đề xuất phải qua kiem_tra() trước
khi tới tay chủ shop; có bất kỳ vấn đề nào thì đề xuất bị chặn (quyền phủ quyết). Các luật tương ứng "bậc 3 — cấm cứng" và
"không bịa" trong Cong-Ty-AI.md:
- đề xuất của AI phải dẫn SỐ LIỆU có thật trong báo cáo và không được nêu số lớn không có trong báo cáo;
- cấm đụng tới giá / khuyến mãi, nhắn tin chủ động cho người lạ, tăng trần bình luận, quảng cáo trả phí, tài khoản phụ /
  mật khẩu, xóa dữ liệu; chỉ được GIẢM các thông số bình luận, không đổi các thông số an toàn khác;
- nội dung viết ra (mẫu bình luận, bài đăng, kịch bản trả lời) phải khớp sổ sự thật, không hứa bảo hành ngoài sổ, không có
  số điện thoại hay đường link (hệ thống tự thêm SĐT của shop), chỉ dùng chỗ trống {giá} {giá_mới} {tiết_kiệm};
- nhóm mới chỉ là nhóm màn hình ở Hà Nội; tiếng Việt phải có dấu.

Mọi luật so khớp trên chữ ĐÃ CHUẨN HÓA (su_that.bo_dau: NFKC, bỏ ký tự vô hình, gộp khoảng trắng, chữ thường, bỏ dấu) và
quét TẤT CẢ các trường chữ của đề xuất, để không lách được bằng dấu cách lạ, ký tự vô hình, bỏ dấu hay đổi kiểu bỏ dấu.
"""
import json
import re

from cong_ty import su_that
from cong_ty.de_xuat import DeXuat

NOI_DUNG_CAN_SOAT = ("mau_moi", "bai_dang_moi", "kich_ban_tra_loi", "thu_nghiem")   # loại có chữ sẽ được gửi ra ngoài
NGUON_KHONG_CAN_SO_LIEU = ("luat", "mau_ai", "tu_khoa_ai")   # đề xuất do code dựng: không bắt chứng minh số liệu như đề xuất AI tự viết
SO_TOI_THIEU_LAM_BANG_CHUNG = 2      # số 0, 1 ai cũng "trùng" nên không tính là dẫn số liệu
SO_LON_PHAI_CO_THAT = 10             # số từ ngần này trở lên đã nêu thì BẮT BUỘC có trong báo cáo (chống bịa số)
MAU_MOI_BAI_TOI_DA = 3               # AI chỉ được đề xuất đặt COMMENT_PRODUCTS_PER_POST từ ngần này trở xuống

NHAN_GIA = "đụng tới giá / khuyến mãi (cấm cứng: AI không được đổi giá hay hứa ưu đãi)"
# Các mẫu dưới đây áp lên chữ ĐÃ BỎ DẤU nên viết không dấu
CAM_CUNG = (
    (NHAN_GIA,
     r"\b(?:giam|tang|doi|ha|nang|thay|bot|dieu\s*chinh)\s+gia\b(?!\s*tri)|\bgia\s+(?:giam|ha|khuyen\s*mai|soc)\b"
     r"|khuyen\s*mai|uu\s*dai|\bsale\b|chiet\s*khau|\bvoucher\b|\bcoupon\b|mien\s*phi|\bgiam\s+(?:con|xuong)\s+\d"
     r"|\bgiam\s+\d+(?:[.,]\d+)?\s*%\s*(?:gia|cho\s+khach|tien)"),
    ("nhắn riêng cho người lạ (cấm cứng)",
     r"chu\s*dong\s+(?:nhan|inbox|gui\s+tin|goi|lien\s*he)"
     r"|(?:nhan\s*tin|inbox|gui\s*tin|lien\s*he|nhan)\s+(?:truc\s*tiep\s+)?(?:cho\s+)?"
     r"(?:nguoi\s+(?:dang|viet|la|mua|can)|chu\s+bai|khach\s+(?:la|chua\s+biet))"
     r"|inbox\s+truc\s*tiep|inbox\s+hang\s*loat|nhan\s*tin\s+hang\s*loat"),
    ("tăng trần / vượt giới hạn bình luận (cấm cứng)",
     r"\b(?:tang|nang|bo|go|noi)\s+(?:tran|gioi\s*han)|vuot\s+(?:tran|gioi\s*han)|khong\s+gioi\s*han"
     r"|\btang\s+(?:so\s+)?binh\s*luan\b"),
    ("quảng cáo trả phí / chi tiền (cấm cứng)",
     r"quang\s*cao\s*tra\s*phi|\bchay\s+(?:ads|quang\s*cao)|facebook\s*ads|\bads\b|sponsor|\bboost|chi\s+tien"
     r"|ngan\s*sach\s+quang\s*cao"),
    ("động tới tài khoản / mật khẩu / nhiều nick (cấm cứng)",
     r"mat\s*khau|\bpassword\b|\b(?:nick|tai\s*khoan)\s*(?:phu|clone|ao|gia|thu\s*hai|thu\s*2)\b"
     r"|tai\s*khoan\s+(?:khac|them|moi)|mo\s+them\s+(?:tai\s*khoan|nick)|doi\s+tai\s*khoan"
     r"|nhieu\s+(?:tai\s*khoan|nick)|\bclone\b"),
    ("xóa dữ liệu (cấm cứng)",
     r"\b(?:xoa|reset|don(?:\s*sach)?|lam\s*sach)\s+(?:du\s*lieu|csdl|database|db|nhat\s*k[yi]|lich\s*su|toan\s*bo|tat\s*ca)\b"),
)
_CAM_CUNG = tuple((nhan, re.compile(mau)) for nhan, mau in CAM_CUNG)
_TANG_QUA = re.compile(r"\btặng\b")   # trên chữ CÓ dấu: "tặng" (cho quà) khác "tăng" (nhiều lên) — bỏ dấu thì lẫn nhau
_BAO_HANH_SO = re.compile(r"bao\s*hanh\D{0,12}?(\d+)\s*(thang|nam)\b")
_BAO_HANH_CHU = re.compile(r"bao\s*hanh\D{0,12}?(?:mot|hai|ba)\s+nam\b|bao\s*hanh\s+(?:vinh\s*vien|tron\s*doi|suot\s*doi)")
_SO_THANG = re.compile(r"(\d+)\s*(thang|nam)\b")
_NHOM_KHONG_PHAI = re.compile(r"\b(?:laptop|pc|linh\s*kien|vga|ssd|cpu|macbook|dien\s*thoai)\b")
_CAU_HINH = re.compile(r"\b(MAX_COMMENTED_POSTS_PER_DAY|COMMENT_PRODUCTS_PER_POST|BLOCK_COOLDOWN_HOURS|COMMENT_GAP_MIN"
                       r"|COMMENT_GAP_MAX|MIN_DELAY|MAX_DELAY|JOIN_PER_DAY|MAX_POST_AGE_MINUTES)\b\D{0,15}?(\d+)")
_LINK = re.compile(r"https?://|\bwww\.|\b[a-z0-9][a-z0-9-]*\.(?:com|vn|net|org|me|link|ly|io|info|biz|xyz|shop|store|site)\b",
                   re.IGNORECASE)
_NGAY = re.compile(r"\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2})?|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
_KHOA_KHONG_PHAI_SO_LIEU = frozenset({"id", "ngay", "hom_nay", "so_ngay", "tran", "tu", "den", "van_ban", "group_url", "ten",
                                      "chua_het", "nhom_quet"})
_SO = re.compile(r"\d+(?:[.,]\d+)*")
_CHO_TRONG = re.compile(r"\{[^{}]*\}")
CHO_TRONG_HOP_LE = ("{giá}", "{giá_mới}", "{tiết_kiệm}")   # chỗ trống modules/products.fill_price điền được
_CHU_CO_DAU = frozenset("àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ")
# từ tiếng Việt thường gặp khi bị viết không dấu; thấy từ 3 từ khác nhau trở lên mà không có chữ có dấu nào = viết không dấu
_TU_KHONG_DAU = frozenset("khong nhom bai gia cua duoc nhung va la co cho mau binh luan man hinh ban shop khach quet lan "
                          "trong voi nay mot nguoi can mua tim".split())
SO_TU_KHONG_DAU_TOI_THIEU = 3


def so_trong_chu(text: str) -> set[float]:
    """Các số trong chữ, hiểu cách viết Việt Nam: 1.262 = một nghìn hai trăm sáu mươi hai, 4,8 = bốn phẩy tám"""
    ket_qua = set()
    for t in _SO.findall(text or ""):
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", t):
            ket_qua.add(float(re.sub(r"[.,]", "", t)))
            continue
        try:
            ket_qua.add(float(t.replace(",", ".")))
        except ValueError:      # "1.2.3" không phải số
            continue
    return ket_qua


def _tat_ca_chu(dx: DeXuat) -> str:
    return "\n".join((dx.tieu_de, dx.noi_dung, dx.vi_sao, dx.ky_vong, dx.rui_ro))


def _so_trong_bao_cao(bc: dict) -> set[float]:
    """Mọi số THẬT trong báo cáo: các giá trị số và số nằm trong câu chữ của báo cáo; bỏ id, ngày, tên nhóm, bản chữ dài và
    các số "khung" (số ngày của kỳ báo cáo, trần bình luận) vì ai cũng có thể viết trùng"""
    ket_qua: set[float] = set()

    def di(gia_tri, khoa: str = "") -> None:
        if khoa in _KHOA_KHONG_PHAI_SO_LIEU or isinstance(gia_tri, bool):
            return
        if isinstance(gia_tri, (int, float)):
            ket_qua.add(round(float(gia_tri), 1))
        elif isinstance(gia_tri, str):
            ket_qua.update(round(x, 1) for x in so_trong_chu(_NGAY.sub(" ", gia_tri)))
        elif isinstance(gia_tri, dict):
            for k, v in gia_tri.items():
                di(v, k)
        elif isinstance(gia_tri, (list, tuple)):
            for v in gia_tri:
                di(v, khoa)

    di(bc)
    return ket_qua - {round(float(bc["so_ngay"]), 1), round(float(bc["rui_ro"]["tran"]), 1)}


def _dang_so(x: float) -> str:
    return f"{x:g}"


def _thieu_so_lieu(dx: DeXuat, bc: dict) -> list[str]:
    da_dan = {round(x, 1) for x in so_trong_chu(_NGAY.sub(" ", su_that.lam_sach(dx.vi_sao)))}
    co_that = _so_trong_bao_cao(bc)
    van_de = []
    if not {x for x in da_dan if x >= SO_TOI_THIEU_LAM_BANG_CHUNG} & co_that:
        van_de.append("không dẫn số liệu nào có trong báo cáo (đề xuất phải kèm số liệu thật)")
    bia = sorted(x for x in da_dan if x >= SO_LON_PHAI_CO_THAT and x not in co_that)
    if bia:
        van_de.append(f"nêu số liệu không có trong báo cáo: {', '.join(_dang_so(x) for x in bia)}")
    return van_de


def _cam_cung(dx: DeXuat) -> list[str]:
    chu = _tat_ca_chu(dx)
    van_de = [nhan for nhan, mau in _CAM_CUNG if mau.search(su_that.bo_dau(chu))]
    if _TANG_QUA.search(su_that.chuan_van_ban(chu)) and NHAN_GIA not in van_de:
        van_de.append(NHAN_GIA)
    return van_de


def _cau_hinh(dx: DeXuat, bc: dict) -> list[str]:
    """Chỉ được đề xuất GIẢM số bình luận; mọi thông số an toàn khác (nghỉ, khoảng cách, tham gia nhóm…) cấm đổi"""
    tran = bc["rui_ro"]["tran"]
    van_de = []
    for khoa, so in _CAU_HINH.findall(su_that.lam_sach(_tat_ca_chu(dx))):
        v = int(so)
        if khoa == "MAX_COMMENTED_POSTS_PER_DAY":
            duoc = v >= 1 and (tran <= 0 or v <= tran)
        elif khoa == "COMMENT_PRODUCTS_PER_POST":
            duoc = 1 <= v <= MAU_MOI_BAI_TOI_DA
        else:
            duoc = False
        if not duoc:
            van_de.append(f"đổi thông số an toàn {khoa} thành {v} (AI chỉ được đề xuất giảm số bình luận)")
    return van_de


def _bao_hanh(dx: DeXuat, so: su_that.SuThat) -> list[str]:
    """Hứa bảo hành (số tháng / năm, "vĩnh viễn"…) nào không có trong mục Bảo hành của sổ sự thật đều bị chặn"""
    trong_so = su_that.bo_dau(so.lay("Bảo hành"))
    duoc_phep = set(_SO_THANG.findall(trong_so))
    chu = su_that.bo_dau(f"{dx.tieu_de}\n{dx.noi_dung}")
    hua = [f"{n} {don_vi}" for n, don_vi in _BAO_HANH_SO.findall(chu) if (n, don_vi) not in duoc_phep]
    hua += [m.group(0) for m in _BAO_HANH_CHU.finditer(chu) if m.group(0) not in trong_so]
    return [f"hứa bảo hành “{h}” không có trong sổ sự thật" for h in dict.fromkeys(hua)]


def thieu_dau(text: str) -> bool:
    """Chữ tiếng Việt bị viết KHÔNG DẤU? (không có chữ có dấu nào mà lại có nhiều từ Việt thông dụng không dấu)"""
    chu = su_that.chuan_van_ban(text)
    if any(c in _CHU_CO_DAU for c in chu):
        return False
    return len(set(re.findall(r"[a-z]+", chu)) & _TU_KHONG_DAU) >= SO_TU_KHONG_DAU_TOI_THIEU


def _viet_khong_dau(dx: DeXuat) -> list[str]:
    return [f"{ten} viết tiếng Việt không dấu (phải có dấu đầy đủ)"
            for ten, chu in (("tiêu đề", dx.tieu_de), ("nội dung", dx.noi_dung), ("lý do", dx.vi_sao)) if thieu_dau(chu)]


def _noi_dung_gui_ra(dx: DeXuat, so: su_that.SuThat, gia_hop_le: frozenset) -> list[str]:
    """Chữ sẽ được chủ shop dán ra ngoài: khớp sổ sự thật, đúng chỗ trống, và KHÔNG có SĐT / link (hệ thống tự thêm SĐT)"""
    chu = su_that.lam_sach(dx.noi_dung)
    van_de = list(su_that.kiem_tra(dx.noi_dung, so, gia_hop_le))
    sai = [c for c in _CHO_TRONG.findall(chu) if c not in CHO_TRONG_HOP_LE]
    if sai:
        van_de.append(f"chỗ trống không hợp lệ {', '.join(dict.fromkeys(sai))} (chỉ có {', '.join(CHO_TRONG_HOP_LE)})")
    if su_that.so_dien_thoai(chu):
        van_de.append("nội dung không được viết số điện thoại (hệ thống tự thêm số của shop vào bình luận)")
    if _LINK.search(chu):
        van_de.append("nội dung không được chèn đường link")
    return van_de


def _nhom_moi(dx: DeXuat) -> list[str]:
    chu = su_that.bo_dau(f"{dx.tieu_de} {dx.noi_dung}")
    if _NHOM_KHONG_PHAI.search(chu):
        return ["nhóm mới phải là nhóm màn hình ở Hà Nội, không phải nhóm PC / laptop / linh kiện"]
    if re.search(r"man\s*hinh", chu) and re.search(r"ha\s*noi|hanoi|\bhn\b", chu):
        return []
    return ["nhóm mới phải là nhóm màn hình ở Hà Nội (hướng chủ shop đã chốt)"]


def kiem_tra_noi_dung(chu: str, so: su_that.SuThat, gia_hop_le: frozenset) -> tuple[str, ...]:
    """Soát MỘT đoạn chữ sẽ được đăng ra ngoài (vd phần mở đầu bình luận do AI viết) bằng đúng các luật cấm cứng của đề xuất
    nội dung: không đụng giá / khuyến mãi, không hứa bảo hành ngoài sổ, tiếng Việt có dấu, khớp sổ sự thật, đúng chỗ trống,
    không SĐT / link"""
    dx = DeXuat(vai="noi_dung", loai="mau_moi", tieu_de="", noi_dung=chu, vi_sao="", ky_vong="", rui_ro="", ngay_do="")
    van_de = [*_cam_cung(dx), *_bao_hanh(dx, so), *_viet_khong_dau(dx), *_noi_dung_gui_ra(dx, so, gia_hop_le)]
    return tuple(dict.fromkeys(van_de))


def kiem_tra(dx: DeXuat, bc: dict, so: su_that.SuThat, gia_hop_le: frozenset, nguon: str = "ai") -> tuple[str, ...]:
    """Các vấn đề của đề xuất (rỗng = qua). bc: báo cáo sáng; so: sổ sự thật; gia_hop_le: giá trong tab Sản phẩm.
    nguon='luat' / 'mau_ai': đề xuất do code dựng (thẳng từ báo cáo / từ chữ AI đã qua mau_ai.kiem_tra_mo_dau) nên không cần
    chứng minh số liệu; mọi luật còn lại vẫn áp dụng"""
    van_de = [*_cam_cung(dx), *_cau_hinh(dx, bc), *_bao_hanh(dx, so), *_viet_khong_dau(dx)]
    if nguon not in NGUON_KHONG_CAN_SO_LIEU:
        van_de = [*_thieu_so_lieu(dx, bc), *van_de]
    if dx.loai in NOI_DUNG_CAN_SOAT:
        van_de += _noi_dung_gui_ra(dx, so, gia_hop_le)
    if dx.loai == "nhom_moi":
        van_de += _nhom_moi(dx)
    return tuple(dict.fromkeys(van_de))
