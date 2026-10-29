"""
Nội dung bán hàng theo mẫu màn (20/10, từ thư mục "Ảnh Màn-20-10"), lưu ở data/noi_dung:
  cau-hinh.json        người bán, SĐT/Zalo, địa chỉ, bảo hành, câu kết bình luận, danh sách mẫu màn (giá, ảnh, tom_tat)
  binh-luan/<mã>.md    bình luận / mẫu màn (26/10/2026: thẻ ngắn mã màn + thông số + công nghệ, xem tools/viet_lai_binh_luan.py)
                       — "## MÃ" rồi nội dung (không ghi SĐT/địa chỉ trong thân)
  bai-dang/<mã>.md     10 bài đăng / mẫu màn — "## MÃ | Nhóm nên đăng" rồi nội dung (có liên hệ)
Câu kết bình luận: bản đầy đủ = {lien_he} (một dòng "Dũng-0902189751-64 Cầu Diễn", xem lien_he_gon); bản không SĐT = không có
câu kết (câu kết rỗng thì không thêm dòng).
Ảnh: ảnh bán hàng (Anh-ban-hang, có giá + SĐT + địa chỉ) -> data/images/<tên>.png — chủ shop dùng ảnh này cho bài
đăng và cho cả 2 bản bình luận (đầy đủ / không SĐT); ảnh gốc MSI (anh_goc) không dùng.

python main.py noidung ["thư mục nguồn"]  : chép nội dung + ảnh vào data/, nạp bình luận vào CSDL (thay mẫu cũ).
Bài đăng theo lịch: cột content = "@xoay" (xoay vòng mẫu màn mỗi ngày) hoặc "@<mã>" (vd @g274qpx) — mỗi nhóm nhận
1 bài khác nhau trong các bài của mẫu màn đó.
"""
import json
import os
import re
import shutil
from dataclasses import dataclass

CONTACT_KEYS = ("cong_ty", "nguoi_ban", "sdt", "zalo", "dia_chi")
PRICE_KEYS = ("ten", "gia", "gia_co_chan", "phu_thu_chan")
ROTATE = "@xoay"


@dataclass(frozen=True)
class Item:
    code: str
    note: str
    text: str
    image: str | None


@dataclass(frozen=True)
class Comment:
    code: str
    full: str          # bình luận + câu ký tên có SĐT/Zalo/địa chỉ
    safe: str          # bình luận + câu ký tên chỉ có tên người bán
    image: str         # tên ảnh trong data/images cho bản đầy đủ (ảnh bán hàng)
    safe_image: str    # ... cho bản chỉ tên (cũng là ảnh bán hàng — chủ shop chọn 20/10)


@dataclass(frozen=True)
class Post:
    code: str
    note: str
    text: str
    image: str


@dataclass(frozen=True)
class Content:
    root: str
    config: dict
    products: list


def parse_md(raw):
    """Các mục '## MÃ' hoặc '## MÃ | Nhóm' (bỏ ghi chú <!-- -->, dòng 'Ảnh: …' là ảnh riêng của mục)"""
    raw = re.sub(r"<!--.*?-->", "", raw.replace("\r\n", "\n"), flags=re.S)
    items, cur = [], None
    for line in raw.splitlines():
        if line.startswith("## "):
            code, _, note = line[3:].partition("|")
            cur = {"code": code.strip(), "note": note.strip(), "lines": [], "image": None}
            items.append(cur)
        elif cur is not None:
            m = re.match(r"^\s*Ảnh:\s*(.+?)\s*$", line)
            if m:
                cur["image"] = m.group(1)
            else:
                cur["lines"].append(line.rstrip())
    return [Item(i["code"], i["note"], "\n".join(i["lines"]).strip(), i["image"]) for i in items]


def render(template, values, where):
    """Thay {biến}; biến lạ hoặc chưa có giá trị (vd {gia_co_chan} của mẫu không bán kèm chân) là lỗi"""
    def rep(m):
        key = m.group(1)
        if key not in values:
            raise ValueError(f"{where}: biến {{{key}}} không dùng được ở đây")
        if values[key] is None:
            raise ValueError(f"{where}: {{{key}}} chưa có giá trị cho mẫu màn này (cau-hinh.json)")
        return values[key]
    return re.sub(r"\{(\w+)\}", rep, template)


