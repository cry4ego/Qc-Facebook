"""Lớp AI miễn phí: thử lần lượt các nguồn, đếm lượt mỗi ngày, dự phòng khi hết lượt / lỗi; gọi Gemini và API kiểu OpenAI."""
import http.client
import io
import json
import urllib.error
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from cong_ty import ai
from modules.db import Database

HOM_NAY = date(2026, 10, 24)
NGAY_MAI = date(2026, 10, 25)


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "t.db"))
    ai.ensure_schema(database)
    return database


def nguon(ten, tran=5, tra_loi="{}", loi=None):
    """Nguồn giả: trả lời `tra_loi` (hoặc ném `loi`); trả về (nguồn, danh sách ghi mỗi lần bị hỏi)"""
    da_hoi = []

    def hoi(he_thong, nguoi_dung):
        da_hoi.append((he_thong, nguoi_dung))
        if loi:
            raise loi
        return tra_loi
    return ai.Nguon(ten, tran, hoi), da_hoi


def bo(db, *nguon_ai, hom_nay=HOM_NAY):
    return ai.BoAI(db, list(nguon_ai), hom_nay=lambda: hom_nay)


# ---------- bộ chọn nguồn + đếm lượt ----------
def test_first_source_answers_and_is_counted(db):
    gemini, hoi_gemini = nguon("gemini", tra_loi='{"a": 1}')
    groq, hoi_groq = nguon("groq")
    kq = bo(db, gemini, groq).hoi("hệ thống", "người dùng", nhan="phan_tich")
    assert (kq.van_ban, kq.nguon) == ('{"a": 1}', "gemini") and len(hoi_gemini) == 1 and hoi_groq == []
    assert ai.luot_hom_nay(db, "2026-10-24")["gemini"]["so_luot"] == 1


def test_source_over_its_daily_cap_is_skipped(db):
    gemini, _ = nguon("gemini", tran=2)
    groq, _ = nguon("groq")
    bo_ai = bo(db, gemini, groq)
    assert [bo_ai.hoi("s", "u").nguon for _ in range(3)] == ["gemini", "gemini", "groq"]


def test_counts_survive_a_new_instance_and_reset_the_next_day(db):
    gemini, _ = nguon("gemini", tran=1)
    assert bo(db, gemini).hoi("s", "u") is not None
    cung_ngay = bo(db, gemini)
    assert cung_ngay.hoi("s", "u") is None and not cung_ngay.con_luot()
    assert bo(db, gemini, hom_nay=NGAY_MAI).hoi("s", "u") is not None


def test_error_falls_through_to_the_next_source_and_is_not_counted(db):
    hong, _ = nguon("gemini", loi=ai.LoiAI("mất mạng"))
    tot, _ = nguon("groq")
    assert bo(db, hong, tot).hoi("s", "u").nguon == "groq"
    assert ai.luot_hom_nay(db, "2026-10-24").get("gemini", {"so_luot": 0})["so_luot"] == 0


def test_quota_error_marks_the_source_exhausted_for_the_day_only(db):
    het, hoi_het = nguon("gemini", loi=ai.HetLuot("429"))
    tot, _ = nguon("groq")
    bo_ai = bo(db, het, tot)
    bo_ai.hoi("s", "u")
    bo_ai.hoi("s", "u")
    assert len(hoi_het) == 1                                        # lần 2 không thử lại nguồn đã hết lượt
    assert next(t for t in bo_ai.trang_thai() if t["nguon"] == "gemini")["het"] is True
    bo(db, het, tot, hom_nay=NGAY_MAI).hoi("s", "u")
    assert len(hoi_het) == 2                                        # sang ngày mới thử lại


def test_exhausted_flag_expires_within_the_day_because_the_free_quota_resets_in_the_afternoon(db):
    gio = [datetime(2026, 10, 24, 9, 0)]
    het, hoi_het = nguon("gemini", loi=ai.HetLuot("429"))
    tot, _ = nguon("groq")
    bo_ai = ai.BoAI(db, [het, tot], hom_nay=lambda: HOM_NAY, bay_gio=lambda: gio[0])
    bo_ai.hoi("s", "u")                                   # 9 giờ: Gemini báo hết lượt
    gio[0] = datetime(2026, 10, 24, 12, 0)
    bo_ai.hoi("s", "u")
    assert len(hoi_het) == 1                              # mới 3 giờ: chưa thử lại
    assert next(t for t in bo_ai.trang_thai() if t["nguon"] == "gemini")["het"] is True
    gio[0] = datetime(2026, 10, 24, 16, 0)
    bo_ai.hoi("s", "u")
    assert len(hoi_het) == 2                              # quá 6 giờ: thử lại


