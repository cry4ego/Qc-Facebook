"""
Những việc công ty được phép TỰ LÀM (Giai đoạn 3 + 5, "bậc 1" trong Cong-Ty-AI.md). Bot đọc lại bảng `comment_variants` mỗi bài
nên mọi thay đổi có hiệu lực ngay, không cần khởi động lại.
- TAT_MAU: tắt các mẫu bình luận hay bị Facebook chặn / từ chối (đề xuất do LUẬT sinh ra);
- THEM_MAU: thêm mẫu bình luận ngắn mà AI viết thẻ thông số, code ghép phần người bán / SĐT / địa chỉ (xem mau_ai.py).

An toàn bằng CODE (không dựa vào lời dặn AI):
- chỉ thực hiện việc có tham số có cấu trúc do CODE tạo (AI không bao giờ tạo được tham số); mỗi hành động chỉ nhận đúng nguồn
  của nó (NGUON_CHO_PHEP); chữ AI viết trong THEM_MAU được kiểm tra LẠI lúc thực hiện;
- chỉ tắt / thêm, không xóa — hoàn tác được; mọi lần làm ghi vào `nhat_ky_hanh_dong` (ghi TRƯỚC khi sửa);
- giới hạn cứng: tắt tối đa MAX_TAT_MOI_NGAY mẫu mỗi ngày, mỗi lần tối đa MAX_MAU_MOI_LAN mẫu, shop luôn còn ít nhất
  MIN_MAU_CON_LAI mẫu đang bật và mỗi sản phẩm luôn còn ít nhất 1 mẫu; thêm mẫu AI theo hạn mức trong mau_ai.py;
- làm được hay không được đều kiểm tra HẾT trước khi sửa: có gì sai thì không sửa gì.
"""
import json
from datetime import datetime, timedelta

from cong_ty import luu_tru, mau_ai, nhom_ai, su_that
from modules.db import Database

TAT_MAU = "tat_mau"
THEM_MAU = mau_ai.THEM_MAU
THEM_TU_KHOA = nhom_ai.THEM_TU_KHOA
MAX_MAU_MOI_LAN = 5
MAX_TAT_MOI_NGAY = 5
MIN_MAU_CON_LAI = 10
NGAY_NGHI_SAU_HOAN_TAC = 30     # chủ shop hoàn tác việc tắt mẫu nào thì ngần ấy ngày công ty không tự tắt lại mẫu đó
PHUT_COI_LA_KET_VIEC = 10       # nhận việc quá ngần này phút mà chưa làm gì (máy tắt) thì coi là bỏ dở và nhả ra
MAX_ID = 2 ** 63 - 1
DINH_DANG_GIO = "%Y-%m-%d %H:%M:%S"
# nguồn của đề xuất mà từng hành động chịu nhận: luat = code dựng thẳng từ báo cáo; mau_ai = chữ AI viết nhưng code kiểm tra và dựng việc
NGUON_CHO_PHEP = {TAT_MAU: ("luat",), THEM_MAU: ("mau_ai",), THEM_TU_KHOA: ("tu_khoa_ai",)}
NGUON_TU_LAM = frozenset(n for nguon in NGUON_CHO_PHEP.values() for n in nguon)
_TU_CHOI_NGUON = {
    TAT_MAU: "Chỉ việc do luật (code) đề xuất mới được công ty tự thực hiện; việc do AI viết bạn tự làm tay",
    THEM_MAU: "Chỉ mẫu bình luận do AI viết qua bộ soạn có kiểm tra của code mới được công ty tự thêm; việc khác do AI "
              "viết bạn tự làm tay",
    THEM_TU_KHOA: "Chỉ từ khóa tìm nhóm do AI đề xuất qua bộ soạn có kiểm tra của code mới được công ty tự thêm; việc khác do "
                  "AI viết bạn tự làm tay"}

SCHEMA = """CREATE TABLE IF NOT EXISTS nhat_ky_hanh_dong (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    de_xuat_id   INTEGER NOT NULL,
    hanh_dong    TEXT NOT NULL,           -- tat_mau / them_mau / them_tu_khoa
    doi_tuong    TEXT NOT NULL,           -- JSON: {"variant_ids": [...]} các mẫu ĐÃ tắt (tat_mau) / ĐÃ thêm (them_mau) lần này;
                                          --       {"tu_khoa": [...]} các từ khóa tìm nhóm ĐÃ thêm (them_tu_khoa)
    luc          TEXT NOT NULL,           -- YYYY-MM-DD HH:MM:SS
    hoan_tac_luc TEXT                     -- NULL = chưa hoàn tác
)"""


class KhongLamDuoc(Exception):
    """Không thực hiện được hành động (vi phạm giới hạn, tham số sai…) — thông báo bằng tiếng Việt, chưa sửa gì"""