def image_name(path):
    """Đường dẫn ảnh trong nguồn -> tên ảnh trong data/images"""
    parts = path.replace("\\", "/").split("/")
    if len(parts) >= 3 and parts[0] == "assets":
        return "/".join(["goc"] + parts[1:])
    return parts[-1]


def load(root):
    with open(os.path.join(root, "cau-hinh.json"), encoding="utf-8") as f:
        config = json.load(f)
    return Content(root, config, list(config["san_pham"]))


def _read(content, kind, sp):
    with open(os.path.join(content.root, kind, f"{sp['ma']}.md"), encoding="utf-8") as f:
        return parse_md(f.read())


def lien_he_gon(nguoi_ban, sdt, dia_chi):
    """Dòng liên hệ gọn của bình luận: tên gọi (chữ cuối của họ tên) - SĐT viết liền - số nhà + phố (trước dấu phẩy đầu tiên), vd
    ("Hoàng Văn Dũng", "0902 189 751", "64 Cầu Diễn, Hà Nội") -> "Dũng-0902189751-64 Cầu Diễn". Chủ shop 26/10/2026: họ tên đầy đủ
    trong bình luận bị Facebook gợi ý gắn thẻ nhầm người. Thiếu một phần thì trả chuỗi rỗng"""
    ten = (nguoi_ban or "").split()
    so = re.sub(r"\D", "", sdt or "")
    pho = " ".join((dia_chi or "").split(",")[0].split())
    return "-".join((ten[-1], so, pho)) if ten and so and pho else ""


def _values(content, sp, contact):
    values = {k: sp.get(k) for k in PRICE_KEYS}
    values["bao_hanh"] = content.config["bao_hanh"]
    if contact:
        values.update({k: content.config[k] for k in CONTACT_KEYS})
        values["lien_he"] = lien_he_gon(values["nguoi_ban"], values["sdt"], values["dia_chi"])    # {lien_he} trong câu kết
    return values


def comments(content, sp):
    """30 bình luận của 1 mẫu màn: bản đầy đủ + bản chỉ tên (câu ký tên xoay vòng như file Word của nguồn)"""
    cfg, idx = content.config, content.products.index(sp)
    body_values, sign_values = _values(content, sp, False), _values(content, sp, True)
    full_signs, safe_signs = cfg["ket_bl_day_du"], cfg["ket_bl_chi_ten"]
    out = []
    for i, it in enumerate(_read(content, "binh-luan", sp)):
        where = f"binh-luan/{sp['ma']}.md {it.code}"
        body = render(it.text, body_values, where)
        full_sign = render(full_signs[(i + idx) % len(full_signs)], sign_values, "ket_bl_day_du")
        safe_sign = render(safe_signs[(i + idx) % len(safe_signs)], sign_values, "ket_bl_chi_ten")
        full = body + ("\n" + full_sign if full_sign.strip() else "")      # câu kết rỗng (vd bản không SĐT từ 28/10) thì không thêm dòng trống
        safe = body + ("\n" + safe_sign if safe_sign.strip() else "")
        image = image_name(it.image or sp["anh"])  # chủ shop: cả 2 bản đều dùng ảnh bán hàng (Anh-ban-hang)
        out.append(Comment(it.code, full, safe, image, image))
    return out


def posts(content, sp):
    values = _values(content, sp, True)
    return [Post(it.code, it.note, render(it.text, values, f"bai-dang/{sp['ma']}.md {it.code}"),
                 image_name(it.image or sp["anh"]))
            for it in _read(content, "bai-dang", sp)]


def rotate(models, day, slot, slots=2):
    """Mẫu màn cho khung giờ thứ `slot` trong ngày: xoay vòng đều mọi mẫu, 2 khung giờ cùng ngày khác mẫu"""
    return models[(day.toordinal() * slots + slot) % len(models)]


