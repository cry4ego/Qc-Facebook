"""
Nạp nội dung bán hàng kiểu MỚI (yêu cầu 12/11/2026): mỗi bài chỉ 1 BÌNH LUẬN + 1 ẢNH GHÉP, bình luận KHÔNG có
tên người bán / SĐT (liên hệ chỉ in sẵn trên ảnh bán hàng). Khác với `python main.py noidung` (gắn câu ký có SĐT/tên,
ảnh riêng từng mẫu, nạp mọi mẫu).

Việc làm:
  1. Ghép ảnh bán hàng của các mẫu ĐANG BÁN (dang_ban = true) thành 1 ảnh 2x2  -> data/images/ghep-4-man-dang-ban.png
  2. Mỗi mẫu đang bán = 1 sản phẩm đang bật, ảnh = ảnh ghép, mẫu bình luận = các thẻ thông số (## MÃ) KHÔNG câu ký
     (text = safe_text = thân thẻ, không SĐT/tên). Các sản phẩm khác (mẫu đã ngừng bán, sản phẩm cũ) bị TẮT.
  3. Sao lưu CSDL trước khi ghi.
Chạy:  .venv\\Scripts\\python.exe tools\\nap_asl_ghep.py ["thư mục nguồn ASL"]
Nhớ đặt COMMENT_PRODUCTS_PER_POST = 1 trong config.py (mỗi bài 1 bình luận).
"""
import os
import sys
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image

from config import Config
from modules.db import Database
from modules import noi_dung as nd

# Nội dung bán hàng đã kèm trong repo (data/noi_dung_asl) -> máy khác clone về chạy được ngay, không cần thư mục ngoài.
# Có thể truyền thư mục nguồn khác qua tham số dòng lệnh.
DEFAULT_SRC = os.path.join(Config.DATA_DIR, "noi_dung_asl")
MERGED_NAME = "ghep-4-man-dang-ban.png"
TILE_WIDTH = 1280          # bề rộng mỗi ô trong ảnh ghép (giữ tỉ lệ 16:9 của ảnh gốc)
GUTTER = 24                # khoảng trắng giữa/viền các ô


def ghep_2x2(src, selling, out_path):
    """Ghép ảnh bán hàng của 4 mẫu đang bán thành lưới 2x2 (nền trắng). selling: list mẫu (cau-hinh)."""
    tiles = []
    for sp in selling[:4]:
        im = Image.open(os.path.join(src, *sp["anh"].replace("\\", "/").split("/"))).convert("RGB")
        w, h = im.size
        tiles.append(im.resize((TILE_WIDTH, round(TILE_WIDTH * h / w)), Image.LANCZOS))
    tile_h = max(t.size[1] for t in tiles)
    while len(tiles) < 4:                       # <4 mẫu thì chừa ô trống (hiếm khi xảy ra)
        tiles.append(Image.new("RGB", (TILE_WIDTH, tile_h), (255, 255, 255)))
    canvas_w = GUTTER * 3 + TILE_WIDTH * 2
    canvas_h = GUTTER * 3 + tile_h * 2
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    spots = [(GUTTER, GUTTER), (GUTTER * 2 + TILE_WIDTH, GUTTER),
             (GUTTER, GUTTER * 2 + tile_h), (GUTTER * 2 + TILE_WIDTH, GUTTER * 2 + tile_h)]
    for tile, (x, y) in zip(tiles, spots):
        canvas.paste(tile, (x, y))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canvas.save(out_path, "PNG")
    return canvas.size


def bodies_khong_ky(content, sp):
    """30 thẻ thông số của 1 mẫu, đã thay {gia}... nhưng KHÔNG thêm câu ký (không SĐT/tên).
    Bỏ qua thẻ dùng biến mẫu này không có (vd {gia_co_chan} của mẫu không bán kèm chân)."""
    values = nd._values(content, sp, contact=False)     # chỉ giá + bảo hành, không có liên hệ
    out = []
    for it in nd._read(content, "binh-luan", sp):
        try:
            out.append(nd.render(it.text, values, f"binh-luan/{sp['ma']}.md {it.code}").strip())
        except ValueError as e:
            print(f"  (bỏ {it.code}: {e})")
    return out


def sao_luu_db():
    dst_dir = os.path.join(Config.DATA_DIR, "sao_luu")
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, f"truoc-nap-asl-ghep-{datetime.now():%Y-%m-%d_%H%M}.db")
    src = sqlite3.connect(Config.DB_FILE)
    out = sqlite3.connect(dst)
    src.backup(out)
    out.close()
    src.close()
    return dst


def main(src=DEFAULT_SRC):
    text_root = os.path.join(src, "noi-dung") if os.path.isdir(os.path.join(src, "noi-dung")) else src
    content = nd.load(text_root)
    selling = [sp for sp in content.products if sp.get("dang_ban")]
    if not selling:
        print("✗ Không có mẫu nào dang_ban = true trong cau-hinh.json"); return 1
    print(f"Mẫu đang bán ({len(selling)}): " + ", ".join(sp["ten"] for sp in selling))

    backup = sao_luu_db()
    print(f"✓ Đã sao lưu CSDL -> {backup}")

    merged = os.path.join(Config.IMAGE_DIR, MERGED_NAME)
    size = ghep_2x2(src, selling, merged)
    print(f"✓ Ảnh ghép {size[0]}x{size[1]} -> {merged}")

    db = Database(Config.DB_FILE)
    keep_ids = set()
    for sp in selling:
        bodies = bodies_khong_ky(content, sp)
        fields = dict(name=sp["ten"], price=sp["gia"], image=MERGED_NAME, active=1)
        p = nd.find_product(db, sp["ten"])
        pid = p["id"] if p else db.add_product(text="", safe_text="", **fields)
        if p:
            db.update_product(pid, **fields)
        keep_ids.add(pid)
        existing = {v["text"]: v for v in db.variants(pid)}
        for body in bodies:
            v = existing.get(body)
            vid = v["id"] if v else db.add_variant(pid, body, body)
            db.update_variant(vid, safe_text=body, image=MERGED_NAME, safe_image=MERGED_NAME, active=1)
        new_set = set(bodies)
        for v in existing.values():                      # tắt mẫu cũ không còn dùng (giữ lịch sử)
            if v["text"] not in new_set and v["active"]:
                db.update_variant(v["id"], active=0)
        print(f"  • {sp['ten']}: {len(bodies)} thẻ bình luận (không câu ký)")

    tat = 0
    for p in db.products(active_only=True):              # tắt sản phẩm cũ / mẫu đã ngừng bán
        if p["id"] not in keep_ids:
            db.update_product(p["id"], active=0)
            tat += 1
    print(f"✓ Đã tắt {tat} sản phẩm khác (không thuộc 4 mẫu đang bán)")
    print("XONG. Nhớ: COMMENT_PRODUCTS_PER_POST = 1 (mỗi bài 1 bình luận + ảnh ghép).")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC))
