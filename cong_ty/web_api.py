"""API web của tab Công ty AI (Flask Blueprint): ghi khách, báo cáo sáng, tình trạng sổ sự thật."""
import json
import logging
import os
import sqlite3
from datetime import date, datetime, timedelta
from typing import Callable, Protocol

from flask import Blueprint, jsonify, request, send_from_directory

from cong_ty import ai, bao_cao, hanh_dong, khach, luu_tru, mau_ai, su_that
from modules.db import Database

log = logging.getLogger(__name__)
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
NGAY_MAC_DINH, NGAY_TOI_DA = 30, 365
LICH_SU_TOI_DA = 50       # số đề xuất gần nhất trả về cho tab
HOP_TOI_DA_MOI_NGAY = 4   # kể cả "Họp ngay": tối đa ... cuộc họp mỗi ngày (mỗi cuộc tốn lượt AI và thêm dòng vào CSDL)
PHUT_COI_LA_KET = 30      # cuộc họp "đang họp" quá ... phút coi như kẹt
GHI_CHU_TOI_DA = 500
LAM_LUON = "lam_luon"     # quyet_dinh đặc biệt: đồng ý rồi công ty làm luôn (khác với 3 quyết định ghi tay của chủ shop)
DINH_DANG_NGAY = "%Y-%m-%d"


class CauHinhWeb(Protocol):
    MAX_COMMENTED_POSTS_PER_DAY: int
    SU_THAT_FILE: str


def _loi(thong_bao: str, ma: int = 400):
    return jsonify({"error": thong_bao}), ma


def _viec_da_lam(db: Database) -> list[dict]:
    """Nhật ký việc công ty đã làm (mới nhất trước), kèm tiêu đề đề xuất, các mẫu đã tắt / thêm (variant_ids) hoặc các từ khóa
    tìm nhóm đã thêm (tu_khoa)"""
    ket_qua, mau = [], {v["id"]: v["text"] for v in db.variants()}
    for dong in hanh_dong.liet_ke(db, LICH_SU_TOI_DA):
        dx = luu_tru.de_xuat_theo_id(db, dong["de_xuat_id"])
        doi_tuong = json.loads(dong["doi_tuong"])
        ids = doi_tuong.get("variant_ids", [])
        # việc thêm mẫu: kèm chính chữ AI đã viết để chủ shop đọc lại ngay trong nhật ký
        mo_ta = [mau_ai.mo_dau_cua(mau[i]) for i in ids if i in mau] if dong["hanh_dong"] == hanh_dong.THEM_MAU else []
        ket_qua.append({**dong, "tieu_de": dx["tieu_de"] if dx else "", "variant_ids": ids,
                        "tu_khoa": doi_tuong.get("tu_khoa", []), "mo_ta": mo_ta})
    return ket_qua


def _so_ngay(chu: str) -> int | None:
    """Số ngày hợp lệ (1..NGAY_TOI_DA), không thì None. Chữ số lạ như '²' (isdigit() nhận nhưng int() không) cũng là None"""
    try:
        so = int(chu)
    except ValueError:
        return None
    return so if 1 <= so <= NGAY_TOI_DA else None


def _khoi_tao(db: Database, config: CauHinhWeb) -> None:
    """Tạo bảng khách + file sổ sự thật mẫu. Thất bại (CSDL đang khóa, không ghi được file…) chỉ ghi log: không được
    làm cả web quản lý không khởi động được"""
    try:
        khach.ensure_schema(db)
        luu_tru.ensure_schema(db)
        hanh_dong.ensure_schema(db)
        ai.ensure_schema(db)
        su_that.tao_mau_neu_chua_co(config.SU_THAT_FILE)
    except (OSError, sqlite3.Error) as e:
        log.warning("Công ty AI: chưa khởi tạo được (%s) — tab Công ty AI có thể báo lỗi, các tab khác vẫn chạy", e)


