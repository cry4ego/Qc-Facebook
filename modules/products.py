"""
Sản phẩm để bình luận (quản lý trên web, lưu trong bảng products).
Mỗi sản phẩm đang bật = 1 bình luận kèm ảnh riêng vào mỗi bài viết.
Mỗi sản phẩm có nhiều MẪU bình luận (bảng comment_variants): mỗi bài chọn ngẫu nhiên 1 mẫu đang bật,
ưu tiên mẫu ít dùng, tránh mẫu đã dùng gần đây trong cùng nhóm, không trùng nội dung trong 1 bài.
Lần đầu chạy, 3 sản phẩm trong data/comments.txt được chuyển vào CSDL.
"""
import os
import re
import time
import random
import unicodedata

PHONE_RE = re.compile(r"(?<!\d)0\d{2,3}[\s.\-]?\d{3}[\s.\-]?\d{3,4}(?!\d)")
# Dòng có SĐT / địa chỉ / Zalo -> bỏ ở bản không SĐT/địa chỉ
CONTACT_RE = re.compile(r"(?<!\d)0\d{2,3}[\s.\-]?\d{3}[\s.\-]?\d{3,4}(?!\d)|địa chỉ|zalo|hotline|liên hệ|\bsđt\b|\bsdt\b",
                        re.IGNORECASE)
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def make_safe(text):
    """Bản không SĐT/địa chỉ: bỏ các dòng có SĐT, địa chỉ, Zalo, hotline"""
    return "\n".join(l for l in (text or "").splitlines() if not CONTACT_RE.search(l)).strip()


def _money(value):
    d = re.sub(r"\D", "", value or "")
    return int(d) if d else 0


def fill_price(text, price, new_price=""):
    """Thay chỗ trống trong nội dung: {giá} = giá bán, {giá_mới} = giá mua mới, {tiết_kiệm} = giá mới - giá bán"""
    text = re.sub(r"\{gi[áa][ _]m[ớo]i\}", new_price or "", text or "", flags=re.IGNORECASE)
    saving = _money(new_price) - _money(price)
    saving = f"{saving:,}".replace(",", ".") + "đ" if _money(price) and saving > 0 else ""
    text = re.sub(r"\{ti[ếe]t[ _]ki[ệe]m\}", saving, text, flags=re.IGNORECASE)
    return re.sub(r"\{gi[áa]\}", price or "", text, flags=re.IGNORECASE)


def slug(s):
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d").replace("Đ", "D")
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:60] or "san_pham"


def save_image(file_storage, name, image_dir):
    """Lưu ảnh tải lên từ web vào data/images, trả về tên file"""
    ext = os.path.splitext(file_storage.filename or "")[1].lower()
    if ext not in IMAGE_EXTS:
        raise ValueError("Ảnh phải là .jpg, .jpeg, .png hoặc .webp")
    filename = f"{slug(name)}_{int(time.time())}{ext}"
    os.makedirs(image_dir, exist_ok=True)
    file_storage.save(os.path.join(image_dir, filename))
    return filename


def parse_comments_file(path):
    """Đọc data/comments.txt (định dạng cũ): khối cách nhau bằng '---'; 'ảnh:', 'liên hệ:', 'an toàn:'.
    Trả về [{name, price, image, text, safe_text}]"""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    items = []
    for block in raw.split("\n---"):
        body, contact, safe_cta, image = [], [], [], ""
        for line in block.splitlines():
            st = line.strip()
            if st.startswith("#") or st == "---":
                continue
            key, _, value = st.partition(":")
            key = key.lower().strip()
            if key == "ảnh":
                image = value.strip()
            elif key == "liên hệ":
                contact.append(value.strip())
            elif key == "an toàn":
                safe_cta.append(value.strip())
            else:
                body.append(line.rstrip())
        text = "\n".join(body + contact).strip()
        if not text:
            continue
        first = next((l for l in body if l.strip()), text)
        price = re.search(r"Giá\s*([\d.,]+\s*(đ|k|tr|triệu)?)", text, re.IGNORECASE)
        items.append({
            "name": re.split(r"\s+[–-]\s+", first)[0].strip()[:80],
            "price": price.group(1).strip() if price else "",
            "image": image,
            "text": text,
            "safe_text": "\n".join([l for l in body if not PHONE_RE.search(l)] + safe_cta).strip(),
        })
    return items