def ensure_schema(db: Database) -> None:
    db.execute(SCHEMA)


def _doc_hanh_dong(tham_so: str) -> tuple[str, dict]:
    try:
        d = json.loads(tham_so or "")
    except ValueError:
        raise KhongLamDuoc("Tham số của hành động không đọc được") from None
    if not isinstance(d, dict) or d.get("hanh_dong") not in NGUON_CHO_PHEP:
        raise KhongLamDuoc("Công ty chưa biết tự làm hành động này")
    return d["hanh_dong"], d


def _doc_tat_mau(d: dict) -> list[int]:
    ids = d.get("variant_ids")
    if (not isinstance(ids, list) or not 1 <= len(ids) <= MAX_MAU_MOI_LAN
            or not all(type(i) is int and 0 < i <= MAX_ID for i in ids)):
        raise KhongLamDuoc(f"Danh sách mẫu phải có từ 1 đến {MAX_MAU_MOI_LAN} số nguyên dương")
    return list(dict.fromkeys(ids))


def da_tat_trong_ngay(db: Database, ngay: str) -> int:
    """Số mẫu đã tắt trong ngày `ngay` và chưa hoàn tác"""
    rows = db.query("SELECT doi_tuong FROM nhat_ky_hanh_dong WHERE hanh_dong = ? AND luc LIKE ? AND hoan_tac_luc IS NULL",
                    (TAT_MAU, ngay + "%"))
    return sum(len(json.loads(r["doi_tuong"])["variant_ids"]) for r in rows)


def _ghi_nhat_ky(db: Database, de_xuat_id: int, hanh_dong: str, doi_tuong: dict, bay_gio: datetime) -> int:
    return db.execute("INSERT INTO nhat_ky_hanh_dong (de_xuat_id, hanh_dong, doi_tuong, luc) VALUES (?, ?, ?, ?)",
                      (de_xuat_id, hanh_dong, json.dumps(doi_tuong, ensure_ascii=False), bay_gio.strftime(DINH_DANG_GIO)))


def _tat_mau(db: Database, de_xuat_id: int, ids: list[int], bay_gio: datetime) -> int:
    mau = {v["id"]: v for v in db.variants()}
    thieu = [i for i in ids if i not in mau]
    if thieu:
        raise KhongLamDuoc(f"Không có mẫu bình luận #{', #'.join(map(str, thieu))}")
    can_tat = [i for i in ids if mau[i]["active"]]
    if not can_tat:
        raise KhongLamDuoc("Các mẫu này đã tắt rồi")
    ngay = bay_gio.strftime("%Y-%m-%d")
    da_tat = da_tat_trong_ngay(db, ngay)
    if da_tat + len(can_tat) > MAX_TAT_MOI_NGAY:
        raise KhongLamDuoc(f"Hôm nay đã tắt {da_tat} mẫu; tối đa {MAX_TAT_MOI_NGAY} mẫu mỗi ngày")
    con_lai = [v for v in mau.values() if v["active"] and v["id"] not in can_tat]
    if len(con_lai) < MIN_MAU_CON_LAI:
        raise KhongLamDuoc(f"Shop phải luôn còn ít nhất {MIN_MAU_CON_LAI} mẫu bình luận đang bật")
    if {mau[i]["product_id"] for i in can_tat} - {v["product_id"] for v in con_lai}:
        raise KhongLamDuoc("Mỗi sản phẩm phải còn ít nhất 1 mẫu bình luận đang bật")
    # ghi nhật ký TRƯỚC khi sửa: máy tắt giữa chừng thì mẫu nào đã tắt cũng có dòng nhật ký để hoàn tác
    nhat_ky_id = _ghi_nhat_ky(db, de_xuat_id, TAT_MAU, {"variant_ids": can_tat}, bay_gio)
    for i in can_tat:
        db.update_variant(i, active=0)
    return nhat_ky_id


def _them_mau(db: Database, de_xuat_id: int, du_lieu: dict, bay_gio: datetime, su_that_file: str | None) -> int:
    if not su_that_file:
        raise KhongLamDuoc("Thiếu đường dẫn sổ sự thật nên không ghép được phần người bán / liên hệ của bình luận")
    try:
        san_pham, noi_dung = mau_ai.chuan_bi_them_mau(db, du_lieu, su_that.doc(su_that_file),
                                                      su_that.gia_hop_le(db.products()), bay_gio)
    except mau_ai.LoiMau as e:
        raise KhongLamDuoc(str(e)) from None
    # thêm ở trạng thái TẮT -> ghi nhật ký -> mới bật: máy tắt giữa chừng thì không có mẫu đang bật mà thiếu nhật ký
    ids = [db.add_variant(san_pham["id"], chu, "", active=0) for chu in noi_dung]
    nhat_ky_id = _ghi_nhat_ky(db, de_xuat_id, THEM_MAU, {"variant_ids": ids}, bay_gio)
    for i in ids:
        db.update_variant(i, active=1)
    return nhat_ky_id


