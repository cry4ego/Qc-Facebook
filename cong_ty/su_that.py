"""
Sổ sự thật (data/su-that.md) — những điều công ty AI được phép nói về shop. Chủ shop điền một lần; AI KHÔNG được nói gì
ngoài sổ này và bảng Sản phẩm (giá). Giai đoạn 1: đọc sổ + soát các mẫu bình luận hiện có; từ Giai đoạn 2 mọi nội dung
AI viết đều phải qua kiem_tra() trước khi dùng.

Định dạng file: mục "## ..."; dòng "Khóa: giá trị" (chữ ĐIỀN hoặc để trống = chưa điền); dòng "- ..." ở mục giá / mục
cấm; dòng bắt đầu bằng "(" là ghi chú, bị bỏ qua.
"""
import os
import re
import unicodedata
from dataclasses import dataclass

TRUONG = ("Tên shop", "Địa chỉ", "Số điện thoại", "Zalo", "Người bán", "Giờ mở cửa", "Bảo hành", "Đổi trả",
          "Giao hàng", "Thanh toán", "Tình trạng máy")
CHUA_DIEN = "ĐIỀN"
GIA_THAP, GIA_CAO = 100_000, 100_000_000   # khoảng giá màn hình (VND); số ngoài khoảng này không coi là giá

MAU = """# Sổ sự thật của shop

Chủ shop điền file này. Công ty AI CHỈ được nói những gì có ở đây và trong tab Sản phẩm (giá).
Dòng nào còn chữ ĐIỀN là chưa điền. Sửa xong chỉ cần lưu file, không cần khởi động lại.

## Thông tin cửa hàng
Tên shop: ĐIỀN
Địa chỉ: ĐIỀN
Số điện thoại: ĐIỀN
Zalo: ĐIỀN
Người bán: ĐIỀN
Giờ mở cửa: ĐIỀN
(vd: 8h - 20h hằng ngày)

## Chính sách
(Đừng ghi số tài khoản ngân hàng hay số điện thoại khác vào file này: nội dung file được gửi cho AI miễn phí để soạn đề xuất.)
Bảo hành: ĐIỀN
(vd: tháng đầu lỗi 1 đổi 1)
Đổi trả: ĐIỀN
Giao hàng: ĐIỀN
Thanh toán: ĐIỀN
Tình trạng máy: ĐIỀN
(vd: màn cũ đã kiểm tra điểm chết pixel, không trầy xước nặng)

## Giá được phép nhắc thêm
(Giá ngoài tab Sản phẩm mà mẫu bình luận được phép nhắc, mỗi dòng một giá. vd: - 2.900.000đ có chân)

## Không được nói
(Cụm từ AI tuyệt đối không được viết, mỗi dòng một cụm. vd: - miễn phí vận chuyển toàn quốc)
"""

_GIA = re.compile(
    r"(?P<cham>(?<![\d.,])\d{1,3}(?:[.,]\d{3})+(?!\d))"                                 # 2.500.000
    r"|(?P<tr>\d+(?:[.,]\d{1,2})?)\s*(?:triệu|tr)(?P<le>\d{1,3})?(?![a-zà-ỹ])"       # 2tr5, 2,5 triệu
    r"|(?P<k>\d{3,5})\s*k\b"                                                            # 2500k (không lấy "2K" = độ phân giải)
    r"|(?P<tron>(?<![\d.,])\d{6,9}(?![\d.,]))",                                         # 2900000 (gõ liền, không dấu chấm)
    re.IGNORECASE)
_SDT = re.compile(r"(?<![\d+])(?:\+84|0)[ .\-]?(\d{2,3}[ .\-]?\d{3}[ .\-]?\d{3,4})(?!\d)")   # 0902 189 751 / +84 902 189 751
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐️]")


@dataclass(frozen=True)
class SuThat:
    thong_tin: tuple = ()     # ((khóa, giá trị), ...) các mục ĐÃ điền
    chua_dien: tuple = ()     # tên các mục trong TRUONG chưa điền
    gia_them: tuple = ()      # giá (VND) được phép nhắc ngoài bảng Sản phẩm
    cam: tuple = ()           # cụm từ không được viết (chữ thường)
    co_file: bool = False
    loi: str = ""             # file có nhưng không đọc được

    def lay(self, truong: str, mac_dinh: str = "") -> str:
        return dict(self.thong_tin).get(truong, mac_dinh)


def tao_mau_neu_chua_co(duong_dan: str) -> bool:
    """Tạo file mẫu nếu chưa có (không bao giờ ghi đè sổ chủ shop đã điền). True nếu vừa tạo"""
    os.makedirs(os.path.dirname(duong_dan) or ".", exist_ok=True)
    try:
        with open(duong_dan, "x", encoding="utf-8") as f:
            f.write(MAU)
    except FileExistsError:
        return False
    return True


def _che_do(tieu_de: str) -> str:
    chu = tieu_de.lower()
    if "không được nói" in chu:
        return "cam"
    return "gia" if "giá" in chu else "thong_tin"


def _da_dien(gia_tri: str) -> bool:
    return bool(gia_tri) and not gia_tri.upper().startswith(CHUA_DIEN)


