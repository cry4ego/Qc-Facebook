"""Tạo 4 file Word bán hàng từ nội dung trong thư mục noi-dung/.

Chạy:  python tao-tai-lieu.py
Kết quả nằm trong thư mục Tai-lieu/:
  1-Binh-luan-co-SDT-Zalo-dia-chi.docx   bình luận + SĐT/Zalo + địa chỉ
  2-Binh-luan-chi-ten-nguoi-ban.docx     cùng bình luận, chỉ ký tên người bán
  3-Bai-dang-ban-hang.docx               bài đăng nhóm, kèm ảnh bán hàng
  4-Anh-kem-binh-luan.docx               từng bình luận ghép với ảnh đăng kèm
"""
import io
import json
import re
import sys
from pathlib import Path

from PIL import Image
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent
ND = ROOT / "noi-dung"
OUT = ROOT / "Tai-lieu"
CFG = json.loads((ND / "cau-hinh.json").read_text(encoding="utf-8"))

NAVY = RGBColor(0x0A, 0x2A, 0x6B)
RED = RGBColor(0xD0, 0x10, 0x2E)
GREY = RGBColor(0x6B, 0x76, 0x8A)
FONT = "Arial"
CONTACT_KEYS = ("cong_ty", "nguoi_ban", "sdt", "zalo", "dia_chi")
SO_BL, SO_BD = 30, 10  # số bình luận / bài đăng mong muốn cho mỗi mã
# Tài liệu không dùng icon (emoji, ✅ ✔ ❓ ☎ …); gạch đầu dòng viết bằng "- ".
ICON = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️↕]")


# ---------- đọc nội dung ----------

def parse_md(path):
    """Tách file .md thành các mục bắt đầu bằng '## MÃ' hoặc '## MÃ | Nhóm'."""
    text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S)
    items, cur = [], None
    for line in text.splitlines():
        if line.startswith("## "):
            ma, _, nhom = line[3:].partition("|")
            cur = {"ma": ma.strip(), "nhom": nhom.strip(), "lines": [], "anh": None}
            items.append(cur)
        elif cur is not None:
            m = re.match(r"^\s*Ảnh:\s*(.+?)\s*$", line)
            if m:
                cur["anh"] = m.group(1)
            else:
                cur["lines"].append(line.rstrip())
    for it in items:
        while it["lines"] and not it["lines"][0].strip():
            it["lines"].pop(0)
        while it["lines"] and not it["lines"][-1].strip():
            it["lines"].pop()
    return items


def fill(template, values, where):
    icons = ICON.findall(template)
    if icons:
        sys.exit(f"LỖI {where}: có icon {' '.join(icons)} – tài liệu không dùng icon, hãy xoá hoặc thay bằng chữ")

    def rep(m):
        key = m.group(1)
        if key not in values:
            hint = " (không ghi liên hệ trong thân bình luận)" if key in CONTACT_KEYS else ""
            sys.exit(f"LỖI {where}: biến {{{key}}} không dùng được ở đây{hint}")
        if values[key] is None:
            sys.exit(f"LỖI {where}: {{{key}}} chưa có giá trị cho mã này trong cau-hinh.json")
        return values[key]
    return re.sub(r"\{(\w+)\}", rep, template)


def digits(s):
    return re.sub(r"\D", "", s)


def load_products():
    contact = {k: CFG[k] for k in CONTACT_KEYS}
    products = []
    for p_idx, sp in enumerate(CFG["san_pham"]):
        base = {k: sp.get(k) for k in ("ten", "gia", "gia_co_chan", "phu_thu_chan")}
        base["bao_hanh"] = CFG["bao_hanh"]
        full = {**base, **contact}

        bl = parse_md(ND / "binh-luan" / f"{sp['ma']}.md")
        bd = parse_md(ND / "bai-dang" / f"{sp['ma']}.md")
        for kind, items, want in (("bình luận", bl, SO_BL), ("bài đăng", bd, SO_BD)):
            ids = [it["ma"] for it in items]
            if len(set(ids)) != len(ids):
                sys.exit(f"LỖI {sp['ma']}: trùng mã {kind}")
            if len(items) != want:
                print(f"  ! {sp['ten']}: có {len(items)} {kind} (mong muốn {want})")

        comments = []
        for i, it in enumerate(bl):
            body = [fill(l, base, f"binh-luan/{sp['ma']}.md {it['ma']}") for l in it["lines"]]
            k1 = CFG["ket_bl_day_du"][(i + p_idx) % len(CFG["ket_bl_day_du"])]
            k2 = CFG["ket_bl_chi_ten"][(i + p_idx) % len(CFG["ket_bl_chi_ten"])]
            c = {
                "ma": it["ma"],
                "body": body,
                "ket_day_du": fill(k1, full, "ket_bl_day_du"),
                "ket_chi_ten": fill(k2, full, "ket_bl_chi_ten"),
                "anh": it["anh"] or sp["anh"],
                "anh_goc": it["anh"] or sp["anh_goc"][i % len(sp["anh_goc"])],
            }
            check_no_contact(c["body"] + [c["ket_chi_ten"]], f"{sp['ma']} {it['ma']}")
            comments.append(c)

        posts = [{
            "ma": it["ma"],
            "nhom": it["nhom"],
            "lines": [fill(l, full, f"bai-dang/{sp['ma']}.md {it['ma']}") for l in it["lines"]],
            "anh": it["anh"] or sp["anh"],
        } for it in bd]

        products.append({**sp, "comments": comments, "posts": posts})
    return products


