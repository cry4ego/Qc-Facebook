"""
Dựng bộ mẫu ĐÁNH GIÁ bộ phân loại bài viết từ CSDL THẬT (chỉ đọc), theo lấy mẫu PHÂN TẦNG để phản ánh phân phối production:

  - Chia toàn bộ bảng post_decisions (mọi bài hệ thống đã xét) thành các TẦNG loại trừ nhau, mỗi tầng giữ đúng quy mô thật (N_tầng).
  - Rút ngẫu nhiên n_tầng bài từ mỗi tầng (hạt giống cố định -> dựng lại được). Mỗi mẫu có trọng số N_tầng / n_tầng, nên số liệu ước lượng
    cho TOÀN production dù đã lấy dư các tầng ca khó (bài bị coi là BÁN nhưng có dấu hiệu người mua, bài Gemini phải phân xử, bài trống…).

Chạy:  .\\.venv\\Scripts\\python.exe danh_gia\\xay_mau.py [--hat-giong N]
Sinh ra trong danh_gia/du_lieu/ (bị .gitignore: chứa bài thật của khách, dù đã che SĐT / link / email):
  mau_chua_gan_nhan.jsonl   {id, van_ban, ten_nhom, nhom_ha_noi}   — đưa cho người gán nhãn (KHÔNG có kết quả của hệ thống)
  mau_he_thong.json         {id: {tang, khoa_goc, chu_de, y_dinh, quyet_dinh, ly_do}} — những gì hệ thống đã làm lúc đó (để so sánh)
  tang.json                 {tên tầng: {tong, mau}} — quy mô thật của từng tầng, để tính trọng số
"""
import argparse
import json
import os
import random
import re
import sqlite3
import sys

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GOC)

THU_MUC_DU_LIEU = os.path.join(GOC, "danh_gia", "du_lieu")
CSDL_MAC_DINH = os.path.join(GOC, "data", "qc_facebook.db")
HAT_GIONG = 20261029

# Số bài lấy ở mỗi tầng. Tầng ca khó được lấy dư (so với tỷ lệ thật) vì ở đó mới có lỗi để đo; trọng số bù lại.
MAU_MOI_TANG = {
    "R_trong_hoac_qua_ngan": 15,       # bài chỉ có ảnh / một-hai chữ: không có gì để phân loại
    "T_chu_de_khac_co_chu_man": 40,    # hệ thống xếp PC/Laptop/khác NHƯNG chữ có "màn", "monitor", "27 inch"… -> nghi bỏ sót màn hình
    "T_chu_de_khac": 40,               # phần lớn production: laptop, PC, linh kiện, không liên quan
    "M_da_binh_luan": 40,              # hệ thống đã quyết định bình luận -> đo độ chính xác (có bình luận nhầm bài BÁN không?)
    "M_mua_nhung_bo_qua": 40,          # xếp là MUA nhưng bị bỏ (khách ở xa, không lấy được link…)
    "M_khong_xac_dinh": 40,            # từ khóa không chắc, Gemini không phân xử được
    "M_ban_do_ai": 30,                 # Gemini phân xử là BÁN
    "M_ban_co_dau_hieu_mua": 40,       # từ khóa xếp BÁN nhưng chữ có "cần / tìm / mua / ai có…" -> nghi bỏ sót người mua
    "M_ban_khac": 40,                  # BÁN theo từ khóa, không có dấu hiệu mua (phần đông)
    "M_khac": 15,                      # còn lại của chủ đề màn hình
}
CHU_MAN_HINH = re.compile(r"màn|man hinh|monitor|\bmh\b|\d+\s?hz\b|\binch\b|\d{2}\s?in\b|lcd|\bips\b", re.IGNORECASE)
DAU_HIEU_MUA = re.compile(r"\b(cần|tìm|muốn|kiếm|xin|ai có|có ai|cho hỏi|tư vấn|mua giúp|nhờ)\b|cần mua|muốn mua|tìm mua", re.IGNORECASE)
# SĐT: có thể dính liền chữ ("zalo0388…"), viết thiếu số 0 đầu ("912000111", "987-000-222"), hoặc tách từng chữ số ("0 9 0 2…")
SDT = re.compile(r"(?<!\d)(?:(?:\+?84|0)(?:[\s.\-]?\d){8,10}|[35789]\d{2}[\s.\-]?\d{3}[\s.\-]?\d{3})(?!\d)")
LINK = re.compile(r"https?://\S+|www\.\S+|\b\S+\.(?:com|vn|me|net|gl)/\S*", re.IGNORECASE)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def che_thong_tin(text: str) -> str:
    """Che SĐT, link, email trước khi ghi ra bộ mẫu (tên riêng trong bài thì không che được nên dữ liệu vẫn không được đưa lên git)"""
    text = EMAIL.sub("<EMAIL>", text or "")
    text = LINK.sub("<LINK>", text)
    return SDT.sub("<SĐT>", text)


