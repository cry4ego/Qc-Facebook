"""
Đề xuất của các vai. Mọi đề xuất — kể cả do AI viết, vốn KHÔNG đáng tin — phải qua chuan_hoa() để thành DeXuat bất biến với
kiểu, độ dài và ngày đo hợp lệ; sai thì ValueError (cuộc họp bỏ đề xuất đó và ghi vào biên bản).
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

VAI = ("giam_doc", "phan_tich", "noi_dung", "san_khach", "cham_soc_khach", "rui_ro")
LOAI = ("uu_tien_nhom", "bat_tat_mau", "mau_moi", "bai_dang_moi", "nhom_moi", "thu_nghiem", "kich_ban_tra_loi",
        "thu_thap_so_lieu", "doi_cau_hinh", "khac")
MAX_TIEU_DE, MAX_NOI_DUNG, MAX_VI_SAO, MAX_NGAN = 120, 1500, 500, 300
NGAY_DO_MAC_DINH, NGAY_DO_TOI_DA = 7, 60


@dataclass(frozen=True)
class DeXuat:
    vai: str
    loai: str
    tieu_de: str
    noi_dung: str      # việc cụ thể: văn bản mẫu / tên nhóm / các bước làm
    vi_sao: str        # lý do KÈM SỐ LIỆU thật
    ky_vong: str
    rui_ro: str
    ngay_do: str       # YYYY-MM-DD: ngày đo xem đề xuất có hiệu quả không
    tham_so: str = ""  # JSON việc công ty có thể tự làm — chỉ LUẬT (code) gắn vào; chuan_hoa không bao giờ đọc từ chữ của AI


def _chu(d: dict, khoa: str, ten: str, toi_da: int, bat_buoc: bool = True) -> str:
    gia_tri = d.get(khoa)
    if gia_tri is None or gia_tri == "":
        if bat_buoc:
            raise ValueError(f"{ten} không được để trống")
        return ""
    if not isinstance(gia_tri, str):
        raise ValueError(f"{ten} phải là chữ")
    chu = gia_tri.strip()
    if bat_buoc and not chu:
        raise ValueError(f"{ten} không được để trống")
    if len(chu) > toi_da:
        raise ValueError(f"{ten} dài tối đa {toi_da} ký tự")
    return chu


def _ngay_do(gia_tri, hom_nay: date) -> str:
    """Số ngày tính từ hôm nay (1..60) hoặc ngày YYYY-MM-DD trong 60 ngày tới; trống = 7 ngày sau"""
    chu = "" if gia_tri is None else str(gia_tri).strip()
    if not chu:
        ngay = hom_nay + timedelta(days=NGAY_DO_MAC_DINH)
    elif chu.isascii() and chu.isdigit():
        so = int(chu)
        if not 1 <= so <= NGAY_DO_TOI_DA:
            raise ValueError(f"Ngày đo phải từ 1 đến {NGAY_DO_TOI_DA} ngày tới")
        ngay = hom_nay + timedelta(days=so)
    else:
        try:
            ngay = datetime.strptime(chu, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("Ngày đo phải là số ngày hoặc ngày dạng năm-tháng-ngày") from None
        if not hom_nay < ngay <= hom_nay + timedelta(days=NGAY_DO_TOI_DA):
            raise ValueError(f"Ngày đo phải trong {NGAY_DO_TOI_DA} ngày tới")
    return ngay.strftime("%Y-%m-%d")


def chuan_hoa(vai: str, d: dict, hom_nay: date) -> DeXuat:
    """Kiểm tra + chuẩn hóa 1 đề xuất thô (dict) của vai `vai`; sai thì ValueError với lý do tiếng Việt"""
    if vai not in VAI:
        raise ValueError(f"Vai không hợp lệ: {vai}")
    if not isinstance(d, dict):
        raise ValueError("Đề xuất phải là một đối tượng JSON")
    loai = d.get("loai")
    if loai not in LOAI:
        raise ValueError(f"Loại đề xuất phải là một trong: {', '.join(LOAI)}")
    return DeXuat(vai=vai, loai=loai, tieu_de=_chu(d, "tieu_de", "Tiêu đề", MAX_TIEU_DE),
                  noi_dung=_chu(d, "noi_dung", "Nội dung", MAX_NOI_DUNG), vi_sao=_chu(d, "vi_sao", "Lý do", MAX_VI_SAO),
                  ky_vong=_chu(d, "ky_vong", "Kỳ vọng", MAX_NGAN, bat_buoc=False),
                  rui_ro=_chu(d, "rui_ro", "Rủi ro", MAX_NGAN, bat_buoc=False),
                  ngay_do=_ngay_do(d.get("ngay_do"), hom_nay))
