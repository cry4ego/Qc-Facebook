"""
Các vai AI của công ty (Phân tích, Săn khách, Nội dung, Chăm sóc khách) và Giám đốc. AI chỉ lo phần LỜI: nhận xét, đề xuất,
bản nháp; mọi con số do code tính sẵn trong báo cáo rồi đưa vào "bối cảnh". Vai Kiểm soát rủi ro KHÔNG dùng AI (rao_chan.py).

Riêng tư: bối cảnh gửi cho AI chỉ gồm số liệu tổng hợp, tên nhóm công khai, giá trong tab Sản phẩm và các mục chính sách của
sổ sự thật — KHÔNG có SĐT, Zalo, tên người bán, nội dung bài của khách hay bất kỳ thông tin khách hàng nào.
"""
import json
import re
from dataclasses import asdict, dataclass, field

from cong_ty import ai
from cong_ty.de_xuat import LOAI, DeXuat
from cong_ty.su_that import TRUONG, SuThat

VAI_AI = ("phan_tich", "san_khach", "noi_dung", "cham_soc_khach")   # thứ tự họp
DE_XUAT_MOI_VAI = 2     # mỗi vai nêu tối đa ... đề xuất mỗi cuộc họp
MAX_VAN_BAN = 1500
KHONG_GUI_AI = ("Số điện thoại", "Zalo", "Người bán")       # mục sổ sự thật không đưa cho AI
CHO_PHEP_GUI_AI = tuple(t for t in TRUONG if t not in KHONG_GUI_AI)   # chỉ các mục có tên này mới được gửi (danh sách cho phép)
_DAY_SO_DAI = re.compile(r"\d(?:[ .\-]?\d){7,}")   # dãy từ 8 chữ số trở lên (SĐT, số tài khoản…)
SO_NGAY_GUI_AI = 7

LUAT_CHUNG = """Bạn là một thành viên của công ty AI giúp shop bán màn hình MSI cũ ở Hà Nội (bán qua Facebook).
Quy tắc bắt buộc:
- Chỉ dựa trên dữ liệu được cung cấp. Không bịa số liệu, giá, bảo hành, khuyến mãi hay thông tin khách.
- Mỗi đề xuất phải nêu ít nhất một SỐ LIỆU có thật trong dữ liệu (trường "vi_sao").
- KHÔNG đề xuất: đổi giá hay khuyến mãi; nhắn tin chủ động cho người lạ; tăng số bình luận hoặc vượt trần mỗi ngày; quảng cáo trả phí; dùng nick phụ; xóa dữ liệu.
- Chỉ nhóm Facebook mua bán MÀN HÌNH ở HÀ NỘI. Không PC, linh kiện, laptop, khách tỉnh xa.
- Viết tiếng Việt CÓ DẤU đầy đủ (không bao giờ viết không dấu), ngắn gọn, không emoji.
- Trường "de_xuat_da_co" liệt kê các đề xuất ĐÃ CÓ: đừng lặp lại; chỉ đề xuất ý MỚI hoặc cụ thể hơn, hoặc để "de_xuat" rỗng
  nếu không có gì mới.
Trả lời DUY NHẤT một đối tượng JSON, không thêm chữ nào ngoài JSON."""

NHIEM_VU = {
    "phan_tich": "Bạn là TRƯỞNG PHÒNG PHÂN TÍCH. Đọc số liệu, nêu điều đáng chú ý nhất (tối đa 3 ý, mỗi ý kèm số liệu) "
                 "và đề xuất việc nên làm.",
    "san_khach": "Bạn là TRƯỞNG PHÒNG SĂN KHÁCH, lo việc chọn nhóm Facebook: nhóm nào nên ưu tiên, nên giảm, nên tìm thêm "
                 "(chỉ nhóm màn hình ở Hà Nội).",
    "noi_dung": "Bạn là TRƯỞNG PHÒNG NỘI DUNG. Đề xuất mẫu bình luận hoặc bài đăng mới, hoặc thử nghiệm so sánh 2 bản. "
                "Quy tắc mẫu bình luận: phải NGẮN — khách đọc dài sẽ khó nhớ và nghĩ là spam. Chỉ gồm mã màn hình, thông số màn, "
                "công nghệ màn (tối đa 3 dòng); hệ thống tự ghép MỘT dòng liên hệ dạng Tên-SĐT-địa chỉ ở cuối. KHÔNG lời chào "
                "mời dài, KHÔNG viết giá, bảo hành, tình trạng máy, số điện thoại, địa chỉ hay tên người bán; KHÔNG emoji; "
                "không hứa gì ngoài sổ sự thật.",
    "cham_soc_khach": "Bạn là TRƯỞNG PHÒNG CHĂM SÓC KHÁCH. Soạn sẵn kịch bản trả lời khi khách hỏi (giá, bảo hành, địa chỉ, "
                      "xem máy) chỉ dựa trên sổ sự thật, hoặc đề xuất cách thu thập số liệu khách. Không nhắn chủ động "
                      "cho người lạ.",
}
KHUON_VAI = ('Định dạng: {"nhan_xet": "tối đa 80 từ", "de_xuat": [tối đa %d phần tử, mỗi phần tử: {"loai": một trong %s, '
             '"tieu_de": "...", "noi_dung": "việc cụ thể (mẫu bình luận thì viết đủ nội dung mẫu)", '
             '"vi_sao": "lý do KÈM SỐ LIỆU", "ky_vong": "...", "rui_ro": "...", '
             '"ngay_do": số ngày tới để đo kết quả, từ 1 đến 60}]}') % (DE_XUAT_MOI_VAI, json.dumps(list(LOAI), ensure_ascii=False))