def test_no_source_or_only_failing_sources_gives_none(db):
    assert bo(db).hoi("s", "u") is None and not bo(db).con_luot()
    hong, _ = nguon("gemini", loi=ai.LoiAI("x"))
    assert bo(db, hong).hoi("s", "u") is None


def test_status_lists_every_source_with_cap_and_usage(db):
    gemini, _ = nguon("gemini")
    groq, _ = nguon("groq")
    bo_ai = bo(db, gemini, groq)
    bo_ai.hoi("s", "u")
    assert bo_ai.trang_thai() == [{"nguon": "gemini", "tran": 5, "so_luot": 1, "het": False},
                                  {"nguon": "groq", "tran": 5, "so_luot": 0, "het": False}]


def cau_hinh(**kw):
    return SimpleNamespace(**{"GEMINI_API_KEY": None, "GEMINI_MODEL": "gm", "GROQ_API_KEY": None, "GROQ_MODEL": "lm",
                              "OLLAMA_MODEL": None, "OLLAMA_URL": "http://127.0.0.1:11434/v1/chat/completions",
                              "CONG_TY_AI_TRAN": {"gemini": 40, "groq": 30, "ollama": 200}, **kw})


def test_missing_configuration_means_no_sources(db):
    assert ai.tao_bo_ai(db, SimpleNamespace()).trang_thai() == []


def test_sources_follow_the_configuration(db):
    assert ai.tao_bo_ai(db, cau_hinh()).trang_thai() == []
    day_du = ai.tao_bo_ai(db, cau_hinh(GEMINI_API_KEY="k1", GROQ_API_KEY="k2", OLLAMA_MODEL="qwen"))
    assert [(t["nguon"], t["tran"]) for t in day_du.trang_thai()] == [("gemini", 40), ("groq", 30), ("ollama", 200)]
    assert [t["nguon"] for t in ai.tao_bo_ai(db, cau_hinh(GROQ_API_KEY="k")).trang_thai()] == ["groq"]


# ---------- gọi API thật (urlopen giả) ----------
def gia_urlopen(monkeypatch, data=None, loi=None):
    """Thay urlopen: ghi lại các request, trả `data` (JSON) hoặc ném `loi`"""
    da_goi = []

    def urlopen(req, timeout=None):
        da_goi.append(req)
        if loi:
            raise loi
        return io.BytesIO(json.dumps(data).encode("utf-8"))
    monkeypatch.setattr(ai.urllib.request, "urlopen", urlopen)
    return da_goi


def header(req):
    return {k.lower(): v for k, v in req.header_items()}


def test_gemini_request_and_reply(monkeypatch):
    goi = gia_urlopen(monkeypatch, {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]})
    van_ban = ai.hoi_gemini("KHOA-BI-MAT", "gemini-x", "hệ thống", "người dùng")
    req, body = goi[0], json.loads(goi[0].data)
    assert "gemini-x" in req.full_url and header(req)["x-goog-api-key"] == "KHOA-BI-MAT" and "KHOA" not in req.full_url
    assert body["systemInstruction"]["parts"][0]["text"] == "hệ thống"
    assert body["contents"][0]["parts"][0]["text"] == "người dùng"
    assert body["generationConfig"]["responseMimeType"] == "application/json" and van_ban == '{"ok": true}'


def test_gemini_quota_error_is_exhausted_and_other_errors_never_leak_the_key(monkeypatch):
    gia_urlopen(monkeypatch, loi=urllib.error.HTTPError("u", 429, "Too Many", {}, io.BytesIO(b'{"error": "quota"}')))
    with pytest.raises(ai.HetLuot):
        ai.hoi_gemini("KHOA-BI-MAT", "m", "s", "u")
    gia_urlopen(monkeypatch, loi=urllib.error.HTTPError("u", 500, "Boom", {}, io.BytesIO(b"oops")))
    with pytest.raises(ai.LoiAI) as e:
        ai.hoi_gemini("KHOA-BI-MAT", "m", "s", "u")
    assert not isinstance(e.value, ai.HetLuot) and "KHOA-BI-MAT" not in str(e.value) and "500" in str(e.value)


class PhanHoiHong(io.BytesIO):
    """Máy chủ cắt ngang giữa chừng: http.client ném IncompleteRead (không phải OSError)"""

    def read(self, *_):
        raise http.client.IncompleteRead(b"mot-phan")