def check_no_contact(lines, where):
    """Bản 'chỉ tên người bán' không được lộ SĐT, địa chỉ, tên công ty."""
    text = "\n".join(lines)
    street = CFG["dia_chi"].split(",")[0].strip()
    bad = [w for w in (CFG["cong_ty"], street) if w.lower() in text.lower()]
    if any(digits(CFG[k]) in digits(text) for k in ("sdt", "zalo")):
        bad.append("SĐT")
    if bad:
        sys.exit(f"LỖI {where}: bình luận chứa {', '.join(bad)} – bản chỉ tên người bán sẽ bị lộ liên hệ")


# ---------- định dạng Word ----------

_img_cache = {}


def img_stream(rel, max_w=1400):
    """Ảnh nén JPEG nền trắng để file Word nhẹ; cùng ảnh chỉ nhúng 1 lần."""
    if rel not in _img_cache:
        path = ROOT / rel
        if not path.exists():
            sys.exit(f"LỖI: không thấy ảnh {rel}")
        im = Image.open(path).convert("RGBA")
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.split()[3])
        if bg.width > max_w:
            bg = bg.resize((max_w, round(bg.height * max_w / bg.width)), Image.LANCZOS)
        buf = io.BytesIO()
        bg.save(buf, "JPEG", quality=85, optimize=True)
        _img_cache[rel] = buf.getvalue()
    return io.BytesIO(_img_cache[rel])


def set_style_font(style, size=None, bold=None, color=None):
    style.font.name = FONT
    if size:
        style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if color is not None:
        style.font.color.rgb = color
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        rfonts.attrib.pop(qn(a), None)
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(a), FONT)


def new_doc(title, subtitle):
    doc = Document()
    zoom = doc.settings.element.find(qn("w:zoom"))  # mẫu mặc định thiếu w:percent (sai chuẩn)
    if zoom is not None:
        zoom.set(qn("w:percent"), "100")
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2)
    sec.top_margin = sec.bottom_margin = Cm(1.8)

    normal = doc.styles["Normal"]
    set_style_font(normal, 11)
    normal.paragraph_format.space_after = Pt(3)
    normal.paragraph_format.line_spacing = 1.15
    set_style_font(doc.styles["Heading 1"], 18, True, NAVY)
    doc.styles["Heading 1"].paragraph_format.space_before = Pt(0)
    doc.styles["Heading 1"].paragraph_format.space_after = Pt(6)
    set_style_font(doc.styles["Heading 2"], 13, True, NAVY)
    doc.styles["Heading 2"].paragraph_format.space_before = Pt(10)
    set_style_font(doc.styles["List Bullet"], 11)

    # số trang ở chân trang
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = fp.add_run("Trang ")
    r.font.size, r.font.color.rgb = Pt(9), GREY
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    fr = OxmlElement("w:r")
    ft = OxmlElement("w:t")
    ft.text = "1"
    fr.append(ft)
    fld.append(fr)
    fp._p.append(fld)

    p = doc.add_paragraph()
    r = p.add_run(title)
    r.bold, r.font.size, r.font.color.rgb = True, Pt(24), NAVY
    p = doc.add_paragraph()
    r = p.add_run(subtitle)
    r.font.size, r.font.color.rgb = Pt(12), GREY
    return doc


def para(container, text="", bold=False, color=None, size=None, italic=False, after=None):
    p = container.add_paragraph()
    if text:
        r = p.add_run(text)
        r.bold, r.italic = bold, italic
        if color is not None:
            r.font.color.rgb = color
        if size:
            r.font.size = Pt(size)
    if after is not None:
        p.paragraph_format.space_after = Pt(after)
    return p


def label_value(container, label, value):
    p = container.add_paragraph()
    r = p.add_run(label)
    r.bold = True
    p.add_run(value)
    return p


def bullets(doc, items):
    for t in items:
        doc.add_paragraph(t, style="List Bullet")