def doc(duong_dan: str) -> SuThat:
    """Đọc sổ sự thật. Chưa có file / không đọc được -> coi như mọi mục chưa điền"""
    if not os.path.exists(duong_dan):
        return SuThat(chua_dien=TRUONG)
    try:
        with open(duong_dan, encoding="utf-8-sig") as f:
            dong = f.read().splitlines()
    except (OSError, UnicodeDecodeError) as e:
        return SuThat(chua_dien=TRUONG, loi=f"Không đọc được sổ sự thật: {e}")
    che_do, thong_tin, gia, cam = None, {}, [], []
    for d in (x.strip() for x in dong):
        if not d or d.startswith("(") or (d.startswith("#") and not d.startswith("##")):
            continue
        if d.startswith("##"):
            che_do = _che_do(d.lstrip("#").strip())
        elif che_do == "gia" and d.startswith("-"):
            gia.extend(tim_gia(d))
        elif che_do == "cam" and d.startswith("-"):
            cum = d.lstrip("- ").strip().lower()
            if cum:
                cam.append(cum)
        elif che_do == "thong_tin" and ":" in d:
            khoa, _, gia_tri = d.partition(":")
            if khoa.strip() and _da_dien(gia_tri.strip()):
                thong_tin[khoa.strip()] = gia_tri.strip()
    return SuThat(thong_tin=tuple(thong_tin.items()), chua_dien=tuple(t for t in TRUONG if t not in thong_tin),
                  gia_them=tuple(dict.fromkeys(gia)), cam=tuple(dict.fromkeys(cam)), co_file=True)


def _gia_tu_khop(m: re.Match) -> int:
    if m.group("cham"):
        return int(re.sub(r"[.,]", "", m.group("cham")))
    if m.group("tr"):
        le = int(m.group("le").ljust(3, "0")) * 1000 if m.group("le") else 0   # 2tr6 = 2.600.000
        return round(float(m.group("tr").replace(",", ".")) * 1_000_000) + le
    if m.group("tron"):
        return int(m.group("tron"))
    return int(m.group("k")) * 1000


def tim_gia(text: str) -> list[int]:
    """Các giá (VND) nhắc trong chữ: 2.500.000đ, 2tr5, 2,5 triệu, 2500k, 2900000 — theo thứ tự xuất hiện"""
    sach = _SDT.sub(" ", text or "")   # bỏ số điện thoại trước: "090.218.9751" không phải giá
    gia = (_gia_tu_khop(m) for m in _GIA.finditer(sach))
    return [g for g in gia if GIA_THAP <= g <= GIA_CAO]


def so_dien_thoai(text: str) -> list[str]:
    """Các số điện thoại trong chữ, chuẩn về dạng 0xxxxxxxxx (0902 189 751 và +84 902 189 751 đều thành 0902189751)"""
    so = ("0" + re.sub(r"\D", "", m) for m in _SDT.findall(text or ""))
    return [s for s in so if 10 <= len(s) <= 11]


def gia_hop_le(san_pham) -> frozenset:
    """Giá (VND) được phép nhắc theo bảng Sản phẩm: giá đang bán + giá mua mới"""
    return frozenset(g for p in san_pham for cot in ("price", "new_price") for g in tim_gia(p.get(cot) or ""))


def dinh_dang_gia(gia: int) -> str:
    return f"{gia:,}".replace(",", ".")


def lam_sach(text: str) -> str:
    """NFKC (chữ gõ tổ hợp, số / chữ toàn chiều rộng thành chữ thường) và bỏ ký tự vô hình (zero-width, soft hyphen, BOM…)
    để không thể lách các luật soát bằng cách chèn ký tự lạ"""
    chu = unicodedata.normalize("NFKC", text or "")
    return "".join(c for c in chu if unicodedata.category(c) != "Cf")


def chuan_van_ban(text: str) -> str:
    """lam_sach + gộp mọi khoảng trắng (kể cả NBSP) thành 1 dấu cách + chữ thường — để so sánh"""
    return re.sub(r"\s+", " ", lam_sach(text)).strip().casefold()


def bo_dau(text: str) -> str:
    """chuan_van_ban rồi bỏ dấu tiếng Việt (đ -> d): so sánh không phân biệt dấu / kiểu bỏ dấu"""
    phan_ra = unicodedata.normalize("NFD", chuan_van_ban(text).replace("đ", "d"))
    return "".join(c for c in phan_ra if unicodedata.category(c) != "Mn")


def kiem_tra(text: str, so: SuThat, gia_hop_le_san_pham) -> tuple:
    """Soát 1 đoạn nội dung theo sổ sự thật. Trả về các vấn đề tìm thấy (rỗng = đạt)"""
    text = lam_sach(text)
    van_de = []
    if _EMOJI.search(text):
        van_de.append("có emoji (bot gõ lỗi với emoji)")
    sdt_shop = {s for truong in ("Số điện thoại", "Zalo") for s in so_dien_thoai(so.lay(truong))}
    if sdt_shop:  # chưa điền SĐT thì không có gì để đối chiếu
        van_de += [f"SĐT lạ {s} (không có trong sổ sự thật)" for s in dict.fromkeys(so_dien_thoai(text))
                   if s not in sdt_shop]
    hop_le = set(gia_hop_le_san_pham) | set(so.gia_them)
    van_de += [f"giá {dinh_dang_gia(g)}đ không có trong tab Sản phẩm / sổ sự thật"
               for g in dict.fromkeys(tim_gia(text)) if g not in hop_le]
    khong_dau = bo_dau(text)
    van_de += [f"có cụm bị cấm: “{cum}”" for cum in so.cam if bo_dau(cum) in khong_dau]
    return tuple(van_de)