def test_truncated_and_oversized_replies_are_loi_ai_not_crashes(monkeypatch):
    monkeypatch.setattr(ai.urllib.request, "urlopen", lambda req, timeout=None: PhanHoiHong())
    with pytest.raises(ai.LoiAI):
        ai.hoi_gemini("k", "m", "s", "u")
    qua_dai = {"candidates": [{"content": {"parts": [{"text": "x" * (ai.MAX_TRA_LOI_BYTE + 10)}]}}]}
    gia_urlopen(monkeypatch, qua_dai)
    with pytest.raises(ai.LoiAI, match="quá dài"):
        ai.hoi_gemini("k", "m", "s", "u")


def test_a_deeply_nested_reply_is_a_value_error_not_a_recursion_crash():
    with pytest.raises(ValueError):
        ai.doc_json("[" * 200_000)


def test_unexpected_exceptions_from_a_source_just_move_on_to_the_next(db):
    la, _ = nguon("gemini", loi=KeyError("hỏng bất ngờ"))
    tot, _ = nguon("groq")
    assert bo(db, la, tot).hoi("s", "u").nguon == "groq"


def test_a_failing_source_is_skipped_for_a_few_minutes_then_tried_again(db):
    gio = [datetime(2026, 10, 24, 7, 0)]
    hong, hoi_hong = nguon("gemini", loi=ai.LoiAI("quá giờ"))
    tot, _ = nguon("groq")
    bo_ai = ai.BoAI(db, [hong, tot], hom_nay=lambda: HOM_NAY, bay_gio=lambda: gio[0])
    for _ in range(3):
        bo_ai.hoi("s", "u")
    assert len(hoi_hong) == 1                                       # 2 lần sau bỏ qua nguồn đang lỗi, khỏi đợi quá giờ nữa
    gio[0] += timedelta(minutes=ai.LOI_NGHI_PHUT + 1)
    bo_ai.hoi("s", "u")
    assert len(hoi_hong) == 2


def test_network_error_and_odd_replies_are_loi_ai(monkeypatch):
    gia_urlopen(monkeypatch, loi=urllib.error.URLError("không có mạng"))
    with pytest.raises(ai.LoiAI):
        ai.hoi_gemini("k", "m", "s", "u")
    gia_urlopen(monkeypatch, {"candidates": []})                     # Gemini từ chối trả lời (bộ lọc an toàn)
    with pytest.raises(ai.LoiAI):
        ai.hoi_gemini("k", "m", "s", "u")


def test_openai_compatible_request_and_reply(monkeypatch):
    goi = gia_urlopen(monkeypatch, {"choices": [{"message": {"content": '{"ok": 1}'}}]})
    van_ban = ai.hoi_openai("https://api.groq.com/openai/v1/chat/completions", "KHOA", "llama", "hệ thống", "người dùng")
    req, body = goi[0], json.loads(goi[0].data)
    assert req.full_url.endswith("/chat/completions") and header(req)["authorization"] == "Bearer KHOA"
    assert body["model"] == "llama" and body["messages"][0] == {"role": "system", "content": "hệ thống"}
    assert body["messages"][1] == {"role": "user", "content": "người dùng"}
    assert body["response_format"] == {"type": "json_object"} and van_ban == '{"ok": 1}'


def test_openai_compatible_without_a_key_sends_no_authorization_header(monkeypatch):
    goi = gia_urlopen(monkeypatch, {"choices": [{"message": {"content": "{}"}}]})
    ai.hoi_openai("http://127.0.0.1:11434/v1/chat/completions", None, "qwen", "s", "u")
    assert "authorization" not in header(goi[0])


def test_openai_compatible_quota_and_shape_errors(monkeypatch):
    gia_urlopen(monkeypatch, loi=urllib.error.HTTPError("u", 429, "Too Many", {}, io.BytesIO(b"{}")))
    with pytest.raises(ai.HetLuot):
        ai.hoi_openai("http://x/chat/completions", "k", "m", "s", "u")
    gia_urlopen(monkeypatch, {"choices": []})
    with pytest.raises(ai.LoiAI):
        ai.hoi_openai("http://x/chat/completions", "k", "m", "s", "u")


# ---------- đọc JSON từ câu trả lời của AI ----------
@pytest.mark.parametrize("van_ban", ['{"a": 1}', '```json\n{"a": 1}\n```', 'Đây là kết quả:\n{"a": 1}\nHết.', '  {"a": 1}  '])
def test_json_is_found_in_plain_fenced_and_wrapped_replies(van_ban):
    assert ai.doc_json(van_ban) == {"a": 1}


@pytest.mark.parametrize("van_ban", ["", "không có json", "[1, 2]", '{"a": ', "null"])
def test_replies_without_a_json_object_are_rejected(van_ban):
    with pytest.raises(ValueError):
        ai.doc_json(van_ban)