def post_picker(items, day):
    """Nhóm thứ i trong lượt đăng nhận bài khác nhau; mỗi ngày bắt đầu từ bài khác"""
    start = day.toordinal()
    return lambda i: items[(start + i) % len(items)]


def scheduled_post(cell, slot, day, root):
    """Ô content của lịch đăng: '@xoay' (mẫu màn xoay vòng theo ngày, slot = thứ tự khung giờ '@xoay' trong ngày) hoặc
    '@<mã>' -> (hàm i -> bài cho nhóm thứ i, tên ảnh, tên mẫu); chữ thường -> None (đăng nguyên chữ như cũ)"""
    cell = str(cell or "").strip()
    if not cell.startswith("@"):
        return None
    content = load(root)
    codes = [sp["ma"] for sp in content.products]
    code = rotate(codes, day, slot) if cell.lower() == ROTATE else cell[1:].strip().lower()
    sp = next((s for s in content.products if s["ma"] == code), None)
    if sp is None:
        raise ValueError(f"Lịch đăng ghi '{cell}' nhưng không có mẫu màn '{code}' trong cau-hinh.json "
                         f"(có: {', '.join(codes)})")
    items = posts(content, sp)
    return post_picker([p.text for p in items], day), items[0].image, sp["ten"]


def _model_key(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def find_product(db, ten):
    """Sản phẩm sẵn có cùng mẫu máy (vd 'MSI G274QPF E2 27"' ứng với 'MSI G274QPF E2')"""
    key = _model_key(ten)
    for p in db.products():
        other = _model_key(p["name"])
        if other == key or (other.startswith(key) and not other[len(key):len(key) + 1].isalpha()):
            return p
    return None


def import_to_db(db, content):
    """Mỗi mẫu màn = 1 sản phẩm đang bật (giá, ảnh mới); bình luận mới thành mẫu bình luận, mẫu cũ tắt (giữ lịch sử).
    Trả về [(tên, số bình luận)]"""
    summary = []
    for sp in content.products:
        items = comments(content, sp)
        fields = dict(name=sp["ten"], price=sp["gia"], image=image_name(sp["anh"]), active=1)
        p = find_product(db, sp["ten"])
        pid = p["id"] if p else db.add_product(text="", safe_text="", **fields)
        if p:
            db.update_product(pid, **fields)
        existing = {v["text"]: v for v in db.variants(pid)}
        for c in items:
            v = existing.get(c.full)
            vid = v["id"] if v else db.add_variant(pid, c.full, c.safe)
            db.update_variant(vid, safe_text=c.safe, image=c.image, safe_image=c.safe_image, active=1)
        new_texts = {c.full for c in items}
        for v in existing.values():
            if v["text"] not in new_texts and v["active"]:
                db.update_variant(v["id"], active=0)
        summary.append((sp["ten"], len(items)))
    return summary


def copy_source(src, dst_text, image_dir):
    """Chép nội dung chữ (cau-hinh.json, binh-luan, bai-dang — trong src/noi-dung) vào dst_text và ảnh dùng tới
    (đường dẫn tính từ src, vd Anh-ban-hang/…, assets/<mã>/…) vào data/images"""
    text_src = os.path.join(src, "noi-dung") if os.path.isdir(os.path.join(src, "noi-dung")) else src
    content = load(text_src)
    os.makedirs(dst_text, exist_ok=True)
    shutil.copy2(os.path.join(text_src, "cau-hinh.json"), os.path.join(dst_text, "cau-hinh.json"))
    for kind in ("binh-luan", "bai-dang"):
        shutil.copytree(os.path.join(text_src, kind), os.path.join(dst_text, kind), dirs_exist_ok=True)
    images = set()
    for sp in content.products:
        images.add(sp["anh"])
        for kind in ("binh-luan", "bai-dang"):
            images.update(it.image for it in _read(content, kind, sp) if it.image)
    for path in sorted(images):
        target = os.path.join(image_dir, *image_name(path).split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(src, *path.replace("\\", "/").split("/")), target)
    return load(dst_text), len(images)
