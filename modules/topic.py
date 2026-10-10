"""
Chủ đề bài viết (Config.COMMENT_TOPICS): 'Màn hình' / 'PC' / 'Laptop' / None (không liên quan).
Bot bình luận bài màn hình trước, rồi bài PC / linh kiện; bài laptop, điện thoại bỏ qua.
"""
import re

MONITOR_TOPIC = re.compile(
    r"màn|man hinh|monitor|\bmh\b|\d+\s?hz\b|\binch\b|\d{2}\s?in\b|ultrasharp|\b[upse]\d{4}[a-z]*\b", re.IGNORECASE)
# Tên / dòng laptop (bài laptop hay ghi "màn 15.6", "165hz" — là màn của laptop, không phải bài màn hình)
LAPTOP_TOPIC = re.compile(
    r"laptop|lap top|latop|macbook|mac air|mac pro|thinkpad|latitude|inspiron|insprion|vostro|legion|precision|yoga|elitebook|probook"
    r"|zenbook|vivobook|ideapad|aspire|nitro|\btuf\b|rog |surface|\bxps\b|ultrabook|untrabook|chromebook"
    r"|\bg1[56]\b|predator|omen|victus|pavilion|envy|spectre|katana|\bgf6\d\b|\bloq\b|strix|zephyrus|helios"
    r"|thin a15|cyborg|bravo 15|alienware|\bswift\b|\bthin\b", re.IGNORECASE)
# Thông số máy (RAM, SSD, CPU, VGA) — có ở cả laptop và PC, màn hình thì không có
SPEC_TOPIC = re.compile(r"\bram\b|\bssd\b|core\s?i\d|\bi[3579][-\s]?\d|\bgen\s?\d|ryzen|\brtx\b|\bgtx\b|\bcpu\b",
                        re.IGNORECASE)
# Có thông số máy + dấu hiệu laptop (màn 10–17", pin, cảm ứng) mà không nói PC -> laptop
LAPTOP_HINT = re.compile(r"\b1[0-7][.,]\d\b|\b1[0-7]\s?(inch|in\b|\"|”)|\bpin\b|cảm ứng|gập xoay", re.IGNORECASE)
PC_TOPIC = re.compile(
    r"\bpc\b|máy bàn|may ban|desktop|\bcase\b|thùng máy|cấu hình|cau hinh|\bbuild\b|full bộ|bộ máy|\bvga\b|card màn"
    r"|card đồ họa|mainboard|\bmain\b|\bnguồn\b|tản nhiệt|xeon|optiplex|mini pc|linh kiện|bàn phím|chuột|gaming gear"
    r"|setup|góc máy|máy tính|may tinh|\bmicro\b|\bsff\b|đồng bộ", re.IGNORECASE)
PHONE_TOPIC = re.compile(r"iphone|ipad|samsung galaxy|điện thoại|dien thoai|\boppo\b|xiaomi redmi", re.IGNORECASE)
# "cần/tìm/mua ... màn hình" đứng gần nhau (≤ 25 ký tự, cùng câu) và không phải màn laptop 10–17"
WANT_MONITOR = re.compile(r"(cần|tìm|mua)\b[^.\n]{0,25}(màn hình|man hinh|monitor|\bmh\b|\bmàn\b)"
                          r"(?!\s*(hình\s*)?(laptop|1[0-7]([.,]\d)?\s?(inch|in\b|\"|”)))", re.IGNORECASE)
SELLING = re.compile(r"cần (bán|pass|thanh lý)", re.IGNORECASE)
# "card màn hình" / "card màn" = card đồ họa (linh kiện PC), không phải màn hình
GPU_CARD = re.compile(r"card\s*(màn\s*hình|man\s*hinh|màn|đồ\s*họa|do\s*hoa)", re.IGNORECASE)
MONITOR, PC, LAPTOP = "Màn hình", "PC", "Laptop"


def topic(text):
    """Chủ đề bài viết: 'Màn hình' / 'PC' / 'Laptop' / None (không liên quan)"""
    text = GPU_CARD.sub("vga", text or "")
    if PHONE_TOPIC.search(text) and not re.search(r"laptop|máy tính|\bpc\b|màn hình", text, re.IGNORECASE):
        return None  # bài bán điện thoại
    wants_monitor = bool(WANT_MONITOR.search(text)) and not SELLING.search(text)  # vd "cần build PC + màn hình 27"
    is_pc = bool(PC_TOPIC.search(text))
    if LAPTOP_TOPIC.search(text) or (SPEC_TOPIC.search(text) and LAPTOP_HINT.search(text) and not is_pc):
        return MONITOR if wants_monitor else LAPTOP
    if SPEC_TOPIC.search(text) or (is_pc and not MONITOR_TOPIC.search(text)):
        return MONITOR if wants_monitor else PC
    if MONITOR_TOPIC.search(text):
        return MONITOR
    if is_pc:
        return PC
    return None