def ket_noi(duong_dan: str) -> sqlite3.Connection:
    """Mở CSDL CHỈ ĐỌC (không bao giờ ghi vào dữ liệu thật)"""
    c = sqlite3.connect("file:" + os.path.abspath(duong_dan).replace("\\", "/") + "?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def xep_tang(r) -> str:
    """Tầng của một dòng post_decisions (loại trừ nhau; khớp tầng nào trước thì vào tầng đó)"""
    van_ban = (r["post_text"] or "").strip()
    chu_de, y_dinh, ly_do = r["topic"], r["intent"], r["reason"] or ""
    if len(van_ban) < 15:
        return "R_trong_hoac_qua_ngan"
    if chu_de != "Màn hình":
        return "T_chu_de_khac_co_chu_man" if CHU_MAN_HINH.search(van_ban) else "T_chu_de_khac"
    if r["decision"] in ("Bình luận", "Sẽ bình luận (chạy thử)"):
        return "M_da_binh_luan"
    if y_dinh == "MUA":
        return "M_mua_nhung_bo_qua"
    if y_dinh == "KHÔNG XÁC ĐỊNH":
        return "M_khong_xac_dinh"
    if y_dinh == "BÁN":
        if "AI Gemini" in ly_do:
            return "M_ban_do_ai"
        return "M_ban_co_dau_hieu_mua" if DAU_HIEU_MUA.search(van_ban) else "M_ban_khac"
    return "M_khac"


def dung_mau(duong_dan_csdl: str, hat_giong: int = HAT_GIONG) -> tuple[list[dict], dict, dict]:
    """(danh sách mẫu chưa gán nhãn, kết quả hệ thống theo id, quy mô các tầng)"""
    from modules.group_finder import is_hanoi_group
    c = ket_noi(duong_dan_csdl)
    rows = c.execute("SELECT id, group_name, text_key, post_text, topic, intent, decision, reason FROM post_decisions ORDER BY id").fetchall()
    c.close()
    theo_tang: dict[str, list] = {t: [] for t in MAU_MOI_TANG}
    for r in rows:
        theo_tang[xep_tang(r)].append(r)
    rng = random.Random(hat_giong)
    chua_nhan, he_thong, tang = [], {}, {}
    for ten, ds in theo_tang.items():
        chon = rng.sample(ds, min(MAU_MOI_TANG[ten], len(ds)))
        tang[ten] = {"tong": len(ds), "mau": len(chon)}
        for r in chon:
            chua_nhan.append({"van_ban": che_thong_tin(r["post_text"] or ""), "ten_nhom": r["group_name"] or "",
                              "nhom_ha_noi": is_hanoi_group({"group_name": r["group_name"] or ""}), "_tang": ten, "_id": r["id"]})
            he_thong[r["id"]] = {"tang": ten, "khoa_goc": r["text_key"], "chu_de": r["topic"], "y_dinh": r["intent"],
                                 "quyet_dinh": r["decision"], "ly_do": (r["reason"] or "")[:160]}
    rng.shuffle(chua_nhan)                                  # xáo để người gán nhãn không đoán được tầng theo thứ tự
    mau = []
    ket_qua = {}
    for i, m in enumerate(chua_nhan, 1):
        ma = f"S{i:03d}"
        mau.append({"id": ma, "van_ban": m["van_ban"], "ten_nhom": m["ten_nhom"], "nhom_ha_noi": m["nhom_ha_noi"]})
        ket_qua[ma] = he_thong[m["_id"]]
    return mau, ket_qua, tang


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--csdl", default=CSDL_MAC_DINH)
    ap.add_argument("--hat-giong", type=int, default=HAT_GIONG)
    args = ap.parse_args(argv)
    mau, he_thong, tang = dung_mau(args.csdl, args.hat_giong)
    os.makedirs(THU_MUC_DU_LIEU, exist_ok=True)
    with open(os.path.join(THU_MUC_DU_LIEU, "mau_chua_gan_nhan.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in mau))
    for ten, du_lieu in (("mau_he_thong.json", he_thong), ("tang.json", tang)):
        with open(os.path.join(THU_MUC_DU_LIEU, ten), "w", encoding="utf-8", newline="\n") as f:
            json.dump(du_lieu, f, ensure_ascii=False, indent=1)
    print(f"Đã dựng {len(mau)} mẫu từ {sum(t['tong'] for t in tang.values())} bài thật:")
    for ten, t in tang.items():
        print(f"  {ten:28} {t['tong']:6} bài thật  ->  {t['mau']:3} mẫu  (mỗi mẫu đại diện {t['tong'] / max(t['mau'], 1):.0f} bài)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
