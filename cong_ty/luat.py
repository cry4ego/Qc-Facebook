"""
Đề xuất theo LUẬT: sinh thẳng từ báo cáo sáng bằng code, không cần AI — nên cuộc họp vẫn có việc để bàn khi hết lượt AI.
Mỗi đề xuất dẫn các con số lấy từ chính báo cáo (rào chắn kiểm tra điều đó) và đi qua Kiểm soát rủi ro như đề xuất của AI.
Thứ tự hàm trong de_xuat_theo_luat() cũng là thứ tự ưu tiên khi chỉ chọn được vài đề xuất.
"""
import json
from dataclasses import replace
from datetime import date

from cong_ty import bao_cao, hanh_dong, su_that
from cong_ty.de_xuat import DeXuat, chuan_hoa

TOI_DA_NHOM_NEU_TEN = 5
TU_KHOA_NHOM_MOI = "màn hình cũ Hà Nội, thanh lý màn hình Hà Nội, chợ màn hình Hà Nội"


def _so(x: float) -> str:
    return f"{round(x):,}".replace(",", ".")


def _dx(vai: str, loai: str, tieu_de: str, noi_dung: str, vi_sao: str, ky_vong: str, rui_ro: str,
        hom_nay: date) -> DeXuat:
    return chuan_hoa(vai, {"loai": loai, "tieu_de": tieu_de, "noi_dung": noi_dung, "vi_sao": vi_sao, "ky_vong": ky_vong,
                           "rui_ro": rui_ro, "ngay_do": 7}, hom_nay)


def _nhom_vo_ich(bc: dict, hom_nay: date) -> list[DeXuat]:
    vo_ich = bc["vo_ich"]
    if not vo_ich:
        return []
    ten = ", ".join(r["ten"] for r in vo_ich[:TOI_DA_NHOM_NEU_TEN])
    nhieu_nhat = vo_ich[0]
    return [_dx("san_khach", "uu_tien_nhom", "Giảm ưu tiên các nhóm quét nhiều mà không ra bài",
                f"Giảm ưu tiên (quét thưa hơn) các nhóm: {ten}",
                f"{len(vo_ich)} nhóm quét từ {bao_cao.MIN_QUET_KET_LUAN} lần trong {bc['so_ngay']} ngày mà 0 bài đạt lọc, "
                f"0 khách; nhiều nhất là {nhieu_nhat['ten']} với {nhieu_nhat['quet']} lần quét",
                "đỡ tốn lượt quét, dồn sức cho nhóm có khách", "có thể bỏ lỡ bài hiếm ở các nhóm này", hom_nay)]


def _mau_hay_bi_chan(bc: dict, hom_nay: date) -> list[DeXuat]:
    xau = [m for m in bc["mau"]["thong_ke"] if m["bat"] and bao_cao.mau_hay_bi_chan(m)][:hanh_dong.MAX_MAU_MOI_LAN]
    if not xau:
        return []
    ids = ", ".join(f"#{m['id']}" for m in xau)
    chi_tiet = "; ".join(f"mẫu #{m['id']}: {m['da_gui'] + m['bi_tu_choi']} bình luận, {m['bi_tu_choi']} bị chặn / từ chối"
                         for m in xau[:3])
    dx = _dx("noi_dung", "bat_tat_mau", f"Tắt các mẫu bình luận hay bị chặn ({ids})",
             f"Tắt mẫu {ids} ở tab Sản phẩm (bỏ tick), rồi viết lại cho nhẹ nhàng hơn nếu muốn dùng lại",
             f"{chi_tiet}", "giảm bình luận bị Facebook từ chối, giảm nguy cơ bị chặn tài khoản",
             "bớt đa dạng mẫu bình luận", hom_nay)
    # việc ghi trong chữ = việc công ty sẽ làm nếu bạn bấm "Đồng ý và làm luôn" (tắt, không xóa; hoàn tác được)
    return [replace(dx, tham_so=json.dumps({"hanh_dong": hanh_dong.TAT_MAU, "variant_ids": [m["id"] for m in xau]}))]


def _thieu_khach(bc: dict, hom_nay: date) -> list[DeXuat]:
    if bc["khach"]["co_so_lieu"]:
        return []
    p = bc["pheu"]
    return [_dx("cham_soc_khach", "thu_thap_so_lieu", "Ghi khách gọi / nhắn / mua mỗi tối",
                "Mỗi tối vào tab Công ty AI, mục Ghi kết quả khách, ghi số khách gọi / nhắn / mua "
                "(kèm tên nhóm nếu biết khách thấy shop ở đâu)",
                f"Chưa có lượt khách nào trong {bc['so_ngay']} ngày trong khi đã bình luận {p['bai_binh_luan']} bài "
                f"({p['binh_luan_gui']} bình luận) — chưa đo được nhóm nào ra khách",
                "biết nhóm và mẫu nào ra khách để dồn sức", "mất khoảng 1 phút mỗi tối", hom_nay)]


