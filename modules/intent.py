"""
Phân loại ý định bài viết: MUA (người cần mua) / BÁN (người bán) / KHÔNG XÁC ĐỊNH.

Dựa trên từ khóa có trọng số trong file cấu hình riêng (mặc định data/tu_khoa_mua_ban.txt — sửa file, không sửa code):
mỗi từ khóa khớp được cộng điểm vào phía MUA hoặc BÁN (mỗi từ khóa tính 1 lần; nằm trong ~50 ký tự đầu bài thì x1,5
vì câu mở đầu thường nói rõ ý định). Bài là MUA khi điểm MUA ≥ min_score và hơn điểm BÁN ít nhất margin; BÁN tương tự;
còn lại là KHÔNG XÁC ĐỊNH (bot bỏ qua, ghi log để xem lại).
"""
import os
import re
import hashlib
import logging
import unicodedata
from dataclasses import dataclass

log = logging.getLogger(__name__)

BUY, SELL, UNKNOWN = "MUA", "BÁN", "KHÔNG XÁC ĐỊNH"
DEFAULT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tu_khoa_mua_ban.txt")
DEFAULT_WEIGHT = 2.0
HEAD_CHARS = 50          # từ khóa bắt đầu trong ... ký tự đầu bài được nhân HEAD_BONUS
HEAD_BONUS = 1.5
SECTIONS = {"MUA": "buy", "BÁN": "sell", "BAN": "sell"}
WEIGHT_SUFFIX = re.compile(r"^(.*?)\s+\|\s*(\d+(?:[.,]\d+)?)\s*(?:\|\s*(.+?))?\s*$")  # "… | điểm | tên"


@dataclass(frozen=True)
class Rule:
    label: str           # cụm từ / regex như viết trong file (để ghi log)
    pattern: re.Pattern
    weight: float


@dataclass(frozen=True)
class Rules:
    buy: tuple
    sell: tuple


@dataclass(frozen=True)
class IntentResult:
    label: str           # MUA / BÁN / KHÔNG XÁC ĐỊNH
    buy_score: float
    sell_score: float
    buy_hits: tuple      # từ khóa MUA đã khớp
    sell_hits: tuple     # từ khóa BÁN đã khớp
    ai_reason: str = ""  # có = nhãn do Gemini chấm (từ khóa chưa đủ chắc)

    @property
    def reason(self):
        hits = lambda h: ", ".join(h) or "—"
        words = (f"điểm mua {self.buy_score:g} / bán {self.sell_score:g} · mua: {hits(self.buy_hits)} "
                 f"· bán: {hits(self.sell_hits)}")
        if self.ai_reason:
            return f"{self.label} (AI Gemini: {self.ai_reason}) · từ khóa chưa chắc: {words}"
        return f"{self.label} ({words})"


AGE_WORDS = re.compile(r"\d+\s*(phút|giờ|ngày|tuần|min|hr|h|m|d)\b|vừa xong|just now", re.IGNORECASE)


def plain_text(text):
    """Nội dung bài để so sánh: chữ thường, gom khoảng trắng, bỏ mốc thời gian ("5 phút") vì nó đổi mỗi lần quét"""
    return " ".join(AGE_WORDS.sub(" ", (text or "").lower()).split())


def text_key(text):
    """Mã ngắn của nội dung bài — nhận ra bài đã xét khi gặp lại (kể cả lúc chưa lấy link bài)"""
    return hashlib.sha1(plain_text(text)[:300].encode("utf-8")).hexdigest()[:16]


def normalize(text):
    """Chữ thường, dạng Unicode dựng sẵn (NFC), gom khoảng trắng trong từng dòng"""
    text = unicodedata.normalize("NFC", text or "").lower()
    return "\n".join(re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines())


def _phrase_pattern(phrase):
    """Cụm từ -> regex khớp nguyên từ (không khớp 'bán' trong 'bánh'), khoảng trắng linh hoạt"""
    words = [re.escape(w) for w in normalize(phrase).split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)")