def _them_tu_khoa(db: Database, de_xuat_id: int, du_lieu: dict, bay_gio: datetime, truy_van_goc: tuple[str, ...]) -> int:
    try:
        tu_khoa = nhom_ai.chuan_bi_them(db, du_lieu, tuple(truy_van_goc), bay_gio)
    except nhom_ai.LoiTuKhoa as e:
        raise KhongLamDuoc(str(e)) from None
    nhat_ky_id = _ghi_nhat_ky(db, de_xuat_id, THEM_TU_KHOA, {"tu_khoa": tu_khoa}, bay_gio)    # ghi TRƯỚC khi sửa cài đặt
    nhom_ai.them_vao_setting(db, tu_khoa)
    return nhat_ky_id


def thuc_hien(db: Database, de_xuat_id: int, tham_so: str, nguon: str, bay_gio: datetime,
              su_that_file: str | None = None, truy_van_goc: tuple[str, ...] = ()) -> int:
    """Làm việc trong `tham_so` (tắt mẫu / thêm mẫu AI / thêm từ khóa tìm nhóm). Trả về id dòng nhật ký; không làm được thì
    KhongLamDuoc và KHÔNG sửa gì. su_that_file: đường dẫn sổ sự thật (bắt buộc với THEM_MAU để ghép người bán / SĐT / địa chỉ);
    truy_van_goc: các từ khóa tìm nhóm có sẵn trong config (để không thêm trùng)"""
    ten, du_lieu = _doc_hanh_dong(tham_so)
    if nguon not in NGUON_CHO_PHEP[ten]:
        raise KhongLamDuoc(_TU_CHOI_NGUON[ten])
    if ten == TAT_MAU:
        return _tat_mau(db, de_xuat_id, _doc_tat_mau(du_lieu), bay_gio)
    if ten == THEM_TU_KHOA:
        return _them_tu_khoa(db, de_xuat_id, du_lieu, bay_gio, truy_van_goc)
    return _them_mau(db, de_xuat_id, du_lieu, bay_gio, su_that_file)


def _mau_vua_bi_hoan_tac(db: Database, ids: list[int], bay_gio: datetime) -> list[int]:
    """Các mẫu trong `ids` mà chủ shop đã hoàn tác việc tắt trong NGAY_NGHI_SAU_HOAN_TAC ngày qua"""
    tu = (bay_gio - timedelta(days=NGAY_NGHI_SAU_HOAN_TAC)).strftime(DINH_DANG_GIO)
    rows = db.query("SELECT doi_tuong FROM nhat_ky_hanh_dong WHERE hanh_dong = ? AND hoan_tac_luc >= ?", (TAT_MAU, tu))
    da_hoan = {i for r in rows for i in json.loads(r["doi_tuong"])["variant_ids"]}
    return [i for i in ids if i in da_hoan]