def _nguon_khach_giam(bc: dict, hom_nay: date) -> list[DeXuat]:
    cd = bc["chan_doan"]
    if cd["trang_thai"] != "giam" or not cd["goc"]:
        return []
    nen, gan = cd["nen"], cd["gan"]
    if cd["goc"] in ("bai_thay", "bai_mua"):
        return [_dx("san_khach", "nhom_moi", "Tìm thêm nhóm màn hình Hà Nội để bù nguồn khách giảm",
                    "Tìm và tham gia thêm nhóm Facebook mua bán màn hình máy tính cũ ở Hà Nội "
                    f"(từ khóa: {TU_KHOA_NHOM_MOI})",
                    f"bài MUA giảm {_so(nen['bai_mua'])} → {_so(gan['bai_mua'])} bài/ngày, bài bình luận giảm "
                    f"{cd['giam_pct']}% trong khi bot vẫn quét {_so(gan['quet'])} lần/ngày",
                    "thêm nguồn bài người cần mua", "nhóm mới có thể ít khách thật", hom_nay)]
    if cd["goc"] == "quet":
        return [_dx("phan_tich", "khac", "Kiểm tra vì sao bot quét ít hơn",
                    "Mở các cửa sổ QC-Facebook (bình luận, quét) xem còn chạy không; xem nhật ký lỗi ở tab Bình luận",
                    f"số lần quét giảm {_so(nen['quet'])} → {_so(gan['quet'])}/ngày, kéo theo bài bình luận giảm "
                    f"{cd['giam_pct']}%", "bot quét lại đầy đủ", "không có", hom_nay)]
    return [_dx("phan_tich", "khac", "Xem lại bộ lọc: tỷ lệ bài MUA đạt lọc giảm",
                "Xem lý do bỏ qua ở tab Phân loại bài, kiểm tra bộ lọc khu vực và chủ đề có chặn quá tay không",
                f"tỷ lệ bài MUA đạt lọc giảm {round(nen['ty_le_dat'] * 100)}% → {round(gan['ty_le_dat'] * 100)}%, "
                f"bài bình luận giảm {cd['giam_pct']}%", "nhận thêm bài đúng khách", "nới lọc có thể thêm bài sai khách",
                hom_nay)]


def _bo_so_dien_thoai(bc: dict, hom_nay: date) -> list[DeXuat]:
    if not bc["rui_ro"]["safe_all"]:
        return []
    p = bc["pheu"]
    return [_dx("phan_tich", "khac", "Quyết định về bản bình luận không SĐT (đang bật cho mọi nhóm)",
                "Bản không SĐT/địa chỉ đang gửi cho MỌI nhóm kể từ lần Facebook chặn bình luận; khách chỉ liên hệ được "
                "qua trả lời bình luận hoặc nhắn tin. Chủ shop quyết định: giữ nguyên (an toàn hơn) hoặc thử dùng lại "
                "bản có SĐT ở 1–2 nhóm trong vài ngày rồi theo dõi số bình luận bị chặn",
                f"trong {bc['so_ngay']} ngày đã gửi {p['binh_luan_gui']} bình luận không SĐT; khách ghi nhận "
                f"{p['goi'] + p['nhan'] + p['mua']}", "có thêm khách gọi trực tiếp", "bị Facebook chặn bình luận lại",
                hom_nay)]


def _binh_luan_moi_bai(bc: dict, hom_nay: date) -> list[DeXuat]:
    mb = bc["moi_bai"]
    if not mb or mb["nen"] <= 0 or mb["gan"] < mb["nen"] * bao_cao.NGUONG_BL_MOI_BAI:
        return []
    return [_dx("rui_ro", "doi_cau_hinh", "Giảm số bình luận mỗi bài xuống 3",
                "Trong config.py đặt COMMENT_PRODUCTS_PER_POST = 3 rồi khởi động lại cửa sổ bình luận "
                "(mỗi bài chỉ 3 mẫu màn thay vì nhiều hơn)",
                f"mỗi bài đang nhận trung bình {mb['gan']} bình luận (trước đó {mb['nen']})",
                "giảm nguy cơ bị Facebook coi là spam", "ít mẫu màn được nhìn thấy hơn", hom_nay)]


def _gia_la(bc: dict, hom_nay: date) -> list[DeXuat]:
    mau = bc["mau"]
    if not mau["gia_la"]:
        return []
    gia = "; ".join(f"{su_that.dinh_dang_gia(g['gia'])}đ ({g['so_mau']} mẫu)" for g in mau["gia_la"][:TOI_DA_NHOM_NEU_TEN])
    return [_dx("noi_dung", "khac", "Xác nhận các giá lạ trong mẫu bình luận",
                f"Mẫu bình luận đang nhắc giá không có trong tab Sản phẩm: {gia}. Giá đúng thì thêm vào mục "
                '"Giá được phép nhắc thêm" của data/su-that.md; giá sai thì sửa mẫu',
                f"{mau['so_mau_lech']}/{mau['so_mau']} mẫu bình luận có thông tin lệch tab Sản phẩm hoặc sổ sự thật",
                "mẫu bình luận chỉ nhắc giá đúng", "không có", hom_nay)]


def de_xuat_theo_luat(bc: dict, hom_nay: date) -> list[DeXuat]:
    """Các đề xuất rút ra từ báo cáo `bc`, theo thứ tự ưu tiên"""
    ket_qua: list[DeXuat] = []
    for ham in (_nhom_vo_ich, _mau_hay_bi_chan, _thieu_khach, _nguon_khach_giam, _bo_so_dien_thoai,
                _binh_luan_moi_bai, _gia_la):
        ket_qua += ham(bc, hom_nay)
    return ket_qua