def ensure_seed(db, config):
    """Bảng products trống -> nhập 3 sản phẩm từ comments.txt"""
    if db.query("SELECT 1 FROM products LIMIT 1"):
        return 0
    items = parse_comments_file(config.COMMENTS_FILE)
    for it in items:
        db.add_product(active=1, **it)
    return len(items)


def ensure_variants(db):
    """Lần đầu có tính năng mẫu bình luận: nội dung bình luận cũ của từng sản phẩm thành mẫu đầu tiên"""
    if db.get_setting("variants_migrated") == "1":
        return
    for p in db.products():
        if (p["text"] or "").strip() and not db.variants(p["id"]):
            db.add_variant(p["id"], p["text"], p["safe_text"] or "")
    db.set_setting("variants_migrated", "1")


NEEDS_NEW_PRICE = re.compile(r"\{(gi[áa][ _]m[ớo]i|ti[ếe]t[ _]ki[ệe]m)\}", re.IGNORECASE)


def price_ready(text, p):
    """Mẫu có {giá_mới}/{tiết_kiệm} chỉ dùng được khi sản phẩm có giá mua mới cao hơn giá bán (tránh câu bị trống)"""
    if not NEEDS_NEW_PRICE.search(text or ""):
        return True
    return _money(p.get("new_price")) > _money(p["price"]) > 0


def _content(text, safe, p):
    text = fill_price(text, p["price"], p.get("new_price")).strip()
    safe = fill_price(safe, p["price"], p.get("new_price")).strip() or make_safe(text)
    return text, safe or text


def load_pool(db, config, logger=None):
    """Sản phẩm đang bật có nội dung bình luận (kiểm tra trước vòng quét):
    [{'name', 'image', 'variants': số mẫu đang bật}]"""
    ensure_seed(db, config)
    ensure_variants(db)
    pool = []
    for p in db.products(active_only=True):
        n = len(db.variants(p["id"], active_only=True))
        if not n and (db.variants(p["id"]) or not (p["text"] or "").strip()):  # tắt hết mẫu = không bình luận
            if logger:
                logger.warning(f"Sản phẩm '{p['name']}' chưa có mẫu bình luận nào được bật — bỏ qua")
            continue
        image = os.path.join(config.IMAGE_DIR, p["image"]) if p["image"] else None
        if image and not os.path.exists(image):
            if logger:
                logger.warning(f"Không tìm thấy ảnh của sản phẩm '{p['name']}': {image}")
            image = None
        pool.append({"name": p["name"], "image": image, "variants": n, "text": p["text"] or "", "safe_text": ""})
    return pool