def lam_luon(db: Database, de_xuat_id: int, ghi_chu: str, bay_gio: datetime, tu_dong: bool = False,
             su_that_file: str | None = None, truy_van_goc: tuple[str, ...] = ()) -> dict:
    """Chủ shop bấm "Đồng ý và làm luôn" (tu_dong=False) hoặc công tắc tự làm (tu_dong=True): làm việc trong đề xuất rồi đánh
    dấu đã làm. Việc làm TRƯỚC, đánh dấu SAU; đánh dấu hỏng (đề xuất vừa đổi trạng thái ở nơi khác) thì hoàn tác việc vừa
    làm. Tự động thì tôn trọng quyết định của chủ shop: mẫu bạn vừa hoàn tác không bị tắt lại trong NGAY_NGHI_SAU_HOAN_TAC
    ngày. LookupError nếu không có đề xuất; ValueError nếu không còn chờ duyệt / đã duyệt; KhongLamDuoc nếu việc không làm
    được (chưa sửa gì)"""
    dx = luu_tru.de_xuat_theo_id(db, de_xuat_id)
    if dx is None:
        raise LookupError("Không tìm thấy đề xuất này")
    if dx["trang_thai"] == luu_tru.DANG_LAM:     # đang làm dở, hoặc đã làm xong mà chưa kịp đánh dấu (máy tắt giữa chừng)
        da_ghi = db.query("SELECT id FROM nhat_ky_hanh_dong WHERE de_xuat_id = ? AND hoan_tac_luc IS NULL ORDER BY id DESC LIMIT 1",
                          (de_xuat_id,))
        if da_ghi:
            luu_tru.hoan_tat_viec(db, de_xuat_id, f"Công ty đã làm (nhật ký #{da_ghi[0]['id']}). {ghi_chu}".strip(), bay_gio)
            return {"da_lam": True, "nhat_ky_id": da_ghi[0]["id"]}
        nhan_luc = datetime.strptime(dx["quyet_luc"] or "", DINH_DANG_GIO) if dx["quyet_luc"] else None
        if nhan_luc is None or bay_gio - nhan_luc < timedelta(minutes=PHUT_COI_LA_KET_VIEC):
            raise ValueError("Đề xuất đang được xử lý ở nơi khác — đợi một lát rồi tải lại trang")
        luu_tru.tra_viec(db, de_xuat_id, luu_tru.CHO_DUYET)       # nhận việc quá lâu mà không làm gì: coi là bị bỏ dở, nhả ra
        dx = luu_tru.de_xuat_theo_id(db, de_xuat_id)
    if dx["trang_thai"] not in (luu_tru.CHO_DUYET, luu_tru.DA_DUYET):
        raise ValueError(f"Đề xuất đang ở trạng thái “{dx['trang_thai']}” — không làm được nữa")
    if not dx["tham_so"]:
        raise KhongLamDuoc("Đề xuất này công ty không tự làm được — bạn làm tay rồi bấm “Tôi đã làm xong”")
    ten, du_lieu = _doc_hanh_dong(dx["tham_so"])
    lai = _mau_vua_bi_hoan_tac(db, _doc_tat_mau(du_lieu), bay_gio) if tu_dong and ten == TAT_MAU else []
    if lai:
        raise KhongLamDuoc(f"Bạn đã hoàn tác việc tắt mẫu #{', #'.join(map(str, lai))} trong {NGAY_NGHI_SAU_HOAN_TAC} ngày "
                           "qua — để bạn tự quyết, công ty không tự tắt lại")
    truoc = luu_tru.nhan_viec(db, de_xuat_id, bay_gio)            # NHẬN việc trước: chỉ một bên làm được
    if truoc is None:
        raise ValueError("Đề xuất vừa được đổi trạng thái ở nơi khác — tải lại trang rồi thử lại")
    try:
        nhat_ky_id = thuc_hien(db, de_xuat_id, dx["tham_so"], dx["nguon"], bay_gio, su_that_file, truy_van_goc)
    except BaseException:
        luu_tru.tra_viec(db, de_xuat_id, truoc)                   # làm không được / hỏng: trả về trạng thái cũ (chưa sửa gì)
        raise
    luu_tru.hoan_tat_viec(db, de_xuat_id, f"Công ty đã làm (nhật ký #{nhat_ky_id}). {ghi_chu}".strip(), bay_gio)
    return {"da_lam": True, "nhat_ky_id": nhat_ky_id}


def hoan_tac(db: Database, nhat_ky_id: int, bay_gio: datetime) -> None:
    """Trả lại như cũ: việc tắt mẫu thì bật lại các mẫu, việc thêm mẫu thì tắt các mẫu đã thêm (không xóa), việc thêm từ khóa thì
    bỏ các từ khóa đó. LookupError nếu không có dòng đó; ValueError nếu đã hoàn tác rồi"""
    rows = db.query("SELECT * FROM nhat_ky_hanh_dong WHERE id = ?", (nhat_ky_id,)) if 0 < nhat_ky_id <= MAX_ID else []
    if not rows:
        raise LookupError("Không tìm thấy việc này trong nhật ký")
    if rows[0]["hoan_tac_luc"]:
        raise ValueError("Việc này đã hoàn tác rồi")
    doi_tuong = json.loads(rows[0]["doi_tuong"])
    if rows[0]["hanh_dong"] == THEM_TU_KHOA:
        nhom_ai.bo_khoi_setting(db, doi_tuong.get("tu_khoa", []))
    else:
        ton_tai = {v["id"] for v in db.variants()}
        bat = 0 if rows[0]["hanh_dong"] == THEM_MAU else 1
        for vid in doi_tuong.get("variant_ids", []):
            if vid in ton_tai:
                db.update_variant(vid, active=bat)
    db.execute("UPDATE nhat_ky_hanh_dong SET hoan_tac_luc = ? WHERE id = ?", (bay_gio.strftime(DINH_DANG_GIO), nhat_ky_id))


def liet_ke(db: Database, limit: int = 30) -> list[dict]:
    """Nhật ký hành động, mới nhất trước"""
    return db.query("SELECT * FROM nhat_ky_hanh_dong ORDER BY id DESC LIMIT ?", (limit,))
