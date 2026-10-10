"""AI (Gemini) kết hợp từ khóa: chỉ hỏi khi từ khóa KHÔNG XÁC ĐỊNH, có lưu kết quả, giới hạn/ngày, lỗi không làm dừng bot.
Không gọi mạng thật — dùng hàm hỏi giả."""
import json
from types import SimpleNamespace

from modules.ai_intent import AiIntent, AiVerdict, parse_response
from modules.db import Database
from modules.filters import PostCandidate
from modules.intent import BUY, DEFAULT_FILE, SELL, UNKNOWN

LOG = SimpleNamespace(info=lambda *a: None, warning=lambda *a: None, error=lambda *a: None)
UNCLEAR = "Màn 24inch ở cao bằng"   # từ khóa không đủ chắc (bài thật)


def cfg(**over):
    base = dict(INTENT_AI=True, GEMINI_API_KEY="khoa-gia", GEMINI_MODEL="gemini-test", GEMINI_MAX_CALLS_PER_DAY=500,
                INTENT_KEYWORDS_FILE=DEFAULT_FILE, INTENT_MIN_SCORE=3, INTENT_MARGIN=2)
    return SimpleNamespace(**{**base, **over})


def make_ai(tmp_path, answer=AiVerdict(BUY, "người đăng đang tìm màn"), **over):
    calls = []

    def ask(text, key, model):
        calls.append(text)
        if isinstance(answer, Exception):
            raise answer
        return answer
    return AiIntent(Database(str(tmp_path / "t.db")), cfg(**over), LOG, ask=ask), calls


def test_ai_used_only_when_keywords_are_unsure(tmp_path):
    ai, calls = make_ai(tmp_path)
    assert PostCandidate("Thanh lý màn Dell giá 2tr, bao test", 0, cfg(), lambda: None, ai=ai).intent.label == SELL
    assert PostCandidate("Cần tìm màn 27 inch tầm 3tr", 0, cfg(), lambda: None, ai=ai).intent.label == BUY
    assert calls == []                                        # từ khóa đã chắc -> không hỏi Gemini
    r = PostCandidate(UNCLEAR, 0, cfg(), lambda: None, ai=ai).intent
    assert r.label == BUY and "AI Gemini" in r.reason and calls == [UNCLEAR]


def test_each_text_is_asked_once_then_cached(tmp_path):
    ai, calls = make_ai(tmp_path)
    ai(UNCLEAR)
    ai(UNCLEAR)
    assert len(calls) == 1


def test_daily_limit_and_errors_fall_back_to_unknown(tmp_path):
    ai, calls = make_ai(tmp_path, GEMINI_MAX_CALLS_PER_DAY=0)
    assert ai(UNCLEAR) is None and calls == []
    ai, _ = make_ai(tmp_path, answer=RuntimeError("Gemini báo lỗi 429"))
    assert ai("bài khác hẳn") is None
    assert PostCandidate(UNCLEAR, 0, cfg(), lambda: None, ai=ai).intent.label == UNKNOWN


def test_disabled_without_key_or_switch(tmp_path):
    ai, calls = make_ai(tmp_path, GEMINI_API_KEY="")
    assert ai(UNCLEAR) is None
    ai, calls = make_ai(tmp_path, INTENT_AI=False)
    assert ai(UNCLEAR) is None and calls == []


def test_parse_gemini_response():
    data = {"candidates": [{"content": {"parts": [{"text": json.dumps({"label": "BÁN", "reason": "shop quảng cáo"})}]}}]}
    assert parse_response(data) == AiVerdict(SELL, "shop quảng cáo")
    data["candidates"][0]["content"]["parts"][0]["text"] = json.dumps({"label": "KHÁC", "reason": "hỏi sửa"})
    assert parse_response(data).label == UNKNOWN
