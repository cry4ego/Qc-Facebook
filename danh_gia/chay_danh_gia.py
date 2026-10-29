"""
ĐÁNH GIÁ hệ thống trên dữ liệu thật (eval-harness) — chạy được lại bất cứ lúc nào, mọi con số đều tính bằng code.

  A. Bộ phân loại bài viết (chủ đề → ý định MUA/BÁN → khu vực → quyết định bình luận): chạy ĐÚNG pipeline lọc của bot
     (modules.filters.POST_FILTERS, cấu hình thật, Gemini thay bằng bộ nhớ đệm thật trong CSDL nên không tốn lượt nào) trên bộ mẫu PHÂN TẦNG
     dựng từ 18 nghìn quyết định thật (danh_gia/xay_mau.py), so với nhãn của HAI người gán nhãn độc lập. Số liệu được nhân trọng số tầng
     (N_tầng / n_tầng) để ước lượng cho TOÀN production, kèm khoảng tin cậy 95% bằng bootstrap phân tầng. Ba kịch bản nhãn: chỉ ca hai người
     đồng ý ("vàng"), chỉ nhãn người 1, chỉ nhãn người 2 — các ca bất đồng chính là ca khó nên không được bỏ qua lặng lẽ.
  B. Thẻ bình luận: mẫu đang chạy thật, câu AI từng đề xuất (production), 163 mẫu cũ dài, mọi bình luận đã đăng, và các ca tấn công tổng hợp.
  C. Che thông tin (SĐT / link) khi dựng bộ mẫu: rò rỉ trên toàn bộ bài thật.

Chạy:  .\\.venv\\Scripts\\python.exe danh_gia\\chay_danh_gia.py [--csdl đường_dẫn] [--lan-lap 1000]
Ra:    danh_gia/ket_qua/AAAA-MM-DD.md (+ .json)         — tổng hợp, KHÔNG có chữ của khách
       danh_gia/du_lieu/loi_chi_tiet.md                 — từng ca sai (có trích đoạn bài; thư mục bị .gitignore)
"""
import argparse
import json
import math
import os
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GOC)
sys.path.insert(0, os.path.join(GOC, "danh_gia"))

DU_LIEU = os.path.join(GOC, "danh_gia", "du_lieu")
KET_QUA = os.path.join(GOC, "danh_gia", "ket_qua")
CSDL = os.path.join(GOC, "data", "qc_facebook.db")
NOI_DUNG = os.path.join(GOC, "Ảnh Màn-20-10", "noi-dung")
SU_THAT = os.path.join(GOC, "data", "su-that.md")
SO_NGAY_DU_LIEU = 23           # post_decisions phủ 06/10 → 29/10/2026: để đổi "số bài" thành "bài mỗi ngày"
TEN_CHU_DE = {"Màn hình": "man_hinh", "PC": "pc", "Laptop": "laptop", None: "khac"}
TEN_Y_DINH = {"MUA": "MUA", "BÁN": "BAN", "KHÔNG XÁC ĐỊNH": "KXD"}
# chữ làm bình luận dài / giống spam / lộ tên: dùng để kiểm mẫu đang chạy
CHU_THUA = re.compile(r"\bgiá\b|bảo hành|\bBH\b|qua sử dụng|1 đổi 1|inbox|nhắn|liên hệ|lưu ý|\{|hoàng|người bán|zalo|hotline", re.IGNORECASE)


# ======================================================================= tiện ích đo
def doc_jsonl(duong_dan: str) -> list[dict]:
    with open(duong_dan, encoding="utf-8") as f:
        return [json.loads(d) for d in f if d.strip()]