def text_block(container, lines):
    for line in lines:
        para(container, line, after=1)


def hr(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(8)
    pbdr = OxmlElement("w:pBdr")
    b = OxmlElement("w:bottom")
    for k, v in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", "D0D7E2")):
        b.set(qn(k), v)
    pbdr.append(b)
    p._p.get_or_add_pPr().insert_element_before(
        pbdr, "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
        "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi",
        "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing",
        "w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment",
        "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr",
        "w:pPrChange")


def page_break(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def shade(cell, fill):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().insert_element_before(
        shd, "w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark")


def make_table(doc, widths_cm, header=None):
    t = doc.add_table(rows=0, cols=len(widths_cm))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    if header:
        row = add_row(t, widths_cm)
        for cell, h in zip(row.cells, header):
            cell.paragraphs[0].add_run(h).bold = True
            shade(cell, "E8EEFB")
    return t


def add_row(table, widths_cm):
    row = table.add_row()
    trpr = row._tr.get_or_add_trPr()
    trpr.append(OxmlElement("w:cantSplit"))  # không cắt 1 dòng sang 2 trang
    for cell, w in zip(row.cells, widths_cm):
        cell.width = Cm(w)
    return row


def price_table(doc, products, with_image_col):
    head = ["Mã màn", "Giá (không chân / giá bán)", "Có chân đế"]
    widths = [5.0, 4.5, 3.5]
    if with_image_col:
        head.append("Ảnh bán hàng")
        widths = [4.2, 3.6, 3.0, 6.2]
    t = make_table(doc, widths, head)
    for sp in products:
        row = add_row(t, widths)
        vals = [sp["ten"], sp["gia"], sp["gia_co_chan"] or "—"]
        if with_image_col:
            vals.append(sp["anh"])
        for cell, v in zip(row.cells, vals):
            cell.paragraphs[0].add_run(v)
    para(doc, after=6)


def product_heading(doc, sp, image_note):
    doc.add_heading(sp["ten"], level=1)
    para(doc, sp["tom_tat"], color=GREY)
    label_value(doc, "Giá: ", sp["gia"] + (f" (không chân) · {sp['gia_co_chan']} (có chân)" if sp["gia_co_chan"] else ""))
    label_value(doc, "Ảnh đăng kèm: ", image_note)
    p = label_value(doc, "Nguồn thông số: ", " · ".join(sp["nguon"]))
    for r in p.runs:
        r.font.size, r.font.color.rgb = Pt(9), GREY


# ---------- 4 tài liệu ----------

def doc_binh_luan(products, day_du):
    if day_du:
        doc = new_doc("1 · Bình luận bán hàng – có SĐT/Zalo và địa chỉ",
                      f"{CFG['cong_ty']} · {len(products)} mã màn · {SO_BL} bình luận mỗi mã")
        label_value(doc, "Người bán: ", CFG["nguoi_ban"])
        label_value(doc, "SĐT / Zalo: ", CFG["sdt"])
        label_value(doc, "Địa chỉ: ", CFG["dia_chi"])
    else:
        doc = new_doc("2 · Bình luận bán hàng – chỉ tên người bán",
                      f"Không có SĐT, địa chỉ · {len(products)} mã màn · {SO_BL} bình luận mỗi mã")
        label_value(doc, "Người bán: ", CFG["nguoi_ban"])
    label_value(doc, "Bảo hành: ", CFG["bao_hanh"])
    label_value(doc, "Tình trạng: ", CFG["tinh_trang"])

    doc.add_heading("Cách dùng", level=2)
    tips = [
        "Mỗi bình luận có mã riêng (ví dụ QPX-01). Mỗi mã chỉ dùng 1 lần cho 1 bài/nhóm để tránh trùng nội dung.",
        "Copy nguyên khối bình luận, gồm cả dòng ký tên cuối.",
        "Ảnh đăng kèm ghi ở đầu phần mỗi mã màn; bảng ghép từng bình luận với ảnh nằm ở file 4.",
    ]
    if day_du:
        tips.append("Ảnh bán hàng (thư mục Anh-ban-hang) đã in giá, SĐT và địa chỉ – hợp với bình luận ở file này.")
    else:
        tips.append("Ảnh bán hàng có in SĐT và địa chỉ, nên KHÔNG dùng với file này. Dùng ảnh gốc MSI (không có liên hệ) như ghi ở từng bình luận.")
    bullets(doc, tips)

    doc.add_heading("Bảng giá", level=2)
    price_table(doc, products, with_image_col=day_du)

    for sp in products:
        page_break(doc)
        note = sp["anh"] if day_du else "ảnh gốc MSI, xoay vòng – " + ", ".join(sp["anh_goc"])
        product_heading(doc, sp, note)
        hr(doc)
        for c in sp["comments"]:
            p = para(doc, c["ma"], bold=True, color=RED, size=10, after=2)
            if not day_du:
                r = p.add_run(f"   · ảnh: {c['anh_goc']}")
                r.font.size, r.font.color.rgb = Pt(9), GREY
            text_block(doc, c["body"])
            para(doc, c["ket_day_du"] if day_du else c["ket_chi_ten"], after=1)
            hr(doc)
    return doc


def doc_bai_dang(products):
    doc = new_doc("3 · Bài đăng bán hàng kèm ảnh",
                  f"{CFG['cong_ty']} · {len(products)} mã màn · {SO_BD} bài cho {SO_BD} kiểu nhóm khác nhau mỗi mã")
    doc.add_heading("Cách dùng", level=2)
    bullets(doc, [
        "Mỗi bài ghi sẵn kiểu nhóm nên đăng. Mỗi bài chỉ đăng ở 1 nhóm để nội dung không bị trùng.",
        "Đăng kèm ảnh bán hàng của đúng mã màn (in ở đầu phần mỗi mã, file gốc trong thư mục Anh-ban-hang).",
        "Giá, bảo hành, SĐT/Zalo, địa chỉ đã có sẵn trong bài.",
    ])
    doc.add_heading("Bảng giá", level=2)
    price_table(doc, products, with_image_col=True)

    for sp in products:
        page_break(doc)
        product_heading(doc, sp, sp["anh"])
        doc.add_paragraph().add_run().add_picture(img_stream(sp["anh"]), width=Cm(16.5))
        for post in sp["posts"]:
            doc.add_heading(f"{post['ma']} – {post['nhom']}", level=2)
            p = label_value(doc, "Ảnh đính kèm: ", post["anh"])
            for r in p.runs:
                r.font.size, r.font.color.rgb = Pt(9), GREY
            text_block(doc, post["lines"])
            hr(doc)
    return doc


def doc_anh_kem(products):
    doc = new_doc("4 · Ảnh kèm bình luận",
                  "Mỗi dòng = 1 bình luận + ảnh đăng kèm bình luận đó")
    doc.add_heading("Cách dùng", level=2)
    bullets(doc, [
        "Phần A: bình luận có SĐT/Zalo + địa chỉ (giống file 1), đăng kèm ảnh bán hàng có giá.",
        "Phần B: bình luận chỉ tên người bán (giống file 2), đăng kèm ảnh gốc MSI không có liên hệ.",
        "Mã bình luận giống nhau ở file 1, 2 và 4 – dùng mã để đánh dấu bình luận đã đăng.",
    ])

    widths = [5.6, 11.4]
    for part, day_du in (("A", True), ("B", False)):
        for sp in products:
            page_break(doc)
            title = "có SĐT + địa chỉ" if day_du else "chỉ tên người bán"
            doc.add_heading(f"{part} · {sp['ten']} – {title}", level=1)
            t = make_table(doc, widths, ["Ảnh đăng kèm", "Bình luận"])
            for c in sp["comments"]:
                anh = c["anh"] if day_du else c["anh_goc"]
                row = add_row(t, widths)
                left = row.cells[0]
                left.paragraphs[0].add_run().add_picture(
                    img_stream(anh, 900), width=Cm(5.2 if day_du else 4.4))
                note = left.add_paragraph()
                nr = note.add_run(anh)
                nr.font.size, nr.font.color.rgb = Pt(7.5), GREY
                right = row.cells[1]
                rp = right.paragraphs[0]
                rr = rp.add_run(c["ma"])
                rr.bold, rr.font.color.rgb, rr.font.size = True, RED, Pt(10)
                text_block(right, c["body"] + [c["ket_day_du"] if day_du else c["ket_chi_ten"]])
    return doc


def main():
    OUT.mkdir(exist_ok=True)
    products = load_products()
    files = {
        "1-Binh-luan-co-SDT-Zalo-dia-chi.docx": doc_binh_luan(products, True),
        "2-Binh-luan-chi-ten-nguoi-ban.docx": doc_binh_luan(products, False),
        "3-Bai-dang-ban-hang.docx": doc_bai_dang(products),
        "4-Anh-kem-binh-luan.docx": doc_anh_kem(products),
    }
    for name, doc in files.items():
        doc.save(OUT / name)
        print(f"  ✓ Tai-lieu/{name}")
    n_bl = sum(len(sp["comments"]) for sp in products)
    n_bd = sum(len(sp["posts"]) for sp in products)
    print(f"Xong: {len(products)} mã màn, {n_bl} bình luận, {n_bd} bài đăng.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
