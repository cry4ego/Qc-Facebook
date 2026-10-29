"""
Kiểm tra VẬN HÀNH (chỉ ĐỌC, không tắt / bật gì): 6 cửa sổ của bot có đang chạy không, và có đang chạy MÃ CŨ không.

Sự cố thật 28/10/2026: sửa code xong nhưng cửa sổ họp và web vẫn là tiến trình cũ giữ mã cũ trong bộ nhớ — nên đề xuất mới vẫn sinh theo khuôn cũ
và nút "Đồng ý và làm luôn" vẫn chạy mã cũ. Công cụ này so thời điểm KHỞI ĐỘNG của từng tiến trình với thời điểm sửa file code mà nó dùng.

Chạy:  .\\.venv\\Scripts\\python.exe tools\\kiem_tra_van_hanh.py
Thoát: 0 = mọi cửa sổ đang chạy mã mới; 1 = có cửa sổ tắt hoặc đang chạy mã cũ (cần khởi động lại).
"""
import os
import sqlite3
import sys
from datetime import datetime

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSDL = os.path.join(GOC, "data", "qc_facebook.db")
CAY_CHUNG = ("modules", "config.py")
# tên cửa sổ -> (lệnh: tên file + các tham số, nơi chứa code mà cửa sổ đó dùng)
CUA_SO = {
    "Bình luận": (("main.py",), CAY_CHUNG + ("main.py",)),
    "Web quản lý": (("web.py",), CAY_CHUNG + ("cong_ty", "web.py")),
    "Họp sáng (công ty AI)": (("main.py", "hopngam"), CAY_CHUNG + ("cong_ty", "main.py")),
    "Quét 1": (("main.py", "quet"), CAY_CHUNG + ("main.py",)),
    "Quét 2": (("main.py", "quet", "2"), CAY_CHUNG + ("main.py",)),
    "Khám phá nhóm": (("main.py", "khampha"), CAY_CHUNG + ("main.py",)),
}


def chu_ky_lenh(cmdline: list[str]) -> tuple[str, ...]:
    """('python.exe', 'main.py', 'quet', '2') -> ('main.py', 'quet', '2'); không phải main.py / web.py thì ()"""
    for i, tok in enumerate(cmdline):
        if os.path.basename(tok) in ("main.py", "web.py"):
            return (os.path.basename(tok), *cmdline[i + 1:])
    return ()


def sua_code_moi_nhat(cay: tuple[str, ...], goc: str = GOC) -> tuple[float, str]:
    """(thời điểm, tên file) của file .py được sửa gần nhất trong các nơi `cay` (thư mục hoặc file lẻ, tính từ gốc dự án)"""
    moi = (0.0, "")
    for muc in cay:
        duong_dan = os.path.join(goc, muc)
        if os.path.isfile(duong_dan):
            ds = [duong_dan]
        else:
            ds = [os.path.join(d, f) for d, _, fs in os.walk(duong_dan) if "__pycache__" not in d for f in fs if f.endswith(".py")]
        for f in ds:
            t = os.path.getmtime(f)
            if t > moi[0]:
                moi = (t, os.path.relpath(f, goc))
    return moi


def danh_gia_cua_so(tien_trinh: list[dict], sua_moi_nhat: dict[str, tuple[float, str]]) -> list[dict]:
    """Mỗi cửa sổ mong đợi -> trạng thái. tien_trinh: [{cmd: tuple, bat_dau: timestamp}] (chỉ tiến trình python của dự án).
    Trạng thái: 'tat' (không thấy tiến trình), 'cu' (khởi động TRƯỚC lần sửa code gần nhất), 'moi'. 'chay_trung' = có hơn một cặp
    tiến trình cách nhau > 10 phút (mỗi cửa sổ bình thường là 1 cặp: tiến trình cha của venv + tiến trình con, khởi động sát nhau)"""
    kq = []
    for ten, (lenh, _cay) in CUA_SO.items():
        cua = sorted(t["bat_dau"] for t in tien_trinh if t["cmd"] == lenh)
        if not cua:
            kq.append({"cua_so": ten, "trang_thai": "tat", "bat_dau": None, "chay_trung": False, "file_sua_sau": ""})
            continue
        t_sua, file_sua = sua_moi_nhat[ten]
        cu = cua[0] < t_sua                                   # tiến trình cha khởi động sớm nhất: nếu nó đã cũ thì cả cửa sổ cũ
        kq.append({"cua_so": ten, "trang_thai": "cu" if cu else "moi", "bat_dau": cua[0],
                   "chay_trung": any(b - a > 600 for a, b in zip(cua, cua[1:])), "file_sua_sau": file_sua if cu else ""})
    return kq