def ket_noi(duong_dan: str) -> sqlite3.Connection:
    """Mở CSDL CHỈ ĐỌC"""
    c = sqlite3.connect("file:" + os.path.abspath(duong_dan).replace("\\", "/") + "?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def kappa(a: list, b: list) -> float:
    """Hệ số đồng thuận Cohen giữa hai người gán nhãn (1 = hoàn toàn, 0 = như đoán mò)"""
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def trong_so_tang(tang: dict, ds_mau: list[dict]) -> list[dict]:
    """Gắn trọng số w = N_tầng / (số mẫu hợp lệ của tầng) cho từng mẫu — tổng w của một tầng luôn bằng quy mô thật của tầng"""
    dem = Counter(m["tang"] for m in ds_mau)
    return [{**m, "w": tang[m["tang"]]["tong"] / dem[m["tang"]]} for m in ds_mau]


def tong_w(ds: list[dict], dieu_kien) -> float:
    return sum(m["w"] for m in ds if dieu_kien(m))


def ti_le(tu: float, mau: float) -> float:
    return tu / mau if mau else float("nan")


def bootstrap(ds: list[dict], ham, lan_lap: int = 1000, hat_giong: int = 7) -> tuple[float, float]:
    """Khoảng tin cậy 95% bằng bootstrap PHÂN TẦNG (rút lại có hoàn lại trong từng tầng, giữ nguyên số mẫu mỗi tầng)"""
    theo_tang = defaultdict(list)
    for m in ds:
        theo_tang[m["tang"]].append(m)
    rng = random.Random(hat_giong)
    kq = []
    for _ in range(lan_lap):
        lai = [rng.choice(d) for d in theo_tang.values() for _ in d]
        v = ham(lai)
        if not math.isnan(v):
            kq.append(v)
    if len(kq) < 20:
        return float("nan"), float("nan")
    kq.sort()
    return kq[int(0.025 * len(kq))], kq[min(int(0.975 * len(kq)), len(kq) - 1)]


def khoang(ds, ham, lan_lap) -> str:
    gt = ham(ds)
    lo, hi = bootstrap(ds, ham, lan_lap)
    if math.isnan(gt):
        return "không đo được"
    return f"{gt:,.0f} (95%: {lo:,.0f}–{hi:,.0f})" if not math.isnan(lo) else f"{gt:,.0f}"


def phan_tram(gt, lo_hi=None) -> str:
    if gt is None or (isinstance(gt, float) and math.isnan(gt)):
        return "—"
    return f"{gt * 100:.1f}%" + (f" (95%: {lo_hi[0] * 100:.0f}–{lo_hi[1] * 100:.0f}%)" if lo_hi and not math.isnan(lo_hi[0]) else "")


# ======================================================================= A. bộ phân loại bài
def nen_binh_luan(chu_de: str, y_dinh: str, khu_vuc: str, nhom_ha_noi: bool, config) -> bool:
    """Theo chính sách của chủ shop: chỉ khách TÌM MUA MÀN HÌNH; khách ở xa thì bỏ; không ghi khu vực: nhóm Hà Nội vẫn bình luận,
    nhóm toàn quốc tùy thử nghiệm (REGION_REQUIRED_IN_NATIONAL_GROUPS)"""
    if chu_de != "man_hinh" or y_dinh != "MUA" or khu_vuc == "xa":
        return False
    if khu_vuc == "gan" or nhom_ha_noi:
        return True
    return not config.REGION_REQUIRED_IN_NATIONAL_GROUPS


def chay_he_thong(mau: dict, khoa_goc: str, bo_nho_ai: dict, config) -> dict:
    """Chạy đúng pipeline lọc của bot trên một bài. Gemini = bộ nhớ đệm thật (không gọi mạng)"""
    from modules.ai_intent import AiVerdict
    from modules.engagement import Engagement
    from modules.filters import POST_FILTERS, PostCandidate, run_filters

    def ai(_text):
        d = bo_nho_ai.get(khoa_goc)
        return AiVerdict(d["label"], d["reason"]) if d else None

    cand = PostCandidate(mau["van_ban"], 0, config, lambda: Engagement(0, 0, 0, known=False), ai=ai, hanoi_group=mau["nhom_ha_noi"])
    v = run_filters(POST_FILTERS, cand, config)
    r = cand.region
    return {"chu_de": TEN_CHU_DE.get(cand.topic, "khac"), "y_dinh": TEN_Y_DINH.get(cand.intent.label, "KXD"),
            "khu_vuc": "xa" if r.is_far else ("gan" if r.near else "khong_ghi"), "nen": bool(v.ok), "ly_do": v.reason}


def dung_ds_mau(csdl: str) -> dict:
    """Đọc mẫu + nhãn của hai người + kết quả hệ thống; trả về mọi thứ cần để tính"""
    from config import Config
    mau = {m["id"]: m for m in doc_jsonl(os.path.join(DU_LIEU, "mau_chua_gan_nhan.jsonl"))}
    he_cu = json.load(open(os.path.join(DU_LIEU, "mau_he_thong.json"), encoding="utf-8"))
    tang = json.load(open(os.path.join(DU_LIEU, "tang.json"), encoding="utf-8"))
    n1 = {n["id"]: n for n in doc_jsonl(os.path.join(DU_LIEU, "nhan_claude.jsonl"))}
    n2 = {n["id"]: n for n in doc_jsonl(os.path.join(DU_LIEU, "nhan_doc_lap.jsonl"))}
    c = ket_noi(csdl)
    bo_nho_ai = {r["text_key"]: {"label": r["label"], "reason": r["reason"]} for r in c.execute("SELECT text_key, label, reason FROM ai_intent")}
    c.close()
    ds = []
    for ma, m in mau.items():
        he = chay_he_thong(m, he_cu[ma]["khoa_goc"], bo_nho_ai, Config)
        ds.append({"id": ma, "tang": he_cu[ma]["tang"], "van_ban": m["van_ban"], "nhom_ha_noi": m["nhom_ha_noi"],
                   "n1": {k: n1[ma][k] for k in ("chu_de", "y_dinh", "khu_vuc")}, "n2": {k: n2[ma][k] for k in ("chu_de", "y_dinh", "khu_vuc")},
                   "he": he, "thuc_te": he_cu[ma]})
    return {"ds": ds, "tang": tang, "config": Config}


def kich_ban(ds: list[dict], ten: str, tang: dict, config) -> list[dict]:
    """Chọn bộ nhãn theo kịch bản ('vang' = chỉ ca hai người đồng ý; 'n1'; 'n2'), tính nhãn 'nen' và trọng số"""
    chon = []
    for m in ds:
        if ten == "vang":
            if m["n1"] != m["n2"]:
                continue
            nhan = m["n1"]
        else:
            nhan = m[ten]
        chon.append({**m, "nhan": nhan, "nen_dung": nen_binh_luan(nhan["chu_de"], nhan["y_dinh"], nhan["khu_vuc"], m["nhom_ha_noi"], config)})
    return trong_so_tang(tang, chon)


def nguyen_nhan_bo_sot(m: dict) -> str:
    he = m["he"]
    if he["chu_de"] != "man_hinh":
        return "hệ thống xếp sai chủ đề (không coi là màn hình)"
    if he["y_dinh"] == "BAN":
        return "hệ thống coi là bài BÁN"
    if he["y_dinh"] == "KXD":
        return "ý định không xác định (Gemini cũng không chắc / hết lượt)"
    if he["khu_vuc"] == "xa":
        return "hệ thống coi khách ở xa"
    return "khác (vd nhóm toàn quốc không ghi khu vực)"


def do_phan_loai(du_lieu: dict, lan_lap: int) -> dict:
    ds, tang, config = du_lieu["ds"], du_lieu["tang"], du_lieu["config"]
    kq = {"dong_thuan": {}, "kich_ban": {}}
    for truong in ("chu_de", "y_dinh", "khu_vuc"):
        a, b = [m["n1"][truong] for m in ds], [m["n2"][truong] for m in ds]
        kq["dong_thuan"][truong] = {"khop": sum(x == y for x, y in zip(a, b)) / len(a), "kappa": kappa(a, b)}
    kq["dong_thuan"]["ca_ba"] = sum(m["n1"] == m["n2"] for m in ds) / len(ds)
    for ten in ("vang", "n1", "n2"):
        ms = kich_ban(ds, ten, tang, config)
        he_nen, dung = (lambda m: m["he"]["nen"]), (lambda m: m["nen_dung"])
        kb = {"so_mau": len(ms), "quy_mo": sum(m["w"] for m in ms)}
        kb["recall_nen"] = (ti_le(tong_w(ms, lambda m: he_nen(m) and dung(m)), tong_w(ms, dung)),
                            bootstrap(ms, lambda s: ti_le(tong_w(s, lambda m: he_nen(m) and dung(m)), tong_w(s, dung)), lan_lap))
        kb["precision_nen"] = (ti_le(tong_w(ms, lambda m: he_nen(m) and dung(m)), tong_w(ms, he_nen)),
                               bootstrap(ms, lambda s: ti_le(tong_w(s, lambda m: he_nen(m) and dung(m)), tong_w(s, he_nen)), lan_lap))
        kb["so_khach_dung"] = khoang(ms, lambda s: tong_w(s, dung), lan_lap)
        kb["so_bo_sot"] = khoang(ms, lambda s: tong_w(s, lambda m: dung(m) and not he_nen(m)), lan_lap)
        kb["so_binh_luan_nham"] = khoang(ms, lambda s: tong_w(s, lambda m: he_nen(m) and not dung(m)), lan_lap)
        kb["bo_sot_moi_ngay"] = tong_w(ms, lambda m: dung(m) and not he_nen(m)) / SO_NGAY_DU_LIEU
        nguyen_nhan = Counter()
        for m in ms:
            if m["nen_dung"] and not m["he"]["nen"]:
                nguyen_nhan[nguyen_nhan_bo_sot(m)] += m["w"]
        kb["nguyen_nhan_bo_sot"] = dict(nguyen_nhan.most_common())
        # chủ đề màn hình
        mh_dung, mh_he = (lambda m: m["nhan"]["chu_de"] == "man_hinh"), (lambda m: m["he"]["chu_de"] == "man_hinh")
        kb["chu_de_recall"] = ti_le(tong_w(ms, lambda m: mh_dung(m) and mh_he(m)), tong_w(ms, mh_dung))
        kb["chu_de_precision"] = ti_le(tong_w(ms, lambda m: mh_dung(m) and mh_he(m)), tong_w(ms, mh_he))
        kb["chu_de_nham"] = {}
        for t in ("man_hinh", "pc", "laptop", "khac"):
            for p in ("man_hinh", "pc", "laptop", "khac"):
                kb["chu_de_nham"][f"{t}->{p}"] = tong_w(ms, lambda m, t=t, p=p: m["nhan"]["chu_de"] == t and m["he"]["chu_de"] == p)
        # ý định, chỉ trên bài đúng là màn hình
        tren_mh = [m for m in ms if mh_dung(m)]
        mua_dung, mua_he = (lambda m: m["nhan"]["y_dinh"] == "MUA"), (lambda m: m["he"]["y_dinh"] == "MUA")
        kb["y_dinh_recall_mua"] = ti_le(tong_w(tren_mh, lambda m: mua_dung(m) and mua_he(m)), tong_w(tren_mh, mua_dung))
        kb["y_dinh_precision_mua"] = ti_le(tong_w(tren_mh, lambda m: mua_dung(m) and mua_he(m)), tong_w(tren_mh, mua_he))
        kb["mua_bi_xep"] = {p: tong_w(tren_mh, lambda m, p=p: mua_dung(m) and m["he"]["y_dinh"] == p) for p in ("MUA", "BAN", "KXD")}
        # khu vực, trên bài có ghi
        co_ghi = [m for m in ms if m["nhan"]["khu_vuc"] != "khong_ghi"]
        kb["khu_vuc_chinh_xac"] = ti_le(tong_w(co_ghi, lambda m: m["nhan"]["khu_vuc"] == m["he"]["khu_vuc"]), tong_w(co_ghi, lambda m: True))
        kb["khach_xa_lot_qua"] = ti_le(tong_w(ms, lambda m: m["nhan"]["khu_vuc"] == "xa" and m["he"]["khu_vuc"] != "xa"), tong_w(ms, lambda m: m["nhan"]["khu_vuc"] == "xa"))
        # theo tầng (đếm mẫu, không trọng số: để thấy ca khó nằm ở đâu)
        kb["theo_tang"] = {}
        for t in tang:
            st = [m for m in ms if m["tang"] == t]
            if st:
                kb["theo_tang"][t] = {"mau": len(st), "sai_quyet_dinh": sum(m["he"]["nen"] != m["nen_dung"] for m in st),
                                      "bo_sot": sum(m["nen_dung"] and not m["he"]["nen"] for m in st),
                                      "nham": sum(m["he"]["nen"] and not m["nen_dung"] for m in st)}
        kq["kich_ban"][ten] = kb
    # so với quyết định thực tế lúc đó (độ lệch giữa mã hiện tại và production)
    bl_thuc = [m for m in ds if m["thuc_te"]["quyet_dinh"] in ("Bình luận", "Sẽ bình luận (chạy thử)")]
    ids_thuc = {m["id"] for m in bl_thuc}
    kq["lech_so_voi_production"] = {"bai_production_da_binh_luan": len(bl_thuc), "ma_hien_tai_van_cho_binh_luan": sum(m["he"]["nen"] for m in bl_thuc),
                                    "ma_hien_tai_cho_binh_luan_bai_production_bo_qua": sum(m["he"]["nen"] for m in ds if m["id"] not in ids_thuc)}
    return kq


# ======================================================================= B. thẻ bình luận
TAN_CONG_TU_CHOI = [   # (nhóm lỗi, thẻ có lỗi gắn vào thẻ tốt): thẻ phải bị TỪ CHỐI
    ("giá bằng số", "{TOT} Giá 2.500.000đ thôi bác"), ("giá viết tắt", "{TOT} 2m5 lấy luôn"), ("giá bằng chữ", "{TOT} giá hai triệu rưỡi"),
    ("bảo hành", "{TOT} BH 6 tháng"), ("đổi trả", "{TOT} đổi trả trong 7 ngày"), ("giao hàng", "{TOT} freeship toàn quốc"),
    ("SĐT cách chữ số", "{TOT} 0 9 0 2 1 8 9 7 5 1"), ("SĐT dấu chấm", "{TOT} 090.218.9751"), ("SĐT ký tự vô hình", "{TOT} 0902​189​751"),
    ("SĐT viết chữ", "{TOT} không chín không hai một tám chín bảy năm một"), ("SĐT sát chữ", "{TOT} ib0902189751"),
    ("zalo", "{TOT} zalo mình nhé"), ("inbox", "{TOT} inbox em nha"), ("ib", "{TOT} ib em"), ("link đầy đủ", "{TOT} https://bit.ly/abc"),
    ("link trần", "{TOT} bit.ly/abc"), ("emoji", "{TOT} 🔥"), ("họ tên đầy đủ", "{TOT} Hoàng Văn Dũng"), ("tên gọi", "{TOT} Dũng"),
    ("địa chỉ", "{TOT} 64 Cầu Diễn"), ("cam kết", "{TOT} chính hãng 100%"), ("thúc ép", "{TOT} chỉ còn 2 máy nhanh tay"),
    ("hãng khác", "{TOT} tốt hơn Dell"), ("thông số bịa: 4K", "MSI G274QPX – 27\" 4K · 240Hz · 1ms – Rapid IPS"),
    ("thông số bịa: Hz", "MSI G274QPX – 27\" 2K · 360Hz · 1ms – Rapid IPS · HDR 400"), ("thông số bịa: OLED", "MSI G274QPX – 27\" 2K · 240Hz · OLED"),
    ("tiếng Anh", "Great monitor MSI G274QPX 27 inch 2K 240Hz"), ("văn xuôi", "Bác nào cần màn chơi game thì MSI G274QPX 240Hz rất mượt nên mua nhé"),
    ("lời chào", "Chào bạn, bên mình có MSI G274QPX 27 inch 2K 240Hz"), ("thiếu mã màn", "27\" 2K · 240Hz · 1ms · Rapid IPS · HDR 400"),
    ("chỉ có mã", "MSI G274QPX"), ("quá dài", "MSI G274QPX – " + " · ".join(["27\" 2K", "240Hz", "1ms", "Rapid IPS", "HDR 400", "USB-C sạc 65W"] * 4)),
    ("giả chữ Cyrillic", "MSI G274QPX – 27\" 2K · 240Hz · 1ms – Rаpid IPS"),
]
TAN_CONG_CHAP_NHAN = [   # thẻ hợp lệ (cách trình bày khác nhau) phải được CHẤP NHẬN
    "MSI G274QPX\nCông nghệ: Rapid IPS | HDR 400 | USB-C sạc 65W\nThông số: 27\" 2K | 240Hz | 1ms", "MSI G274QPX – 27\" 2K, 240Hz, 1ms\nCông nghệ: Rapid IPS, HDR 400",
    "Mã màn: MSI G274QPX\nThông số: 27\" 2K · 240Hz · 1ms\nCông nghệ: USB-C sạc 65W · HDR 400 · Rapid IPS", "MSI G274QPX: 27\" 2K · 240Hz · 1ms · USB-C sạc 65W",
]


def do_the_binh_luan(csdl: str) -> dict:
    from cong_ty import mau_ai, su_that
    from modules import noi_dung, products
    kq = {}
    c = ket_noi(csdl)
    content = noi_dung.load(NOI_DUNG)
    cfg = content.config
    lien_he = noi_dung.lien_he_gon(cfg["nguoi_ban"], cfg["sdt"], cfg["dia_chi"])
    so = su_that.doc(SU_THAT)
    gia = su_that.gia_hop_le([{"price": sp["gia"], "new_price": ""} for sp in content.products])
    sp0 = next(sp for sp in content.products if sp["ma"] == "g274qpx")
    mau_sp0 = noi_dung.comments(content, sp0)
    thong_so = "\n".join([sp0["ten"], *(mau_ai._chi_thong_so(m.full) for m in mau_sp0)])
    da_co, ma_man = [m.full for m in mau_sp0], mau_ai._ma_may(sp0["ten"])

    def tu_choi(the):
        return mau_ai.kiem_tra_mo_dau(the, thong_so, da_co, so, gia, ma_man)

    # B1. mẫu ĐANG BẬT trong CSDL thật phải đúng chính sách thẻ ngắn
    dang_bat = c.execute("SELECT v.id, v.text, v.safe_text, p.name FROM comment_variants v JOIN products p ON p.id = v.product_id WHERE v.active = 1 AND p.active = 1").fetchall()
    loi_b1 = []
    for r in dang_bat:
        t, s = r["text"], r["safe_text"] or products.make_safe(r["text"])
        van_de = []
        if t.splitlines()[-1] != lien_he:
            van_de.append("dòng cuối không phải dòng liên hệ gọn")
        if len(t) > 190 or t.count("\n") > 4:
            van_de.append("quá dài")
        if CHU_THUA.search(t) or CHU_THUA.search(s):
            van_de.append("còn chữ thừa / họ tên")
        if products.PHONE_RE.search(s) or "Cầu Diễn" in s or "Dũng" in s:
            van_de.append("bản không SĐT còn lộ liên hệ")
        if mau_ai._ma_may(r["name"]).lower() not in t.lower().replace(" ", ""):
            van_de.append("thiếu mã màn")
        if van_de:
            loi_b1.append((r["id"], van_de))
    kq["b1_mau_dang_bat"] = {"tong": len(dang_bat), "loi": loi_b1}

    # B2. câu AI từng đề xuất trong production phải bị từ chối khi xét như một thẻ thông số
    ai_that = []
    for r in c.execute("SELECT id, loai, nguon, noi_dung, tham_so FROM de_xuat WHERE (nguon = 'ai' AND loai IN ('mau_moi', 'kich_ban_tra_loi', 'bai_dang_moi')) OR nguon = 'mau_ai'"):
        if r["nguon"] == "mau_ai" and r["tham_so"]:
            try:
                ai_that += [(r["id"], x) for x in json.loads(r["tham_so"]).get("mo_dau", [])]
            except ValueError:
                pass
        else:
            ai_that.append((r["id"], r["noi_dung"]))
    nhan_nham = [(i, x) for i, x in ai_that if not tu_choi(x)]
    kq["b2_ai_that"] = {"tong": len(ai_that), "bi_chap_nhan_nham": [(i, x[:80]) for i, x in nhan_nham]}

    # B3. mẫu cũ DÀI (đã tắt) phải bị từ chối khi xét như thẻ; và đếm bao nhiêu mẫu cũ có họ tên đầy đủ
    cu = c.execute("SELECT id, text FROM comment_variants WHERE active = 0 AND length(text) > 190").fetchall()
    chap_nhan_cu = [r["id"] for r in cu if not tu_choi(r["text"])]
    kq["b3_mau_cu_dai"] = {"tong": len(cu), "bi_chap_nhan_nham": chap_nhan_cu, "co_ho_ten_day_du": sum("Hoàng Văn Dũng" in r["text"] for r in cu)}

    # B4. bình luận ĐÃ ĐĂNG: bản "Không SĐT/địa chỉ" không được lộ liên hệ; và make_safe phải gỡ sạch liên hệ khỏi bản đầy đủ
    lo_lien_he = re.compile(r"(?<!\d)0\d{2,3}[\s.\-]?\d{3}[\s.\-]?\d{3,4}(?!\d)|Cầu Diễn|zalo|hotline", re.IGNORECASE)
    an_toan = [r["text"] for r in c.execute("SELECT DISTINCT text FROM comments WHERE variant = 'Không SĐT/địa chỉ' AND status = 'Đã đăng'")]
    day_du = [r["text"] for r in c.execute("SELECT DISTINCT text FROM comments WHERE variant = 'Đầy đủ'")]
    kq["b4_da_dang"] = {"an_toan_tong": len(an_toan), "an_toan_lo_lien_he": [t[:70] for t in an_toan if lo_lien_he.search(t)],
                        "day_du_tong": len(day_du), "day_du_con_lien_he_sau_make_safe": [t[:70] for t in day_du if lo_lien_he.search(products.make_safe(t))],
                        "da_dang_co_ho_ten_day_du": c.execute("SELECT COUNT(*) FROM comments WHERE text LIKE '%Hoàng Văn Dũng%' AND status = 'Đã đăng'").fetchone()[0]}

    # B5. ca tấn công tổng hợp
    tot = mau_sp0[1].full.rsplit("\n", 1)[0]          # một thẻ tốt (bỏ dòng liên hệ)
    sai_tu_choi, sai_chap_nhan = [], []
    for nhom, mau in TAN_CONG_TU_CHOI:
        if not tu_choi(mau.replace("{TOT}", tot)):
            sai_tu_choi.append(nhom)
    for the in TAN_CONG_CHAP_NHAN:
        van_de = tu_choi(the)
        if van_de:
            sai_chap_nhan.append((the[:60], list(van_de[:2])))
    kq["b5_tan_cong"] = {"tu_choi_tong": len(TAN_CONG_TU_CHOI), "bi_lot_qua": sai_tu_choi, "chap_nhan_tong": len(TAN_CONG_CHAP_NHAN), "bi_tu_choi_nham": sai_chap_nhan}
    c.close()
    return kq


# ======================================================================= C. che thông tin
def do_che_thong_tin(csdl: str) -> dict:
    from xay_mau import che_thong_tin
    c = ket_noi(csdl)
    van_ban = [r[0] or "" for r in c.execute("SELECT post_text FROM post_decisions")]
    c.close()
    chuoi_so = re.compile(r"(?:\d[\s.\-]?){9,}")
    # dạng người ta thật sự viết SĐT: liền nhau 9–11 số, hoặc các nhóm 3–4 số nối bằng dấu cách / chấm / gạch (KHÔNG xuống dòng)
    di_dong_vn = re.compile(r"(?<!\d)(?:(?:\d{3,4}[ .\-]){1,3}\d{2,4}|\d{9,11})(?!\d)")

    def giong_sdt(t: str) -> bool:
        """Còn một chuỗi 9–11 chữ số có dạng số di động Việt Nam (0/84 + 3,5,7,8,9 + 8 số, hoặc thiếu số 0 đầu)"""
        return any(re.fullmatch(r"(?:84|0)?[35789]\d{8}", re.sub(r"\D", "", m.group(0))) for m in di_dong_vn.finditer(t))

    co_so = [t for t in van_ban if chuoi_so.search(t)]
    sau_che = [che_thong_tin(t) for t in co_so]
    return {"tong_bai": len(van_ban), "bai_co_chuoi_9_so": len(co_so),
            "van_con_chuoi_9_so_sau_khi_che": sum(bool(chuoi_so.search(t)) for t in sau_che),
            "van_con_giong_sdt_sau_khi_che": sum(giong_sdt(t) for t in sau_che)}


# ======================================================================= báo cáo
LY_DO_TANG = {"R_trong_hoac_qua_ngan": "bài chỉ có ảnh / vài chữ", "T_chu_de_khac_co_chu_man": "xếp PC/laptop nhưng chữ có \"màn\", \"monitor\", \"27 inch\" → nghi bỏ sót màn hình",
              "T_chu_de_khac": "phần lớn production: laptop, PC, linh kiện, không liên quan", "M_da_binh_luan": "bài hệ thống đã bình luận → đo bình luận nhầm",
              "M_mua_nhung_bo_qua": "xếp MUA nhưng bị bỏ (khách xa, không lấy được link…)", "M_khong_xac_dinh": "từ khóa không chắc, Gemini cũng không chắc",
              "M_ban_do_ai": "Gemini phân xử là BÁN", "M_ban_co_dau_hieu_mua": "xếp BÁN nhưng chữ có \"cần/tìm/mua/ai có…\" → nghi bỏ sót người mua",
              "M_ban_khac": "BÁN theo từ khóa, không dấu hiệu mua", "M_khac": "còn lại"}


def viet_bao_cao(a: dict, b: dict, c: dict, du_lieu: dict, lan_lap: int) -> str:
    tang = du_lieu["tang"]
    v, n1, n2 = a["kich_ban"]["vang"], a["kich_ban"]["n1"], a["kich_ban"]["n2"]
    b1, b2, b3, b4, b5 = b["b1_mau_dang_bat"], b["b2_ai_that"], b["b3_mau_cu_dai"], b["b4_da_dang"], b["b5_tan_cong"]
    L = []
    w = L.append
    w(f"# Báo cáo đánh giá hệ thống — {date.today().isoformat()}\n")
    w("> Tạo tự động bởi `danh_gia/chay_danh_gia.py`. Mọi con số tính bằng code từ dữ liệu thật; không có số nào do AI \"ước chừng\".\n")
    w("## 1. Tóm tắt — đọc phần này trước\n")
    w(f"Bộ mẫu: **{sum(t['mau'] for t in tang.values())} bài thật** rút từ **{sum(t['tong'] for t in tang.values()):,} bài** hệ thống đã xét (06/10 → 29/10/2026), "
      "lấy mẫu phân tầng nên số liệu dưới đây là ước lượng cho TOÀN production, không phải chỉ cho các bài trong mẫu.\n")
    w("| Câu hỏi | Kết quả (ca hai người gán nhãn đồng ý) | Nếu tính theo nhãn từng người |")
    w("|---|---|---|")
    w(f"| Trong số khách THẬT SỰ nên bình luận, hệ thống bắt được bao nhiêu? (recall) | **{phan_tram(*v['recall_nen'])}** | {phan_tram(n1['recall_nen'][0])} / {phan_tram(n2['recall_nen'][0])} |")
    w(f"| Trong số bài hệ thống chọn bình luận, bao nhiêu là khách thật? (precision) | **{phan_tram(*v['precision_nen'])}** | {phan_tram(n1['precision_nen'][0])} / {phan_tram(n2['precision_nen'][0])} |")
    w(f"| Ước tính số khách đáng bình luận trong 23 ngày | {v['so_khach_dung']} | {n1['so_khach_dung']} / {n2['so_khach_dung']} |")
    w(f"| Ước tính số khách BỎ SÓT trong 23 ngày | **{v['so_bo_sot']}** (≈ {v['bo_sot_moi_ngay']:.1f} khách/ngày) | {n1['bo_sot_moi_ngay']:.1f} / {n2['bo_sot_moi_ngay']:.1f} khách/ngày |")
    w(f"| Ước tính số bài bình luận NHẦM (không phải khách) trong 23 ngày | {v['so_binh_luan_nham']} | {n1['so_binh_luan_nham']} / {n2['so_binh_luan_nham']} |\n")
    w(f"Thẻ bình luận: mẫu đang chạy đạt chính sách **{b1['tong'] - len(b1['loi'])}/{b1['tong']}**; câu AI từng đề xuất ở production bị từ chối đúng "
      f"**{b2['tong'] - len(b2['bi_chap_nhan_nham'])}/{b2['tong']}**; ca tấn công tổng hợp bị chặn đúng **{b5['tu_choi_tong'] - len(b5['bi_lot_qua'])}/{b5['tu_choi_tong']}**.\n")
    w("## 2. Bộ mẫu phản ánh phân phối thật như thế nào\n")
    w("Mỗi tầng giữ đúng quy mô thật; mẫu được lấy dư ở các tầng ca khó (nơi lỗi thường nằm) rồi nhân trọng số `N_tầng / n_tầng` để ước lượng đúng cho toàn bộ.\n")
    w("| Tầng (loại bài) | Số bài thật | Số mẫu | Mỗi mẫu đại diện | Vì sao có tầng này |")
    w("|---|---:|---:|---:|---|")
    for t, d in tang.items():
        if d["tong"]:
            w(f"| `{t}` | {d['tong']:,} | {d['mau']} | {d['tong'] / max(d['mau'], 1):.0f} bài | {LY_DO_TANG.get(t, '')} |")
    w("\n## 3. Chất lượng nhãn (hai người gán nhãn độc lập)\n")
    dt = a["dong_thuan"]
    w("| Trường | Khớp nhau | Hệ số đồng thuận kappa |")
    w("|---|---:|---:|")
    for k, ten in (("chu_de", "Chủ đề"), ("y_dinh", "Ý định (MUA/BÁN/KHÁC)"), ("khu_vuc", "Khu vực")):
        w(f"| {ten} | {dt[k]['khop'] * 100:.1f}% | {dt[k]['kappa']:.2f} |")
    w(f"| Cả ba trường cùng khớp | {dt['ca_ba'] * 100:.1f}% | — |\n")
    w("Kappa ≥ 0,8 là rất đồng thuận, 0,6–0,8 là tốt. **Những ca hai người bất đồng được giữ lại** (không xóa) và đo riêng ở kịch bản nhãn từng người, vì đó thường là ca khó thật sự.\n")
    w("## 4. Kết quả bộ phân loại bài\n")
    w(f"Khoảng tin cậy tính bằng bootstrap phân tầng ({lan_lap} lần). Kịch bản \"vàng\" chỉ gồm {v['so_mau']} ca hai người đồng ý.\n")
    w("### 4.1 Chủ đề màn hình\n")
    w(f"- Bắt đúng bài về màn hình (recall): vàng **{phan_tram(v['chu_de_recall'])}**, người 1 {phan_tram(n1['chu_de_recall'])}, người 2 {phan_tram(n2['chu_de_recall'])}")
    w(f"- Trong bài hệ thống gọi là màn hình, đúng thật (precision): vàng **{phan_tram(v['chu_de_precision'])}**")
    w("- Ma trận nhầm lẫn (ước lượng số bài trong 23 ngày, kịch bản vàng; hàng = nhãn đúng, cột = hệ thống):\n")
    w("| đúng \\ hệ thống | màn hình | pc | laptop | khác |")
    w("|---|---:|---:|---:|---:|")
    for t in ("man_hinh", "pc", "laptop", "khac"):
        w(f"| {t} | " + " | ".join(f"{v['chu_de_nham'][f'{t}->{p}']:,.0f}" for p in ("man_hinh", "pc", "laptop", "khac")) + " |")
    w("\n### 4.2 Ý định MUA (chỉ tính bài đúng là về màn hình)\n")
    w(f"- Nhận ra người MUA (recall): vàng **{phan_tram(v['y_dinh_recall_mua'])}**, người 1 {phan_tram(n1['y_dinh_recall_mua'])}, người 2 {phan_tram(n2['y_dinh_recall_mua'])}")
    w(f"- Trong bài hệ thống gọi là MUA, đúng thật (precision): vàng **{phan_tram(v['y_dinh_precision_mua'])}**")
    tong_mua = sum(v["mua_bi_xep"].values()) or 1
    w(f"- Người MUA thật bị xếp thành: MUA {v['mua_bi_xep']['MUA'] / tong_mua * 100:.0f}% · BÁN {v['mua_bi_xep']['BAN'] / tong_mua * 100:.0f}% · không xác định {v['mua_bi_xep']['KXD'] / tong_mua * 100:.0f}%\n")
    w("### 4.3 Khu vực\n")
    w(f"- Đọc đúng khu vực (trên bài có ghi): vàng **{phan_tram(v['khu_vuc_chinh_xac'])}**")
    w(f"- Khách ở xa lọt qua bộ lọc (bình luận nhầm khách xa): vàng {phan_tram(v['khach_xa_lot_qua'])}\n")
    w("### 4.4 Nguyên nhân bỏ sót khách\n")
    w("| Nguyên nhân (ước lượng số bài / 23 ngày, kịch bản vàng) | Số bài |")
    w("|---|---:|")
    for k, x in v["nguyen_nhan_bo_sot"].items():
        w(f"| {k} | {x:,.0f} |")
    if not v["nguyen_nhan_bo_sot"]:
        w("| (không có ca bỏ sót trong mẫu vàng) | 0 |")
    w("\n### 4.5 Sai ở tầng nào (đếm mẫu, kịch bản vàng) — cho thấy ca khó nằm đâu\n")
    w("| Tầng | Số mẫu | Quyết định sai | Bỏ sót khách | Bình luận nhầm |")
    w("|---|---:|---:|---:|---:|")
    for t, d in v["theo_tang"].items():
        w(f"| `{t}` | {d['mau']} | {d['sai_quyet_dinh']} | {d['bo_sot']} | {d['nham']} |")
    ls = a["lech_so_voi_production"]
    w("\n### 4.6 Mã hiện tại so với production lúc đó\n")
    w(f"Trong mẫu có {ls['bai_production_da_binh_luan']} bài production đã bình luận; mã hiện tại vẫn cho bình luận {ls['ma_hien_tai_van_cho_binh_luan']} bài trong số đó. "
      f"Ngược lại mã hiện tại cho bình luận thêm {ls['ma_hien_tai_cho_binh_luan_bai_production_bo_qua']} bài mà production đã bỏ (do bước tương tác / lấy link / thử nghiệm khu vực / lọc cũ hơn, ngoài phạm vi bộ lọc này).\n")
    w("## 5. Thẻ bình luận\n")
    w("| Kiểm tra | Kết quả |")
    w("|---|---|")
    w(f"| B1. Mẫu ĐANG BẬT trong CSDL thật đúng chính sách (dòng liên hệ gọn, ngắn, không họ tên, bản không SĐT sạch) | {b1['tong'] - len(b1['loi'])}/{b1['tong']} đạt |")
    w(f"| B2. Câu do AI đề xuất ở production bị từ chối khi xét như thẻ | {b2['tong'] - len(b2['bi_chap_nhan_nham'])}/{b2['tong']} bị từ chối đúng |")
    w(f"| B3. Mẫu cũ dài (đã tắt) bị từ chối khi xét như thẻ | {b3['tong'] - len(b3['bi_chap_nhan_nham'])}/{b3['tong']} bị từ chối đúng; {b3['co_ho_ten_day_du']} mẫu cũ có họ tên đầy đủ |")
    w(f"| B4a. Bình luận ĐÃ ĐĂNG bản \"Không SĐT/địa chỉ\" không lộ liên hệ | {b4['an_toan_tong'] - len(b4['an_toan_lo_lien_he'])}/{b4['an_toan_tong']} sạch |")
    w(f"| B4b. `make_safe` gỡ sạch liên hệ khỏi bản đầy đủ đã đăng | {b4['day_du_tong'] - len(b4['day_du_con_lien_he_sau_make_safe'])}/{b4['day_du_tong']} sạch |")
    w(f"| B4c. Bình luận đã đăng có họ tên đầy đủ \"Hoàng Văn Dũng\" (lý do bạn bỏ tên) | {b4['da_dang_co_ho_ten_day_du']} bình luận |")
    w(f"| B5a. Ca tấn công tổng hợp (giá, SĐT che giấu, link, Cyrillic, thông số bịa…) bị chặn | {b5['tu_choi_tong'] - len(b5['bi_lot_qua'])}/{b5['tu_choi_tong']} |")
    w(f"| B5b. Thẻ hợp lệ nhiều kiểu trình bày được chấp nhận | {b5['chap_nhan_tong'] - len(b5['bi_tu_choi_nham'])}/{b5['chap_nhan_tong']} |\n")
    for nhan, du in (("B1 lỗi", b1["loi"][:5]), ("B2 — AI viết mà LẼ RA phải từ chối nhưng đã chấp nhận", b2["bi_chap_nhan_nham"][:5]),
                     ("B3 — mẫu cũ dài bị chấp nhận nhầm (id)", b3["bi_chap_nhan_nham"][:10]), ("B4a — bản không SĐT đã đăng nhưng còn liên hệ", b4["an_toan_lo_lien_he"][:5]),
                     ("B4b — make_safe để sót liên hệ", b4["day_du_con_lien_he_sau_make_safe"][:5]), ("B5a — ca tấn công LỌT QUA bộ chặn", b5["bi_lot_qua"]),
                     ("B5b — thẻ hợp lệ bị từ chối nhầm", b5["bi_tu_choi_nham"])):
        if du:
            w(f"- **{nhan}:** {du}")
    w("\n## 6. Che thông tin khi dựng bộ mẫu\n")
    w(f"Trong {c['tong_bai']:,} bài thật có {c['bai_co_chuoi_9_so']:,} bài chứa chuỗi ≥ 9 chữ số (SĐT hoặc giống SĐT). Sau khi che, còn **{c['van_con_giong_sdt_sau_khi_che']}** bài vẫn còn chuỗi giống số di động Việt Nam "
      f"(thước đo chính). Thước đo thô \"≥ 9 chữ số bất kỳ\" còn {c['van_con_chuoi_9_so_sau_khi_che']} bài, nhưng khi xem tay thì đó là thông số máy (`7 10750 1650` = i7-10750H + GTX 1650, `CL32-39-39-102`), năm, giá và mã số dài — không phải SĐT. Thước đo chính chỉ nhận dạng viết thật của SĐT (liền nhau, hoặc nhóm 3–4 số nối bằng dấu cách / chấm / gạch, không xuống dòng).\n")
    w("## 7. Giới hạn — đọc kỹ trước khi tin\n")
    w("- **Nhãn do hai \"người\" gán, đều là AI** (một phiên của tôi và một agent độc lập). Chúng độc lập với nhau và với hệ thống, nhưng không phải chủ shop. Bạn nên tự xem `danh_gia/du_lieu/loi_chi_tiet.md` (từng ca sai kèm bài, và các ca hai người bất đồng) và cho biết chỗ nào bạn gán khác.")
    w("- **Mẫu nhỏ ở tầng hiếm** (vd tầng \"không xác định\" chỉ có vài chục bài thật nên gần như lấy hết); khoảng tin cậy ở trên đã phản ánh điều đó — khoảng rộng nghĩa là chưa đủ dữ liệu để kết luận chắc.")
    w("- **Gemini không được gọi lại**: dùng bộ nhớ đệm thật, nên bài chưa có trong bộ nhớ đệm mà từ khóa không chắc sẽ ra \"không xác định\" (giống production khi hết lượt).")
    w("- **Chưa đo hiệu quả bán hàng**: chưa có dòng khách nào được ghi ở tab Công ty AI, nên mọi số liệu ở đây là chất lượng bộ lọc, không phải doanh thu.")
    w(f"- Trọng số theo tầng, bootstrap {lan_lap} lần, hạt giống cố định: chạy lại cho cùng kết quả.")
    return "\n".join(L) + "\n"


def viet_loi_chi_tiet(du_lieu: dict) -> str:
    """Từng ca hệ thống sai (kịch bản vàng) kèm trích đoạn bài — chỉ ghi vào thư mục đã .gitignore"""
    ms = kich_ban(du_lieu["ds"], "vang", du_lieu["tang"], du_lieu["config"])
    bo_sot = [m for m in ms if m["nen_dung"] and not m["he"]["nen"]]
    nham = [m for m in ms if m["he"]["nen"] and not m["nen_dung"]]
    bat_dong = [m for m in du_lieu["ds"] if m["n1"] != m["n2"]]
    L = ["# Ca sai chi tiết (có trích đoạn bài của khách — KHÔNG đưa lên git)\n", f"## Bỏ sót khách ({len(bo_sot)} ca trong mẫu vàng)\n"]
    for m in bo_sot:
        L.append(f"- **{m['id']}** [{m['tang']}] mỗi mẫu đại diện {m['w']:.0f} bài · nguyên nhân: {nguyen_nhan_bo_sot(m)} · hệ thống: {m['he']['chu_de']}/{m['he']['y_dinh']}/{m['he']['khu_vuc']}\n  > {' '.join(m['van_ban'].split())[:220]}")
    L.append(f"\n## Bình luận nhầm ({len(nham)} ca)\n")
    for m in nham:
        L.append(f"- **{m['id']}** [{m['tang']}] mỗi mẫu đại diện {m['w']:.0f} bài · nhãn đúng: {m['nhan']['chu_de']}/{m['nhan']['y_dinh']}/{m['nhan']['khu_vuc']}\n  > {' '.join(m['van_ban'].split())[:220]}")
    L.append(f"\n## Hai người gán nhãn bất đồng ({len(bat_dong)} ca) — cần bạn quyết\n")
    for m in bat_dong:
        khac = [k for k in ("chu_de", "y_dinh", "khu_vuc") if m["n1"][k] != m["n2"][k]]
        L.append(f"- **{m['id']}** khác ở {', '.join(khac)} · người 1: {m['n1']} · người 2: {m['n2']} · hệ thống: {m['he']['chu_de']}/{m['he']['y_dinh']}/{m['he']['khu_vuc']}\n  > {' '.join(m['van_ban'].split())[:220]}")
    return "\n".join(L) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--csdl", default=CSDL)
    ap.add_argument("--lan-lap", type=int, default=1000)
    args = ap.parse_args(argv)
    if not os.path.exists(os.path.join(DU_LIEU, "nhan_doc_lap.jsonl")):
        print("Chưa có bộ mẫu / nhãn: chạy danh_gia/xay_mau.py rồi gán nhãn (nhan_claude.jsonl, nhan_doc_lap.jsonl) trước.")
        return 1
    du_lieu = dung_ds_mau(args.csdl)
    a, b, c = do_phan_loai(du_lieu, args.lan_lap), do_the_binh_luan(args.csdl), do_che_thong_tin(args.csdl)
    os.makedirs(KET_QUA, exist_ok=True)
    ten = date.today().isoformat()
    with open(os.path.join(KET_QUA, f"{ten}.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(viet_bao_cao(a, b, c, du_lieu, args.lan_lap))
    with open(os.path.join(KET_QUA, f"{ten}.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"phan_loai": a, "the_binh_luan": b, "che_thong_tin": c}, f, ensure_ascii=False, indent=1, default=str)
    with open(os.path.join(DU_LIEU, "loi_chi_tiet.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(viet_loi_chi_tiet(du_lieu))
    print(f"Đã ghi danh_gia/ket_qua/{ten}.md (+ .json) và danh_gia/du_lieu/loi_chi_tiet.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