def tao_blueprint(db: Database, config: CauHinhWeb, hom_nay: Callable[[], date] = date.today,
                  bay_gio: Callable[[], datetime] = datetime.now) -> Blueprint:
    """`hom_nay` / `bay_gio`: hàm trả về ngày / giờ hiện tại (đổi được khi test)"""
    _khoi_tao(db, config)
    bp = Blueprint("cong_ty", __name__)

    @bp.get("/api/congty/khach")
    def danh_sach_khach():
        so_ngay = _so_ngay(request.args.get("days", str(NGAY_MAC_DINH)))
        if so_ngay is None:
            return _loi(f"days phải là số từ 1 đến {NGAY_TOI_DA}")
        tu = (hom_nay() - timedelta(days=so_ngay - 1)).strftime(DINH_DANG_NGAY)
        return jsonify({"rows": khach.liet_ke(db, tu), "tong": khach.tong_theo_ngay(db, tu),
                        "nguon": khach.tong_theo_nguon(db, tu)})

    @bp.post("/api/congty/khach")
    def them_khach():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return _loi("Cần gửi dữ liệu JSON")
        try:
            k = khach.chuan_hoa(data.get("ngay") or hom_nay().strftime(DINH_DANG_NGAY), data.get("loai", ""),
                                data.get("so_luong", 1), data.get("nguon", ""), data.get("san_pham", ""),
                                data.get("so_tien"), data.get("ghi_chu", ""), hom_nay=hom_nay())
        except ValueError as e:
            return _loi(str(e))
        return jsonify({"id": khach.them(db, k)})

    @bp.delete("/api/congty/khach/<int:khach_id>")
    def xoa_khach(khach_id):
        if not khach.xoa(db, khach_id):
            return _loi("Không tìm thấy dòng này", 404)
        return jsonify({"ok": True})

    @bp.get("/api/congty/baocao")
    def bao_cao_sang():
        chu = request.args.get("date")
        try:
            ngay = datetime.strptime(chu, DINH_DANG_NGAY).date() if chu else hom_nay()
        except ValueError:
            return _loi("date phải có dạng năm-tháng-ngày, ví dụ 2026-10-24")
        if ngay < bao_cao.NGAY_SOM_NHAT:
            return _loi(f"Báo cáo chỉ có từ {bao_cao.NGAY_SOM_NHAT:%Y-%m-%d} trở đi")
        if ngay > hom_nay():
            return _loi("Không xem được báo cáo của ngày chưa tới")
        return jsonify(bao_cao.tao_bao_cao(db, config, config.SU_THAT_FILE, ngay, bay_gio=bay_gio()))

    @bp.get("/api/congty/suthat")
    def so_su_that():
        so = su_that.doc(config.SU_THAT_FILE)
        return jsonify({"duong_dan": config.SU_THAT_FILE, "co_file": so.co_file, "chua_dien": list(so.chua_dien),
                        "so_truong": len(su_that.TRUONG), "gia_them": list(so.gia_them), "cam": list(so.cam),
                        "loi": so.loi})

    def che_do_hien_tai() -> dict:
        return luu_tru.che_do(db, hom_nay(), getattr(config, "CONG_TY_NGAY_QUAN_SAT", 7))

    @bp.get("/api/congty/hop")
    def trang_thai_hop():
        gan_nhat = luu_tru.cuoc_hop_gan_nhat(db)
        che_do = che_do_hien_tai()
        return jsonify({
            "gan_nhat": gan_nhat and {"cuoc_hop": gan_nhat, "ban_tin": luu_tru.ban_tin_cua(db, gan_nhat["id"]),
                                      "de_xuat": luu_tru.liet_ke_de_xuat(db, cuoc_hop_id=gan_nhat["id"])},
            "cho_duyet": luu_tru.liet_ke_de_xuat(db, trang_thai=luu_tru.CHO_DUYET),
            "lich_su": luu_tru.liet_ke_de_xuat(db, limit=LICH_SU_TOI_DA),
            "ai": ai.tao_bo_ai(db, config, hom_nay).trang_thai(),
            "che_do": che_do, "tu_lam": {"bat": luu_tru.tu_lam_dang_bat(db), "mo_khoa": che_do["xong"]},
            "viec_da_lam": _viec_da_lam(db),
            "dang_cho_hop": luu_tru.dang_cho_hop(db), "gio_hop": getattr(config, "CONG_TY_GIO_HOP", 7)})

    @bp.post("/api/congty/hop")
    def yeu_cau_hop():
        """Bấm "Họp ngay": ghi yêu cầu, cửa sổ họp nền (python main.py hopngam) sẽ họp trong vòng một phút. Không cho bấm
        chồng: đã có yêu cầu đang chờ, đang họp, hoặc hôm nay đã họp đủ HOP_TOI_DA_MOI_NGAY lần"""
        if luu_tru.dang_cho_hop(db):
            return _loi("Đã có yêu cầu họp đang chờ — đợi cửa sổ họp xử lý", 409)
        if luu_tru.dang_hop_gan_day(db, bay_gio(), PHUT_COI_LA_KET):
            return _loi("Công ty đang họp — đợi họp xong rồi bấm lại", 409)
        da_hop = len(luu_tru.cuoc_hop_cua_ngay(db, hom_nay().strftime(DINH_DANG_NGAY)))
        if da_hop >= HOP_TOI_DA_MOI_NGAY:
            return _loi(f"Hôm nay đã họp {da_hop} lần — tối đa {HOP_TOI_DA_MOI_NGAY} lần mỗi ngày", 409)
        luu_tru.yeu_cau_hop(db)
        return jsonify({"ok": True})

    @bp.post("/api/congty/dexuat/<int:de_xuat_id>")
    def quyet_dinh_de_xuat(de_xuat_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return _loi("Cần gửi dữ liệu JSON")
        quyet, ghi_chu = data.get("quyet_dinh"), str(data.get("ghi_chu") or "")[:GHI_CHU_TOI_DA]
        cho_phep = (*luu_tru.QUYET_DINH_CHU_SHOP, LAM_LUON)
        if quyet not in cho_phep:
            return _loi(f"quyet_dinh phải là một trong: {', '.join(cho_phep)}")
        try:
            if quyet == LAM_LUON:     # đồng ý + công ty làm luôn (chỉ việc do luật đề xuất, trong giới hạn cứng)
                return jsonify({"ok": True, **hanh_dong.lam_luon(
                    db, de_xuat_id, ghi_chu, bay_gio(), su_that_file=config.SU_THAT_FILE,
                    truy_van_goc=tuple(getattr(config, "GROUP_SEARCH_QUERIES", ())))})
            luu_tru.quyet_dinh(db, de_xuat_id, quyet, ghi_chu, bay_gio())
        except LookupError as e:
            return _loi(str(e), 404)
        except (ValueError, hanh_dong.KhongLamDuoc) as e:
            return _loi(str(e), 409)
        return jsonify({"ok": True})

    @bp.post("/api/congty/nhatky/<int:nhat_ky_id>/hoantac")
    def hoan_tac_viec(nhat_ky_id):
        try:
            hanh_dong.hoan_tac(db, nhat_ky_id, bay_gio())
        except LookupError as e:
            return _loi(str(e), 404)
        except ValueError as e:
            return _loi(str(e), 409)
        return jsonify({"ok": True})

    @bp.post("/api/congty/tulam")
    def dat_cong_tac_tu_lam():
        """Công tắc "công ty tự làm": TẮT thì luôn được, BẬT chỉ khi đã hết chế độ quan sát"""
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("bat"), bool):
            return _loi('Cần gửi {"bat": true} hoặc {"bat": false}')
        if data["bat"]:
            che_do = che_do_hien_tai()
            if not che_do["xong"]:
                return _loi(f"Công ty còn đang trong chế độ quan sát (ngày {che_do['ngay']}/{che_do['tong']}) — "
                            "hết quan sát mới bật được công tắc tự làm", 409)
        luu_tru.dat_tu_lam(db, data["bat"])
        return jsonify({"ok": True})

    @bp.get("/congty/app.js")
    def ma_giao_dien():
        return send_from_directory(WEB_DIR, "app.js", mimetype="text/javascript")

    return bp
