"""
Viết lại các file bình luận (noi-dung/binh-luan/<mã>.md) thành THẺ NGẮN theo yêu cầu chủ shop 26/10/2026: chữ dài làm khách khó nhớ,
ít chú ý và nghĩ là spam, nên thân bình luận CHỈ có mã màn, thông số màn, công nghệ màn. Một dòng liên hệ cuối "Tên-SĐT-địa chỉ"
(vd Dũng-0902189751-64 Cầu Diễn — 28/10 bỏ họ tên đầy đủ vì Facebook gợi ý gắn thẻ nhầm người) do cau-hinh.json ghép (ket_bl_day_du);
bản không SĐT không có dòng này. Giá và liên hệ đã in sẵn trên ảnh bán hàng đính kèm.

Thông số lấy từ "tom_tat" của từng mẫu màn trong cau-hinh.json (đã đối chiếu trang MSI): các mục ngăn bằng " · ", mục có cỡ màn /
độ phân giải / Hz / ms là THÔNG SỐ, các mục còn lại (tấm nền, HDR, USB-C, loa…) là CÔNG NGHỆ. Mỗi mẫu màn ra 12 bình luận, mỗi bình luận
một kiểu trình bày khác nhau (không có hai bình luận y hệt nhau).

Chạy:     .\\.venv\\Scripts\\python.exe tools\\viet_lai_binh_luan.py ["thư mục nguồn"]      (mặc định "Ảnh Màn-20-10")
Rồi nạp:  .\\.venv\\Scripts\\python.exe main.py noidung ["thư mục nguồn"]                    (mẫu cũ chỉ bị TẮT, không xóa)
Chạy lại nhiều lần cho kết quả giống hệt; file cũ bị ghi đè (sao lưu trước nếu bạn đã sửa tay).
"""
import json
import os
import re
import sys

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GOC)
from modules import noi_dung  # noqa: E402

THU_MUC_NGUON_MAC_DINH = "Ảnh Màn-20-10"
# Mỗi kiểu trình bày = một bình luận của mẫu màn (chỗ trống do the_ngan() điền). Dòng liên hệ cuối chỉ có MỘT dạng nên đa dạng chữ đăng
# lên Facebook chỉ đến từ các kiểu này: giữ ít nhất 12 kiểu (có test)
KIEU_TRINH_BAY = (
    "{ten} – {so_cham} – {cn_cham}",
    "Mã màn: {ten}\nThông số: {so_cham}\nCông nghệ: {cn_cham}",
    "{ten} | {so_dung} | {cn_dung}",
    "{ten} – {so_phay}\nCông nghệ: {cn_phay}",
    "Màn {ten}: {so_phay}, {cn_phay}",
    "{ten}\n{so_cham}\nCông nghệ: {cn_cham}",
    "{ten}: {so_cham} · {cn_cham}",
    "{ten}\nThông số: {so_phay}\nCông nghệ: {cn_phay}",
    "{ten} ({so_phay})\nCông nghệ: {cn_cham}",
    "Mã màn: {ten}\n{so_dung}\n{cn_dung}",
    "{ten} / {so_gach} / {cn_gach}",
    "{ten} – {cn_phay} – {so_phay}",
)
_LA_THONG_SO = re.compile(r'\d\s*"|\b\d+(?:[.,]\d+)?\s*(?:inch|hz|ms)\b|\b[248]k\b|full\s*hd|\bqhd\b|\buhd\b', re.IGNORECASE)
_DAU_FILE = """# Bình luận – {ten}

<!--
Quy ước (đọc trước khi sửa):
- File này do công cụ tools/viet_lai_binh_luan.py TẠO RA từ "tom_tat" trong cau-hinh.json. Muốn đổi thông số thì sửa "tom_tat" rồi chạy
  lại công cụ (sửa tay ở đây sẽ bị ghi đè khi chạy lại).
- Mỗi bình luận bắt đầu bằng dòng "## MÃ" (ví dụ ## {tien_to}-01). Thân CHỈ gồm mã màn, thông số, công nghệ: ngắn để khách dễ nhớ,
  không bị coi là spam.
- Dòng liên hệ cuối "Tên-SĐT-địa chỉ" (vd Dũng-0902189751-64 Cầu Diễn) do cau-hinh.json tự ghép (ket_bl_day_du = {{lien_he}}); bản không
  SĐT không có dòng này (ket_bl_chi_ten rỗng). KHÔNG ghi họ tên đầy đủ (Facebook gợi ý gắn thẻ nhầm người), giá, bảo hành, tình trạng
  máy: giá và liên hệ đã in sẵn trên ảnh bán hàng.
- Thông số lấy từ trang MSI: {nguon}
-->
"""


