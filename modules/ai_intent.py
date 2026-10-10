"""
Phân loại ý định bằng AI (Google Gemini) — dùng KẾT HỢP với từ khóa: chỉ hỏi Gemini những bài mà bộ từ khóa chấm
KHÔNG XÁC ĐỊNH (từ khóa đã chắc MUA / BÁN thì không hỏi, đỡ tốn & đỡ chậm).

- Khóa API đặt trong file .env (GEMINI_API_KEY), bật/tắt bằng Config.INTENT_AI.
- Mỗi nội dung chỉ hỏi 1 lần, kết quả lưu vào CSDL (bảng ai_intent); tối đa GEMINI_MAX_CALLS_PER_DAY lần hỏi mỗi ngày.
- Gemini lỗi / hết hạn mức / mất mạng -> trả None: bài giữ KHÔNG XÁC ĐỊNH (bỏ qua), bot vẫn chạy bình thường.
"""
import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from modules.intent import BUY, SELL, UNKNOWN, text_key

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT_SECONDS = 20
MAX_TEXT_CHARS = 1500
LABELS = {"MUA": BUY, "BÁN": SELL, "KHÁC": UNKNOWN}
PROMPT = """Bạn phân loại bài đăng trong nhóm Facebook mua bán màn hình máy tính / PC / linh kiện ở Việt Nam.
Trả lời đúng 1 nhãn:
- MUA: người đăng đang CẦN MUA / TÌM màn hình, PC hoặc linh kiện (hỏi ai có bán, nêu ngân sách, nhờ tư vấn nên mua gì).
- BÁN: người đăng đang bán, thanh lý, pass, trade, hoặc là shop quảng cáo — kể cả quảng cáo đội lốt người mua
  (vd "anh em đang tìm màn 165Hz thì tham khảo chiếc này").
- KHÁC: hỏi sửa chữa, hỏi máy mình đang có bán được bao nhiêu, khoe góc máy, hoặc không rõ ý định.
Lý do: 1 câu ngắn tiếng Việt.

Bài đăng:
\"\"\"{text}\"\"\""""
SCHEMA = {
    "type": "OBJECT",
    "properties": {"label": {"type": "STRING", "enum": list(LABELS)}, "reason": {"type": "STRING"}},
    "required": ["label", "reason"],
}


@dataclass(frozen=True)
class AiVerdict:
    label: str      # MUA / BÁN / KHÔNG XÁC ĐỊNH (cùng nhãn với modules/intent.py)
    reason: str


def parse_response(data):
    """Kết quả Gemini (JSON trả về) -> AiVerdict"""
    out = json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
    return AiVerdict(LABELS.get(str(out.get("label", "")).strip().upper(), UNKNOWN), str(out.get("reason", ""))[:200])


def ask_gemini(text, api_key, model):
    """Gửi 1 bài cho Gemini, trả về AiVerdict (lỗi mạng / API -> ném lỗi)"""
    body = {
        "contents": [{"parts": [{"text": PROMPT.format(text=(text or "")[:MAX_TEXT_CHARS])}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": SCHEMA},
    }
    req = urllib.request.Request(API_URL.format(model=model), data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return parse_response(json.load(resp))
    except urllib.error.HTTPError as e:  # đọc lý do lỗi của Google (sai khóa, hết hạn mức…) — không in khóa ra log
        detail = e.read().decode("utf-8", "replace")[:200]
        raise RuntimeError(f"Gemini báo lỗi {e.code}: {detail}") from e


class AiIntent:
    """Hỏi Gemini có lưu kết quả (CSDL) và giới hạn số lần gọi mỗi ngày. Gọi: ai(text) -> AiVerdict hoặc None"""

    def __init__(self, db, config, logger, ask=ask_gemini):
        self.db, self.config, self.logger, self.ask = db, config, logger, ask
        self._limit_logged = False

    @property
    def enabled(self):
        return bool(self.config.INTENT_AI and self.config.GEMINI_API_KEY)

    def __call__(self, text):
        if not self.enabled:
            return None
        key = text_key(text)
        cached = self.db.get_ai_intent(key)
        if cached:
            return AiVerdict(cached["label"], cached["reason"])
        if self.db.ai_calls_today() >= self.config.GEMINI_MAX_CALLS_PER_DAY:
            if not self._limit_logged:
                self.logger.warning(f"Đã hỏi Gemini đủ {self.config.GEMINI_MAX_CALLS_PER_DAY} lần hôm nay "
                                    "(GEMINI_MAX_CALLS_PER_DAY) — bài không xác định sẽ bị bỏ qua tới mai")
                self._limit_logged = True
            return None
        try:
            verdict = self.ask(text, self.config.GEMINI_API_KEY, self.config.GEMINI_MODEL)
        except Exception as e:
            self.logger.warning(f"    ✗ Không hỏi được Gemini ({str(e).splitlines()[0][:160]}) — giữ KHÔNG XÁC ĐỊNH")
            return None
        self.db.save_ai_intent(key, verdict.label, verdict.reason, self.config.GEMINI_MODEL)
        return verdict