def pick_pool(db, config, group_url=None):
    """Bình luận cho 1 bài viết: mỗi sản phẩm đang bật chọn ngẫu nhiên 1 mẫu đang bật
    - ưu tiên mẫu chưa dùng trong nhóm này 3 ngày gần đây, rồi mẫu ít được dùng nhất
    - không trùng nội dung với bình luận khác trong cùng bài
    Trả về [{'text', 'safe_text', 'image', 'name', 'variant_id'}]"""
    ensure_seed(db, config)
    ensure_variants(db)
    recent = db.recent_variants_in_group(group_url) if group_url else set()
    pool, used_texts = [], set()
    for p in db.products(active_only=True):
        image = os.path.join(config.IMAGE_DIR, p["image"]) if p["image"] else None
        if image and not os.path.exists(image):
            image = None
        options = [v for v in db.variants(p["id"], active_only=True)
                   if _content(v["text"], v["safe_text"], p)[0] not in used_texts and price_ready(v["text"], p)]
        if options:
            fresh = [v for v in options if v["id"] not in recent] or options  # tránh lặp lại trong cùng nhóm
            least = min(v["used_count"] for v in fresh)
            v = random.choice([v for v in fresh if v["used_count"] <= least + 1])  # ngẫu nhiên trong nhóm ít dùng
            text, safe = _content(v["text"], v["safe_text"], p)
            db.mark_variant_used(v["id"])
            vid = v["id"]
        elif (p["text"] or "").strip() and not db.variants(p["id"]):
            text, safe = _content(p["text"], p["safe_text"], p)  # sản phẩm chưa từng có mẫu: nội dung cũ
            vid = None
        else:
            continue
        if text in used_texts:
            continue
        used_texts.add(text)
        pool.append({"text": text, "safe_text": safe, "image": image, "name": p["name"], "variant_id": vid})
    return pool


# ---------- Nhập mẫu bình luận từ file ----------
def split_blocks(raw):
    """Tách các mẫu cách nhau bằng dòng '---' (bỏ dòng bắt đầu bằng #)"""
    blocks = re.split(r"\n\s*-{3,}\s*(?:\n|$)", (raw or "").replace("\r\n", "\n"))
    out = []
    for b in blocks:
        lines = [l.rstrip() for l in b.splitlines() if not l.strip().startswith("#")]
        text = "\n".join(lines).strip()
        if text:
            out.append(text)
    return out


def _model_codes(name):
    """Mã máy trong tên sản phẩm, vd 'MSI G274QPF E2 27"' -> ['G274QPF']"""
    return [w for w in re.findall(r"[A-Za-z0-9-]+", name or "") if len(w) >= 5 and re.search(r"\d", w)
            and re.search(r"[A-Za-z]", w)]


def _price_digits(price):
    d = re.sub(r"\D", "", price or "")
    return d if len(d) >= 5 else ""


def guess_product(text, products, previous=None):
    """Sản phẩm của 1 mẫu: đếm số lần nhắc mã máy (+2 nếu có đúng giá); hòa thì theo mẫu ngay trước"""
    digits = re.sub(r"[.,\s]", "", text)
    best, best_score, tie = None, 0, False
    for p in products:
        score = sum(len(re.findall(re.escape(c), text, re.IGNORECASE)) for c in _model_codes(p["name"]))
        if _price_digits(p["price"]) and _price_digits(p["price"]) in digits:
            score += 2
        if score > best_score:
            best, best_score, tie = p, score, False
        elif score and score == best_score:
            tie = True
    if tie and previous and any(p["id"] == previous for p in products):
        return previous
    return best["id"] if best else previous


def import_variants(db, full_raw, safe_raw="", product_id=None):
    """Nhập mẫu từ nội dung file: full_raw (bản đầy đủ), safe_raw (bản không liên hệ, ghép theo thứ tự).
    product_id=None: tự nhận sản phẩm theo mã máy / giá. Trả về (số đã nhập, {tên sản phẩm: số}, số mẫu không nhận ra)"""
    fulls, safes = split_blocks(full_raw), split_blocks(safe_raw)
    products = db.products()
    by_id = {p["id"]: p for p in products}
    existing = {(v["product_id"], v["text"].strip()) for v in db.variants()}
    added, per, unknown, prev = 0, {}, 0, None
    for i, text in enumerate(fulls):
        pid = product_id or guess_product(text, products, prev)
        if not pid or pid not in by_id:
            unknown += 1
            continue
        prev = pid
        if (pid, text) in existing:
            continue  # mẫu đã có
        db.add_variant(pid, text, safes[i] if i < len(safes) else "")
        existing.add((pid, text))
        added += 1
        per[by_id[pid]["name"]] = per.get(by_id[pid]["name"], 0) + 1
    return added, per, unknown