def tach_tom_tat(tom_tat: str, ten: str = "") -> tuple[list[str], list[str]]:
    """('27" 2K · Rapid IPS · 240Hz · 1ms · HDR 400') -> (['27" 2K', '240Hz', '1ms'], ['Rapid IPS', 'HDR 400']). Thiếu thông số
    hoặc thiếu công nghệ thì ValueError (kèm tên mẫu màn) vì không dựng được thẻ"""
    phan = [p.strip() for p in (tom_tat or "").split("·") if p.strip()]
    thong_so = [p for p in phan if _LA_THONG_SO.search(p)]
    cong_nghe = [p for p in phan if p not in thong_so]
    if not thong_so or not cong_nghe:
        raise ValueError(f"{ten or 'Mẫu màn'}: \"tom_tat\" phải có cả thông số (cỡ màn, độ phân giải, Hz, ms) lẫn công nghệ "
                         f"(tấm nền, HDR, USB-C…), các mục ngăn bằng “ · ”: {tom_tat!r}")
    return thong_so, cong_nghe


def the_ngan(ten: str, thong_so: list[str], cong_nghe: list[str], kieu: int) -> str:
    """Thẻ ngắn kiểu số `kieu` (xoay vòng qua KIEU_TRINH_BAY): mã màn + thông số + công nghệ, không gì khác"""
    gia_tri = {"ten": ten,
               "so_cham": " · ".join(thong_so), "so_dung": " | ".join(thong_so), "so_phay": ", ".join(thong_so),
               "so_gach": " / ".join(thong_so),
               "cn_cham": " · ".join(cong_nghe), "cn_dung": " | ".join(cong_nghe), "cn_phay": ", ".join(cong_nghe),
               "cn_gach": " / ".join(cong_nghe)}
    return KIEU_TRINH_BAY[kieu % len(KIEU_TRINH_BAY)].format(**gia_tri)


def tien_to_ma(duong_dan: str, ma: str) -> str:
    """Tiền tố mã bình luận: giữ tiền tố đang dùng trong file cũ (## QPX-01 -> QPX), chưa có file thì lấy 4 ký tự đầu của mã mẫu màn"""
    if os.path.exists(duong_dan):
        with open(duong_dan, encoding="utf-8") as f:
            m = re.search(r"^## ([A-Za-z0-9]+)-\d+", f.read(), re.MULTILINE)
        if m:
            return m.group(1)
    return re.sub(r"[^A-Z0-9]", "", ma.upper())[:4]


def viet_file(sp: dict, tien_to: str) -> str:
    """Nội dung file .md của một mẫu màn: mỗi kiểu trình bày một thẻ ngắn, mã ## <tiền tố>-01, -02, …"""
    thong_so, cong_nghe = tach_tom_tat(sp.get("tom_tat", ""), sp["ten"])
    dau = _DAU_FILE.format(ten=sp["ten"], tien_to=tien_to, nguon=(sp.get("nguon") or ["(chưa ghi)"])[0])
    khoi = [f"## {tien_to}-{i:02d}\n{the_ngan(sp['ten'], thong_so, cong_nghe, i - 1)}\n" for i in range(1, len(KIEU_TRINH_BAY) + 1)]
    return dau + "\n" + "\n".join(khoi)


def chay(thu_muc_noi_dung: str) -> list[tuple[str, int]]:
    """Viết lại binh-luan/<mã>.md của mọi mẫu màn trong <thu_muc_noi_dung>/cau-hinh.json. Dựng hết trước, đủ rồi mới ghi: mẫu màn nào
    lỗi thì không ghi file nào. Trả về [(mã mẫu màn, số bình luận)]"""
    with open(os.path.join(thu_muc_noi_dung, "cau-hinh.json"), encoding="utf-8") as f:
        cau_hinh = json.load(f)
    thu_muc_bl = os.path.join(thu_muc_noi_dung, "binh-luan")
    ket_qua = []
    for sp in cau_hinh["san_pham"]:
        duong_dan = os.path.join(thu_muc_bl, f"{sp['ma']}.md")
        ket_qua.append((duong_dan, sp["ma"], viet_file(sp, tien_to_ma(duong_dan, sp["ma"]))))
    os.makedirs(thu_muc_bl, exist_ok=True)
    for duong_dan, _, noi in ket_qua:
        with open(duong_dan, "w", encoding="utf-8", newline="\n") as f:
            f.write(noi)
    return [(ma, len(noi_dung.parse_md(noi))) for _, ma, noi in ket_qua]


def main(argv: list[str]) -> int:
    nguon = argv[0] if argv else os.path.join(GOC, THU_MUC_NGUON_MAC_DINH)
    thu_muc = os.path.join(nguon, "noi-dung") if os.path.isdir(os.path.join(nguon, "noi-dung")) else nguon
    if not os.path.exists(os.path.join(thu_muc, "cau-hinh.json")):
        print(f"Không thấy cau-hinh.json trong {thu_muc}")
        return 1
    try:
        ket_qua = chay(thu_muc)
    except ValueError as e:
        print(f"LỖI: {e}")
        return 1
    for ma, so in ket_qua:
        print(f"  ✓ {ma}: {so} bình luận ngắn")
    ten_nguon = os.path.basename(os.path.normpath(nguon))
    print(f'Xong. Bước tiếp theo: .\\.venv\\Scripts\\python.exe main.py noidung "{ten_nguon}"')
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