NHIEM_VU_GIAM_DOC = ("Bạn là GIÁM ĐỐC. Bạn nhận danh sách đề xuất đã qua Kiểm soát rủi ro. Chọn tối đa %d đề xuất đáng làm "
                     "nhất cho chủ shop duyệt (ưu tiên tác động tới khách thật, rẻ, ít rủi ro cho tài khoản); phần còn lại "
                     "hoãn. Viết tóm tắt cho chủ shop (tối đa 120 từ: điều quan trọng nhất của số liệu và việc cần duyệt). "
                     'Định dạng: {"tom_tat": "...", "quyet_dinh": [{"so_de_xuat": số thứ tự, '
                     '"quyet_dinh": "chap_nhan" hoặc "hoan", "ly_do": "ngắn gọn"}]}')


@dataclass(frozen=True)
class KetQuaVai:
    nhan_xet: str = ""
    de_xuat: tuple = ()     # các đề xuất thô (dict), chưa chuẩn hóa
    loi: str = ""           # có lỗi thì ghi lý do (không có AI / không đọc được trả lời)
    nguon: str = ""         # nguồn AI đã trả lời


@dataclass(frozen=True)
class GiamDoc:
    tom_tat: str
    quyet_dinh: dict = field(default_factory=dict)   # {số thứ tự: (quyet, ly_do)}
    nguon: str = ""


def su_that_cho_ai(so: SuThat) -> dict:
    """Phần sổ sự thật được phép đưa cho AI: chỉ các mục trong CHO_PHEP_GUI_AI (mục lạ như "SĐT", "Hotline" bị bỏ), và mọi
    dãy từ 8 chữ số trở lên (SĐT, số tài khoản) trong giá trị bị che"""
    return {"da_dien": {k: _DAY_SO_DAI.sub("[đã ẩn]", v) for k, v in so.thong_tin if k in CHO_PHEP_GUI_AI},
            "chua_dien": list(so.chua_dien),
            "gia_duoc_phep_them": list(so.gia_them), "cum_cam": list(so.cam)}


def boi_canh(bc: dict, so: SuThat, san_pham: list[dict]) -> dict:
    """Dữ liệu gọn gửi cho AI, rút từ báo cáo sáng (không có thông tin cá nhân của ai)"""
    cd, mau = bc["chan_doan"], bc["mau"]
    return {
        "ngay": bc["hom_nay"], "so_ngay": bc["so_ngay"], "pheu": bc["pheu"],
        "chan_doan": {k: cd[k] for k in ("trang_thai", "giam_pct", "goc", "cau")},
        "theo_ngay": [{k: d[k] for k in ("ngay", "quet", "bai_thay", "bai_mua", "dat_loc", "bai_binh_luan",
                                         "binh_luan_gui")} for d in bc["chuoi"][-SO_NGAY_GUI_AI:]],
        "nhom_noi_bat": [{k: r[k] for k in ("ten", "quet", "mua", "dat_loc", "khach")} for r in bc["nhom"][:5]],
        "nhom_quet_nhieu_khong_ra_bai": [{"ten": r["ten"], "quet": r["quet"]} for r in bc["vo_ich"][:5]],
        "ly_do_bo_qua_bai_mua": bc["ly_do_bo_qua"],
        "mau_binh_luan": {"so_mau": mau["so_mau"], "so_mau_lech": mau["so_mau_lech"], "gia_la": mau["gia_la"],
                          "thong_ke": [{k: m[k] for k in ("id", "san_pham", "da_gui", "bi_tu_choi")}
                                       for m in mau["thong_ke"][:5]]},
        "rui_ro": {k: bc["rui_ro"][k] for k in ("safe_all", "bi_chan", "bi_tu_choi", "bai_hom_nay", "tran", "chan_den")},
        "khach": {**bc["khach"]["tong"], "co_so_lieu": bc["khach"]["co_so_lieu"]},
        "nhan_xet_cua_bao_cao": [n["noi_dung"] for n in bc["nhan_xet"]],
        "san_pham": [{"ten": p["name"], "gia": p["price"]} for p in san_pham],
        "so_su_that": su_that_cho_ai(so),
    }


