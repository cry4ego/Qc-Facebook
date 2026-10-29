"""
Báo cáo sáng bằng code (Giai đoạn 1, chi phí 0đ): đọc CSDL của bot, tính phễu, giải thích vì sao số bài tăng / giảm, xếp
hạng nhóm, soát mẫu bình luận theo sổ sự thật, nêu rủi ro. Mọi câu nhận xét là luật cố định — chưa gọi AI.

tao_bao_cao() trả về dict (web hiển thị, JSON được); ra_van_ban() là bản chữ để lưu file / đọc nhanh.
"""
import os
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Protocol

from cong_ty import khach, so_lieu, su_that
from modules.db import Database

NGAY_SOM_NHAT = date(2000, 1, 1)  # báo cáo của ngày trước mốc này vô nghĩa (và tính ngày sẽ tràn số)
NGAY_CHUOI = 21                 # lấy số liệu ... ngày: đủ cho 3 ngày gần + 7 ngày trước đó + vài ngày bot nghỉ
NGAY_BAO_CAO = 7                 # kỳ báo cáo mặc định
NGAY_HIEN_THI = 14               # số ngày liệt kê trong bảng "theo ngày"
NGAY_GAN, NGAY_NEN, NGAY_NEN_TOI_THIEU = 3, 7, 3   # so 3 ngày gần nhất với (tối đa) 7 ngày trước đó
NGUONG_GIAM = 0.30               # giảm từ 30% trở lên mới coi là "giảm"
NGUONG_BL_MOI_BAI = 1.5          # bình luận mỗi bài tăng ≥ 1,5 lần thì nhắc
MIN_QUET_KET_LUAN = 30           # nhóm quét ít hơn số lần này chưa đủ để kết luận "không có khách"
MIN_BL_DANH_GIA_MAU = 20         # mẫu bình luận gửi ít hơn số này chưa đánh giá
TY_LE_MAU_XAU = 0.20             # mẫu có ≥ 20% bình luận bị chặn / từ chối thì nhắc
TOI_DA_VAN_DE_MAU = 20           # số mẫu lệch liệt kê chi tiết
BUOC = ("quet", "bai_thay", "bai_mua", "ty_le_dat")   # các bước của phễu, từ thượng nguồn xuống
KHOA_LOAI = {"Gọi": "goi", "Nhắn": "nhan", "Mua": "mua"}


class CauHinh(Protocol):
    MAX_COMMENTED_POSTS_PER_DAY: int


def _so(x: float) -> str:
    return f"{round(x):,}".replace(",", ".")


def _dd_mm(ngay: str) -> str:
    return f"{ngay[8:10]}/{ngay[5:7]}"


def _dd_mm_yyyy(ngay: str) -> str:
    return f"{ngay[8:10]}/{ngay[5:7]}/{ngay[:4]}"


# ---------- chẩn đoán số bài tăng / giảm ----------
def _tb(ngay_xet: list[dict], khoa: str) -> float:
    return sum(d[khoa] for d in ngay_xet) / len(ngay_xet)


def _chi_so(ngay_xet: list[dict]) -> dict:
    mua = sum(d["bai_mua"] for d in ngay_xet)
    return {**{k: _tb(ngay_xet, k) for k in ("quet", "bai_thay", "bai_mua", "bai_binh_luan", "binh_luan_gui")},
            "ty_le_dat": sum(d["dat_loc"] for d in ngay_xet) / mua if mua else 0.0}


def _giam(truoc: float, sau: float) -> bool:
    return truoc > 0 and sau < truoc * (1 - NGUONG_GIAM)