def parse_line(line):
    """1 dòng từ khóa -> Rule; dòng hỏng (regex sai / rỗng) -> ValueError kèm lý do"""
    m = WEIGHT_SUFFIX.match(line)
    body, weight = (m.group(1), float(m.group(2).replace(",", "."))) if m else (line, DEFAULT_WEIGHT)
    name = m.group(3) if m else None  # tên dễ đọc cho dòng regex (hiện trong log thay cho cả biểu thức)
    if body.lower().startswith("re:"):
        source = body[3:].strip()
        if not source:
            raise ValueError("dòng 're:' trống")
        try:
            return Rule(name or source, re.compile(source, re.IGNORECASE | re.MULTILINE), weight)
        except re.error as e:
            raise ValueError(f"regex sai ({e})") from e
    body = body.strip()
    if not normalize(body):
        raise ValueError("cụm từ trống")
    return Rule(body, _phrase_pattern(body), weight)


def parse_sections(content, sections, errors=None):
    """Đọc file dạng mục: dòng '[TÊN MỤC]' rồi mỗi dòng 1 cụm từ ('cụm từ | trọng số') hoặc 're: <regex>',
    dòng bắt đầu bằng # là chú thích. sections: {TÊN MỤC viết hoa: khóa}. Trả về {khóa: [Rule]}.
    Dòng hỏng bị bỏ qua (chỉ dòng đó) và ghi vào errors (nếu truyền list) — 1 dòng gõ sai không làm hỏng cả bộ lọc"""
    found = {key: [] for key in sections.values()}
    side = None
    for no, raw in enumerate((content or "").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        header = re.fullmatch(r"\[(.+)\]", line)
        if header:
            side = sections.get(unicodedata.normalize("NFC", header.group(1).strip().upper()))
            continue
        if side:
            try:
                found[side].append(parse_line(line))
            except ValueError as e:
                if errors is not None:
                    errors.append(f"dòng {no}: {e} — {line[:80]}")
    return found


def parse_rules(content, errors=None):
    """Đọc nội dung file từ khóa: các mục [MUA] / [BÁN] (định dạng dòng: xem parse_sections)"""
    found = parse_sections(content, SECTIONS, errors)
    return Rules(tuple(found["buy"]), tuple(found["sell"]))


_cache = {}


def load_cached(path, parse, label):
    """Đọc file cấu hình bằng parse(nội dung, errors); đọc lại khi file được sửa (so thời gian sửa file).
    Dòng hỏng: bỏ qua + ghi cảnh báo vào log chạy. Không đọc được file (bị xóa / đang khóa): dùng bản đọc lần trước"""
    cached = _cache.get(path)
    try:
        mtime = os.path.getmtime(path)
        if cached and cached[0] == mtime:
            return cached[1]
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        if cached:
            log.warning(f"Không đọc được file {label} {path} ({e}) — dùng bản đọc lần trước")
            return cached[1]
        raise
    errors = []
    result = parse(content, errors)
    for err in errors:
        log.warning(f"File {label} {os.path.basename(path)}: bỏ qua {err}")
    _cache[path] = (mtime, result)
    return result


def load_rules(path=DEFAULT_FILE):
    """Bộ từ khóa MUA / BÁN (data/tu_khoa_mua_ban.txt) — sửa file là có hiệu lực, không cần chạy lại"""
    return load_cached(path, parse_rules, "từ khóa")


def _score(text, rules):
    total, hits = 0.0, []
    for r in rules:
        m = r.pattern.search(text)
        if m:
            total += r.weight * (HEAD_BONUS if m.start() < HEAD_CHARS else 1)
            hits.append(r.label)
    return round(total, 1), tuple(hits)


def classify_intent(text, rules, min_score=3, margin=2):
    """Phân loại 1 bài viết -> IntentResult (label MUA / BÁN / KHÔNG XÁC ĐỊNH + điểm + từ khóa đã khớp)"""
    t = normalize(text)
    buy, buy_hits = _score(t, rules.buy)
    sell, sell_hits = _score(t, rules.sell)
    if buy >= min_score and buy - sell >= margin:
        label = BUY
    elif sell >= min_score and sell - buy >= margin:
        label = SELL
    else:
        label = UNKNOWN
    return IntentResult(label, buy, sell, buy_hits, sell_hits)