def _doc_tra_loi(kq: ai.KetQuaAI | None) -> KetQuaVai:
    if kq is None:
        return KetQuaVai(loi="AI không trả lời (hết lượt hoặc lỗi mạng)")
    try:
        data = ai.doc_json(kq.van_ban)
    except ValueError:
        return KetQuaVai(loi="Lỗi: không đọc được câu trả lời của AI (không phải JSON hợp lệ)", nguon=kq.nguon)
    de_xuat = data.get("de_xuat")
    ds = tuple(d for d in de_xuat if isinstance(d, dict))[:DE_XUAT_MOI_VAI] if isinstance(de_xuat, list) else ()
    return KetQuaVai(nhan_xet=str(data.get("nhan_xet") or "")[:MAX_VAN_BAN], de_xuat=ds, nguon=kq.nguon)


def _he_thong(vai: str) -> str:
    return f"{LUAT_CHUNG}\n\n{NHIEM_VU[vai]}\n\n{KHUON_VAI}"


def chay_vai(bo_ai, vai: str, boi: dict) -> KetQuaVai:
    """Một vai nhận bối cảnh, trả nhận xét + tối đa 2 đề xuất thô"""
    return _doc_tra_loi(bo_ai.hoi(_he_thong(vai), json.dumps({"du_lieu": boi}, ensure_ascii=False), nhan=vai))


def sua_vai(bo_ai, vai: str, boi: dict, bi_chan: list[tuple[DeXuat, tuple[str, ...]]]) -> KetQuaVai:
    """Vòng 2: vai nhận lại các đề xuất bị Kiểm soát rủi ro chặn kèm lý do, sửa lại cho hợp lệ hoặc bỏ đi"""
    yeu_cau = ("Các đề xuất dưới đây bị Kiểm soát rủi ro chặn. Hãy sửa lại cho hợp lệ (dẫn số liệu có thật, bỏ phần bị "
               "cấm) hoặc bỏ đi. Trả lời cùng định dạng JSON.")
    nguoi_dung = json.dumps({"du_lieu": boi, "yeu_cau": yeu_cau,
                             "bi_chan": [{"de_xuat": asdict(dx), "ly_do_bi_chan": list(van_de)} for dx, van_de in bi_chan]},
                            ensure_ascii=False)
    return _doc_tra_loi(bo_ai.hoi(_he_thong(vai), nguoi_dung, nhan=f"sua:{vai}"))


def _so_thu_tu(gia_tri) -> int | None:
    """Số thứ tự đề xuất mà AI viết: 1, 1.0 hoặc "1" đều chấp nhận (AI nhỏ hay viết lệch kiểu); còn lại bỏ"""
    if isinstance(gia_tri, bool):
        return None
    if isinstance(gia_tri, int):
        return gia_tri
    if isinstance(gia_tri, float) and gia_tri.is_integer():
        return int(gia_tri)
    if isinstance(gia_tri, str) and gia_tri.strip().isascii() and gia_tri.strip().isdigit():
        return int(gia_tri.strip())
    return None


def giam_doc_chot(bo_ai, ung_vien: list[DeXuat], toi_da: int, boi: dict) -> GiamDoc | None:
    """Giám đốc xem các đề xuất đã qua rào chắn, chọn tối đa `toi_da` cái trình chủ shop và viết tóm tắt. None nếu AI
    không trả lời được (cuộc họp tự chọn theo thứ tự ưu tiên)"""
    ds = [{"so": i, "vai": dx.vai, "loai": dx.loai, "tieu_de": dx.tieu_de, "vi_sao": dx.vi_sao}
          for i, dx in enumerate(ung_vien, 1)]
    he_thong = f"{LUAT_CHUNG}\n\n{NHIEM_VU_GIAM_DOC % toi_da}"
    kq = bo_ai.hoi(he_thong, json.dumps({"du_lieu": boi, "de_xuat": ds}, ensure_ascii=False), nhan="giam_doc")
    if kq is None:
        return None
    try:
        data = ai.doc_json(kq.van_ban)
    except ValueError:
        return None
    quyet_dinh = {}
    for q in data.get("quyet_dinh") if isinstance(data.get("quyet_dinh"), list) else []:
        so = _so_thu_tu(q.get("so_de_xuat")) if isinstance(q, dict) else None
        if so is not None and q.get("quyet_dinh") in ("chap_nhan", "hoan"):
            quyet_dinh[so] = (q["quyet_dinh"], str(q.get("ly_do") or "")[:300])
    return GiamDoc(str(data.get("tom_tat") or "")[:MAX_VAN_BAN], quyet_dinh, kq.nguon)