def _cua_so(chuoi: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """(3 ngày gần nhất, tối đa 7 ngày trước đó, các ngày bot không quét) — chỉ tính ngày trọn và ngày bot có chạy"""
    day_du = [d for d in chuoi if not d["chua_het"]]
    co_quet = [d for d in day_du if d["quet"] > 0]
    dau = next((i for i, d in enumerate(day_du) if d["quet"] > 0), None)
    ngung = [] if dau is None else [d["ngay"] for d in day_du[dau:] if d["quet"] == 0]
    gan = co_quet[-NGAY_GAN:]
    nen = co_quet[-(NGAY_GAN + NGAY_NEN):-NGAY_GAN] if len(co_quet) > NGAY_GAN else []
    return gan, nen, ngung


def _cau_ngung(ngung: list[str]) -> list[str]:
    return [f"Bot không quét {len(ngung)} ngày: {', '.join(_dd_mm(n) for n in ngung)}."] if ngung else []


def _cau_nguyen_nhan(giam: list[str], nen: dict, gan: dict) -> list[str]:
    cau = []
    if "quet" in giam:
        cau.append(f"Bot quét ít hơn: {_so(nen['quet'])} → {_so(gan['quet'])} lần/ngày — kiểm tra bot có bị dừng hoặc lỗi không.")
    if "bai_thay" in giam:
        a, b = _so(nen["bai_thay"]), _so(gan["bai_thay"])
        cau.append(f"Số bài bot xem giảm {a} → {b}/ngày (do quét ít hơn)." if "quet" in giam else
                   f"Bot vẫn quét như cũ (~{_so(gan['quet'])} lần/ngày) nhưng thấy ít bài hơn: {a} → {b} bài/ngày "
                   "— các nhóm đang đăng ít bài hơn.")
    if "bai_mua" in giam:
        cau.append(f"Người cần mua màn hình đăng ít hơn: {_so(nen['bai_mua'])} → {_so(gan['bai_mua'])} bài MUA/ngày.")
    if "ty_le_dat" in giam:
        cau.append(f"Tỷ lệ bài MUA đạt bộ lọc giảm từ {round(nen['ty_le_dat'] * 100)}% xuống "
                   f"{round(gan['ty_le_dat'] * 100)}% — xem lý do bỏ qua ở tab Phân loại bài.")
    return cau or ["Các bước quét, thấy bài, bài MUA, bộ lọc đều không giảm rõ rệt — kiểm tra bài bình luận thất bại "
                   "hoặc bị chặn ở tab Bình luận."]


def chan_doan(chuoi: list[dict]) -> dict:
    """So 3 ngày trọn gần nhất với 7 ngày trước đó (bỏ ngày bot nghỉ): số bài bình luận có giảm không, giảm ở bước nào
    của phễu (quét -> bài thấy -> bài MUA -> tỷ lệ đạt lọc). `goc` = bước thượng nguồn nhất bị giảm"""
    gan, nen, ngung = _cua_so(chuoi)
    khung = {"giam_pct": 0, "goc": None, "giam": [], "ngung": ngung, "nen": None, "gan": None}
    if len(gan) < NGAY_GAN or len(nen) < NGAY_NEN_TOI_THIEU:
        return {**khung, "trang_thai": "thieu_so_lieu", "cau": [
            f"Chưa đủ số liệu để so sánh (cần {NGAY_GAN} ngày gần nhất và ít nhất {NGAY_NEN_TOI_THIEU} ngày trước đó có "
            "bot chạy).", *_cau_ngung(ngung)]}
    cs_nen, cs_gan = _chi_so(nen), _chi_so(gan)
    if cs_nen["bai_binh_luan"] <= 0:
        return {**khung, "trang_thai": "thieu_so_lieu", "cau": [
            "Các ngày trước đó không có bài nào được bình luận nên chưa có gì để so sánh.", *_cau_ngung(ngung)]}
    giam_pct = round((1 - cs_gan["bai_binh_luan"] / cs_nen["bai_binh_luan"]) * 100)
    ket_qua = {**khung, "giam_pct": giam_pct, "nen": cs_nen, "gan": cs_gan}
    if not _giam(cs_nen["bai_binh_luan"], cs_gan["bai_binh_luan"]):
        return {**ket_qua, "trang_thai": "on_dinh", "cau": [
            f"Số bài bình luận ổn định: {_so(cs_gan['bai_binh_luan'])} bài/ngày "
            f"(trước đó {_so(cs_nen['bai_binh_luan'])}).", *_cau_ngung(ngung)]}
    giam = [b for b in BUOC if _giam(cs_nen[b], cs_gan[b])]
    dau_bao = (f"Số bài bình luận trung bình giảm {giam_pct}% (từ {_so(cs_nen['bai_binh_luan'])} xuống "
               f"{_so(cs_gan['bai_binh_luan'])} bài/ngày; so {NGAY_GAN} ngày gần nhất với {len(nen)} ngày trước đó).")
    return {**ket_qua, "trang_thai": "giam", "goc": giam[0] if giam else None, "giam": giam,
            "cau": [dau_bao, *_cau_nguyen_nhan(giam, cs_nen, cs_gan), *_cau_ngung(ngung)]}


def binh_luan_moi_bai(chuoi: list[dict]) -> dict | None:
    """Trung bình số bình luận mỗi bài: 3 ngày gần nhất so với 7 ngày trước đó. None nếu chưa đủ số liệu"""
    gan, nen, _ = _cua_so(chuoi)
    if len(gan) < NGAY_GAN or len(nen) < NGAY_NEN_TOI_THIEU:
        return None

    def ty_le(ngay_xet: list[dict]) -> float:
        bai = sum(d["bai_binh_luan"] for d in ngay_xet)
        return round(sum(d["binh_luan_gui"] for d in ngay_xet) / bai, 1) if bai else 0.0
    return {"nen": ty_le(nen), "gan": ty_le(gan)}


# ---------- tổng hợp ----------
def pheu(chuoi: list[dict], so_ngay: int = NGAY_BAO_CAO) -> dict:
    ky = chuoi[-so_ngay:]
    cong = {k: sum(d[k] for d in ky) for k in ("quet", "bai_thay", "bai_mua", "dat_loc", "bai_binh_luan",
                                               "binh_luan_gui", "goi", "nhan", "mua", "so_tien")}
    return {"tu": ky[0]["ngay"], "den": ky[-1]["ngay"], **cong}


def nhom_vo_ich(hang: list[dict], min_quet: int = MIN_QUET_KET_LUAN) -> list[dict]:
    """Nhóm quét nhiều lần mà không có bài nào đạt lọc và chưa ra khách — nên giảm ưu tiên"""
    ds = [r for r in hang if r["quet"] >= min_quet and r["dat_loc"] == 0 and r.get("khach", 0) == 0]
    return sorted(ds, key=lambda r: -r["quet"])


def kiem_tra_mau(db: Database, so: su_that.SuThat) -> dict:
    """Soát mọi mẫu bình luận đang bật theo tab Sản phẩm + sổ sự thật: giá lạ, SĐT lạ, cụm bị cấm, emoji"""
    san_pham = db.products()
    hop_le = su_that.gia_hop_le(san_pham) | set(so.gia_them)
    ten_san_pham = {p["id"]: p["name"] for p in san_pham}
    mau = db.variants(active_only=True)
    van_de, gia_la = [], Counter()
    for v in mau:
        doan = [t for t in (v["text"], v["safe_text"]) if t]
        loi = tuple(dict.fromkeys(x for t in doan for x in su_that.kiem_tra(t, so, hop_le)))
        gia_la.update({g for t in doan for g in su_that.tim_gia(t)} - hop_le)
        if loi:
            van_de.append({"id": v["id"], "san_pham": ten_san_pham.get(v["product_id"], "?"), "van_de": list(loi)})
    return {"so_mau": len(mau), "so_mau_lech": len(van_de), "van_de": van_de[:TOI_DA_VAN_DE_MAU],
            "gia_la": [{"gia": g, "so_mau": n} for g, n in sorted(gia_la.items(), key=lambda kv: (-kv[1], kv[0]))]}


def _tong_khach(db: Database, tu_ngay: str, den_ngay: str) -> dict:
    theo_ngay = khach.tong_theo_ngay(db, tu_ngay, den_ngay).values()
    tong = {**{KHOA_LOAI[loai]: sum(d[loai] for d in theo_ngay) for loai in khach.LOAI},
            "so_tien": sum(d["so_tien"] for d in theo_ngay)}
    nguon = [{"nguon": ten, **{KHOA_LOAI[loai]: v[loai] for loai in khach.LOAI}, "so_tien": v["so_tien"]}
             for ten, v in khach.tong_theo_nguon(db, tu_ngay, den_ngay).items()]
    nguon.sort(key=lambda r: -(r["goi"] + r["nhan"] + r["mua"]))
    return {"tu": tu_ngay, "tong": tong, "theo_nguon": nguon, "co_so_lieu": any(tong[k] for k in ("goi", "nhan", "mua"))}


def mau_hay_bi_chan(m: dict) -> bool:
    """Mẫu đủ số lần gửi mà tỷ lệ bị chặn / từ chối cao. Mẫu số gồm cả bình luận bị từ chối: mẫu bị từ chối gần hết
    (hoặc chỉ toàn bị từ chối) vẫn phải được nhắc"""
    thu = m["da_gui"] + m["bi_tu_choi"]
    return thu >= MIN_BL_DANH_GIA_MAU and m["bi_tu_choi"] / thu >= TY_LE_MAU_XAU


def nhan_xet(bc: dict) -> list[dict]:
    """Các điều chủ shop cần biết, theo luật cố định. muc: 'chu_y' (cần xem) / 'thong_tin'"""
    ghi = []

    def chu_y(noi_dung: str) -> None:
        ghi.append({"muc": "chu_y", "noi_dung": noi_dung})

    cd, rr, mb, su, mau = bc["chan_doan"], bc["rui_ro"], bc["moi_bai"], bc["su_that"], bc["mau"]
    if cd["trang_thai"] == "giam":
        chu_y(cd["cau"][0] + " Xem mục Chẩn đoán.")
    for cau in _cau_ngung(cd["ngung"]):
        chu_y(cau)
    if not bc["khach"]["co_so_lieu"]:
        chu_y(f"Chưa có số liệu khách trong {bc['so_ngay']} ngày — ghi ở tab Công ty AI (mục Ghi kết quả khách). "
              "Thiếu số này thì chỉ đo được số bình luận, không đo được việc bán hàng.")
    if rr["safe_all"]:
        ly_do = f" ({rr['safe_all_ly_do']})" if rr["safe_all_ly_do"] else ""
        chu_y(f"Đang gửi bản bình luận KHÔNG SĐT/địa chỉ cho mọi nhóm{ly_do}. Khách chỉ liên hệ được qua trả lời bình luận "
              "hoặc nhắn tin; xem mục bản an toàn ở tab Bình luận để quyết định có dùng lại bản đầy đủ không.")
    if rr["chan_den"]:
        chu_y(f"Facebook đang chặn bình luận đến {rr['chan_den']}.")
    if rr["bi_chan"] or rr["bi_tu_choi"]:
        chu_y(f"Trong {bc['so_ngay']} ngày có {rr['bi_chan']} bình luận bị chặn và {rr['bi_tu_choi']} bị từ chối.")
    if mb and mb["nen"] > 0 and mb["gan"] >= mb["nen"] * NGUONG_BL_MOI_BAI:
        chu_y(f"Trung bình mỗi bài đang nhận {mb['gan']} bình luận (trước đó {mb['nen']}); nhiều bình luận trên một bài "
              "có thể làm tăng nguy cơ bị Facebook chặn.")
    if bc["vo_ich"]:
        ten = ", ".join(r["ten"] for r in bc["vo_ich"][:5])
        chu_y(f"{len(bc['vo_ich'])} nhóm quét từ {MIN_QUET_KET_LUAN} lần mà không có bài nào đạt lọc: {ten}. "
              "Cân nhắc giảm ưu tiên.")
    xau = [m for m in mau["thong_ke"] if mau_hay_bi_chan(m)]
    if xau:
        chu_y(f"{len(xau)} mẫu bình luận hay bị chặn / từ chối (từ {round(TY_LE_MAU_XAU * 100)}% trở lên): "
              + ", ".join(f"#{m['id']}" for m in xau[:10]) + ".")
    if su["loi"]:
        chu_y(su["loi"])
    elif su["chua_dien"]:
        chu_y(f"Sổ sự thật còn {len(su['chua_dien'])} mục chưa điền: {', '.join(su['chua_dien'])} (file data/su-that.md).")
    if mau["so_mau_lech"]:
        gia = "; ".join(f"{su_that.dinh_dang_gia(g['gia'])}đ ({g['so_mau']} mẫu)" for g in mau["gia_la"][:5])
        chu_y(f"{mau['so_mau_lech']}/{mau['so_mau']} mẫu bình luận có thông tin lệch tab Sản phẩm / sổ sự thật"
              + (f". Giá không có trong bảng Sản phẩm: {gia}" if gia else "") + ".")
    return ghi or [{"muc": "thong_tin", "noi_dung": "Không có gì bất thường."}]


def tao_bao_cao(db: Database, config: CauHinh, duong_dan_su_that: str, hom_nay: date, so_ngay: int = NGAY_BAO_CAO,
                bay_gio: datetime | None = None) -> dict:
    """Báo cáo của ngày `hom_nay` (kỳ `so_ngay` ngày tới hết ngày đó). `bay_gio` = thời điểm thật khi xem (mặc định coi
    báo cáo là của ngày hôm nay). Chỉ đọc CSDL bot; chỉ tạo bảng `khach` nếu chưa có. Ngày trước 2000 -> ValueError"""
    if hom_nay < NGAY_SOM_NHAT:
        raise ValueError(f"Ngày quá xa: báo cáo chỉ có từ {NGAY_SOM_NHAT:%Y-%m-%d} trở đi")
    khach.ensure_schema(db)
    chuoi = so_lieu.chuoi_ngay(db, NGAY_CHUOI, hom_nay, bay_gio)
    hang = so_lieu.xep_hang_nhom(db, so_ngay, hom_nay)
    so = su_that.doc(duong_dan_su_that)
    tu_ngay = (hom_nay - timedelta(days=so_ngay - 1)).strftime("%Y-%m-%d")
    den_ngay = (hom_nay + timedelta(days=1)).strftime("%Y-%m-%d")
    bc = {
        "hom_nay": hom_nay.strftime("%Y-%m-%d"), "so_ngay": so_ngay,
        "chuoi": chuoi[-NGAY_HIEN_THI:], "pheu": pheu(chuoi, so_ngay), "chan_doan": chan_doan(chuoi),
        "moi_bai": binh_luan_moi_bai(chuoi), "nhom": hang[:10], "vo_ich": nhom_vo_ich(hang),
        "ly_do_bo_qua": so_lieu.ly_do_bo_qua_bai_mua(db, so_ngay, hom_nay),
        "mau": {**kiem_tra_mau(db, so), "thong_ke": so_lieu.mau_binh_luan(db, so_ngay, hom_nay)},
        "rui_ro": so_lieu.rui_ro(db, config.MAX_COMMENTED_POSTS_PER_DAY, hom_nay, so_ngay, bay_gio),
        "khach": _tong_khach(db, tu_ngay, den_ngay),
        "su_that": {"co_file": so.co_file, "chua_dien": list(so.chua_dien), "loi": so.loi},
    }
    bc["nhan_xet"] = nhan_xet(bc)
    bc["van_ban"] = ra_van_ban(bc)
    return bc


# ---------- bản chữ ----------
def _muc_chu_y(bc: dict) -> str:
    return "CẦN CHÚ Ý\n" + "\n".join(f"- {n['noi_dung']}" for n in bc["nhan_xet"])


def _muc_pheu(bc: dict) -> str:
    p, k = bc["pheu"], bc["khach"]["tong"]
    tien = f", thu {_so(k['so_tien'])}đ" if k["so_tien"] else ""
    return (f"PHỄU {bc['so_ngay']} NGÀY ({_dd_mm(p['tu'])} → {_dd_mm(p['den'])})\n"
            f"Bài bot xem: {_so(p['bai_thay'])}\n"
            f"  → bài người cần MUA: {_so(p['bai_mua'])}\n"
            f"  → đạt mọi bộ lọc: {_so(p['dat_loc'])}\n"
            f"  → đã bình luận: {_so(p['bai_binh_luan'])} bài ({_so(p['binh_luan_gui'])} bình luận)\n"
            f"  → khách: gọi {k['goi']}, nhắn {k['nhan']}, mua {k['mua']}{tien}")


def _muc_theo_ngay(bc: dict) -> str:
    dong = [f"{'Ngày':<12}{'Quét':>6}{'Thấy':>7}{'MUA':>6}{'Đạt':>6}{'Bài BL':>8}{'BL':>6}  Gọi/Nhắn/Mua"]
    for d in bc["chuoi"][-10:]:
        nhan = " (nay)" if d["chua_het"] else ""
        dong.append(f"{_dd_mm(d['ngay']) + nhan:<12}{d['quet']:>6}{d['bai_thay']:>7}{d['bai_mua']:>6}{d['dat_loc']:>6}"
                    f"{d['bai_binh_luan']:>8}{d['binh_luan_gui']:>6}  {d['goi']}/{d['nhan']}/{d['mua']}")
    return "THEO NGÀY\n" + "\n".join(dong)


def _muc_nhom(bc: dict) -> str:
    dong = [f"- {r['ten']}: quét {r['quet']} lần, MUA {r['mua']}, đạt lọc {r['dat_loc']}, khách {r['khach']}"
            for r in bc["nhom"][:5]]
    return "NHÓM NỔI BẬT\n" + "\n".join(dong) if dong else ""


def _muc_bo_qua(bc: dict) -> str:
    dong = [f"- {r['ly_do']}: {r['so_bai']} bài" for r in bc["ly_do_bo_qua"]]
    return "BÀI NGƯỜI CẦN MUA BỊ BỎ QUA VÌ\n" + "\n".join(dong) if dong else ""


def ra_van_ban(bc: dict) -> str:
    dau = f"BÁO CÁO SÁNG — {_dd_mm_yyyy(bc['hom_nay'])} ({bc['so_ngay']} ngày gần nhất)"
    chan = "CHẨN ĐOÁN SỐ BÀI\n" + "\n".join(f"- {c}" for c in bc["chan_doan"]["cau"])
    phan = [dau, _muc_chu_y(bc), _muc_pheu(bc), chan, _muc_theo_ngay(bc), _muc_nhom(bc), _muc_bo_qua(bc)]
    return "\n\n".join(p for p in phan if p) + "\n"


def luu(bc: dict, thu_muc: str) -> str:
    """Lưu bản chữ vào <thu_muc>/<ngày>.md (ghi đè báo cáo cùng ngày). Trả về đường dẫn file"""
    os.makedirs(thu_muc, exist_ok=True)
    duong_dan = os.path.join(thu_muc, f"{bc['hom_nay']}.md")
    with open(duong_dan, "w", encoding="utf-8") as f:
        f.write(bc["van_ban"])
    return duong_dan