def tien_trinh_du_an() -> list[dict]:
    import psutil
    ds = []
    for p in psutil.process_iter(["cmdline", "create_time", "name"]):
        try:
            lenh = chu_ky_lenh(p.info["cmdline"] or [])
            if not lenh or "python" not in (p.info["name"] or "").lower():
                continue
            cua_du_an = GOC.lower() in " ".join(p.info["cmdline"]).lower() or os.path.normcase(p.cwd()) == os.path.normcase(GOC)
            if cua_du_an:
                ds.append({"cmd": lenh, "bat_dau": p.info["create_time"]})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return ds


def doc_csdl() -> dict:
    """Vài mốc 'sống' từ CSDL (chỉ đọc)"""
    if not os.path.exists(CSDL):
        return {}
    c = sqlite3.connect("file:" + CSDL.replace("\\", "/") + "?mode=ro", uri=True)
    cai = lambda k: (c.execute("SELECT value FROM settings WHERE key = ?", (k,)).fetchone() or [""])[0]       # noqa: E731
    kq = {"binh_luan_cuoi": c.execute("SELECT MAX(sent_at) FROM comments").fetchone()[0], "hop_cuoi": c.execute("SELECT MAX(bat_dau) FROM cuoc_hop").fetchone()[0],
          "quyet_dinh_cuoi": c.execute("SELECT MAX(last_seen) FROM post_decisions").fetchone()[0], "safe_all": cai("safe_all") == "1",
          "tam_dung": cai("paused") == "1", "bi_chan_toi": cai("blocked_until")}
    c.close()
    return kq


def main() -> int:
    ts = tien_trinh_du_an()
    sua = {ten: sua_code_moi_nhat(cay) for ten, (_, cay) in CUA_SO.items()}
    ket_qua = danh_gia_cua_so(ts, sua)
    gio = lambda t: datetime.fromtimestamp(t).strftime("%d/%m %H:%M")                                      # noqa: E731
    print(f"Kiểm tra vận hành lúc {datetime.now():%d/%m/%Y %H:%M}\n")
    for r in ket_qua:
        if r["trang_thai"] == "tat":
            print(f"  ✗ {r['cua_so']}: KHÔNG chạy")
        elif r["trang_thai"] == "cu":
            print(f"  ! {r['cua_so']}: đang chạy MÃ CŨ (khởi động {gio(r['bat_dau'])}, nhưng {r['file_sua_sau']} sửa sau đó) → cần khởi động lại")
        else:
            print(f"  ✓ {r['cua_so']}: chạy mã mới (khởi động {gio(r['bat_dau'])})" + (" — CÓ THỂ chạy trùng 2 bản" if r["chay_trung"] else ""))
    db = doc_csdl()
    if db:
        print(f"\n  Bình luận cuối: {db['binh_luan_cuoi']} · Họp sáng cuối: {db['hop_cuoi']} · Quyết định cuối: {db['quyet_dinh_cuoi']}")
        print(f"  Bản không SĐT cho mọi nhóm: {'BẬT' if db['safe_all'] else 'tắt'} · Tạm dừng: {'CÓ' if db['tam_dung'] else 'không'}"
              + (f" · Bị chặn tới: {db['bi_chan_toi']}" if db["bi_chan_toi"] else ""))
    can_lam = [r for r in ket_qua if r["trang_thai"] != "moi"]
    if can_lam:
        print("\nCần khởi động lại: " + ", ".join(r["cua_so"] for r in can_lam) + ". Đóng cửa sổ cũ rồi bấm chay-ngam.bat (đừng để chạy trùng).")
    return 1 if can_lam else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
