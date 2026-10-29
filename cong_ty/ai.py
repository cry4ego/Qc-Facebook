"""
Lớp gọi AI MIỄN PHÍ của công ty AI. Thử lần lượt các nguồn đã bật (Gemini -> Groq -> Ollama chạy trên máy bạn); mỗi nguồn có
trần lượt mỗi ngày (config.CONG_TY_AI_TRAN) lưu trong CSDL; nguồn báo hết lượt (HTTP 429) bị bỏ qua tới hết ngày; nguồn lỗi
(mất mạng, lỗi máy chủ, trả lời lạ) thì thử nguồn sau. Không nguồn nào trả lời được -> None và cuộc họp chạy bằng luật.

Chỉ có các nguồn miễn phí dưới đây; khóa nào chưa đặt thì nguồn đó tắt. Khóa API không bao giờ nằm trong URL, log hay
thông báo lỗi.
"""
import http.client
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Sequence

from modules.ai_intent import API_URL as GEMINI_URL
from modules.db import Database

TIMEOUT_GIAY = 60       # một lần gọi tối đa ... giây
NHIET_DO = 0.4          # đủ "sáng tạo" để viết mẫu bình luận nhưng vẫn bám số liệu
USER_AGENT = "QC-Facebook/1.0"   # một số máy chủ chặn User-Agent mặc định của urllib
TRAN_MAC_DINH = 40
MAX_TRA_LOI_BYTE = 256 * 1024   # câu trả lời của máy chủ AI dài hơn ngần này byte thì bỏ (chống treo máy / hết bộ nhớ)
LOI_NGHI_PHUT = 5               # một nguồn vừa lỗi thì bỏ qua ... phút (đỡ chờ quá giờ lặp lại ở mỗi vai)
GEMINI_MODEL_MAC_DINH = "gemini-flash-lite-latest"
HET_LUOT_GIO = 6         # nguồn báo hết lượt thì nghỉ ... giờ rồi thử lại (hạn mức miễn phí của Google được đặt lại giữa
                         # ngày theo giờ Việt Nam nên không thể coi là "hết tới nửa đêm")
DINH_DANG_GIO = "%Y-%m-%d %H:%M:%S"

SCHEMA = """CREATE TABLE IF NOT EXISTS ai_luot (
    ngay    TEXT NOT NULL,                -- YYYY-MM-DD
    nguon   TEXT NOT NULL,                -- gemini / groq / ollama
    so_luot INTEGER NOT NULL DEFAULT 0,   -- số lần gọi thành công trong ngày
    het     INTEGER NOT NULL DEFAULT 0,   -- 1 = nguồn từng báo hết lượt miễn phí trong ngày này
    het_luc TEXT,                         -- lúc báo hết lượt gần nhất (YYYY-MM-DD HH:MM:SS)
    PRIMARY KEY (ngay, nguon)
)"""


class LoiAI(Exception):
    """Gọi AI không được (mất mạng, lỗi máy chủ, trả lời lạ)"""


class HetLuot(LoiAI):
    """Nguồn báo hết lượt miễn phí (HTTP 429)"""


@dataclass(frozen=True)
class KetQuaAI:
    van_ban: str
    nguon: str


@dataclass(frozen=True)
class Nguon:
    ten: str                                   # gemini / groq / ollama
    tran_ngay: int                             # tối đa ... lượt mỗi ngày cho công ty
    hoi: Callable[[str, str], str]             # hoi(he_thong, nguoi_dung) -> văn bản trả lời; lỗi thì ném LoiAI / HetLuot


# ---------- đếm lượt ----------
def ensure_schema(db: Database) -> None:
    db.execute(SCHEMA)


def luot_hom_nay(db: Database, ngay: str) -> dict[str, dict]:
    """{nguồn: {'so_luot', 'het' (từng báo hết lượt trong ngày), 'het_luc'}} của ngày `ngay`"""
    return {r["nguon"]: {"so_luot": r["so_luot"], "het": bool(r["het"]), "het_luc": r["het_luc"]}
            for r in db.query("SELECT nguon, so_luot, het, het_luc FROM ai_luot WHERE ngay = ?", (ngay,))}


def ghi_luot(db: Database, ngay: str, nguon: str, het: bool = False, bay_gio: datetime | None = None) -> None:
    """het=True: ghi nguồn vừa báo hết lượt (lúc `bay_gio`); không thì cộng thêm 1 lượt đã dùng"""
    if het:
        db.execute("INSERT INTO ai_luot (ngay, nguon, so_luot, het, het_luc) VALUES (?, ?, 0, 1, ?) "
                   "ON CONFLICT(ngay, nguon) DO UPDATE SET het = 1, het_luc = excluded.het_luc",
                   (ngay, nguon, (bay_gio or datetime.now()).strftime(DINH_DANG_GIO)))
    else:
        db.execute("INSERT INTO ai_luot (ngay, nguon, so_luot, het) VALUES (?, ?, 1, 0) "
                   "ON CONFLICT(ngay, nguon) DO UPDATE SET so_luot = so_luot + 1", (ngay, nguon))


# ---------- gọi API ----------
def _goi_json(req: urllib.request.Request, timeout: int) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            tho = resp.read(MAX_TRA_LOI_BYTE + 1)
        if len(tho) > MAX_TRA_LOI_BYTE:
            raise LoiAI("câu trả lời của AI quá dài")
        return json.loads(tho.decode("utf-8"))
    except urllib.error.HTTPError as e:   # HTTPError là con của URLError nên phải đứng trước
        if e.code == 429:
            raise HetLuot("hết lượt miễn phí (HTTP 429)") from None
        raise LoiAI(f"máy chủ AI báo lỗi HTTP {e.code}") from None
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError, RecursionError) as e:
        # mất mạng, quá giờ, bị cắt ngang giữa chừng, trả về không phải JSON / JSON lồng quá sâu
        raise LoiAI(f"không gọi được AI ({type(e).__name__})") from None


def hoi_gemini(khoa: str, model: str, he_thong: str, nguoi_dung: str, timeout: int = TIMEOUT_GIAY) -> str:
    body = {"systemInstruction": {"parts": [{"text": he_thong}]},
            "contents": [{"role": "user", "parts": [{"text": nguoi_dung}]}],
            "generationConfig": {"temperature": NHIET_DO, "responseMimeType": "application/json"}}
    req = urllib.request.Request(GEMINI_URL.format(model=model), data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": khoa,
                                          "User-Agent": USER_AGENT})
    data = _goi_json(req, timeout)
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise LoiAI("Gemini không trả lời (có thể bị bộ lọc an toàn chặn)") from None


def hoi_openai(url: str, khoa: str | None, model: str, he_thong: str, nguoi_dung: str,
               timeout: int = TIMEOUT_GIAY) -> str:
    """API kiểu OpenAI (Groq, Ollama...). khoa=None: không gửi Authorization (Ollama trên máy bạn không cần khóa)"""
    body = {"model": model, "temperature": NHIET_DO, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": he_thong}, {"role": "user", "content": nguoi_dung}]}
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if khoa:
        headers["Authorization"] = f"Bearer {khoa}"
    data = _goi_json(urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers), timeout)
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LoiAI("AI không trả lời đúng định dạng") from None


def doc_json(van_ban: str) -> dict:
    """Lấy đối tượng JSON từ câu trả lời của AI (có thể bọc trong ```json … ``` hoặc kèm chữ giải thích)"""
    chu = (van_ban or "").strip()
    dau, cuoi = chu.find("{"), chu.rfind("}")
    for ung_vien in (chu, chu[dau:cuoi + 1] if 0 <= dau < cuoi else ""):
        try:
            data = json.loads(ung_vien)
        except (ValueError, RecursionError):   # JSON hỏng, hoặc lồng quá sâu ("[[[[…")
            continue
        if isinstance(data, dict):
            return data
    raise ValueError("Câu trả lời của AI không có đối tượng JSON")


# ---------- bộ chọn nguồn ----------
class BoAI:
    """Hỏi AI qua các nguồn miễn phí theo thứ tự, đếm lượt mỗi ngày trong CSDL"""

    def __init__(self, db: Database, nguon: Sequence[Nguon], hom_nay: Callable[[], date] = date.today,
                 logger: logging.Logger | None = None, bay_gio: Callable[[], datetime] = datetime.now):
        self.db, self.nguon, self.hom_nay, self.bay_gio = db, list(nguon), hom_nay, bay_gio
        self.log = logger or logging.getLogger(__name__)
        self._loi_den: dict[str, datetime] = {}     # nguồn vừa lỗi -> bỏ qua tới lúc này (chỉ trong tiến trình này)
        ensure_schema(db)

    def _ngay(self) -> str:
        return self.hom_nay().strftime("%Y-%m-%d")

    def _dang_het(self, d: dict) -> bool:
        """Nguồn đang trong thời gian nghỉ sau khi báo hết lượt (chưa quá HET_LUOT_GIO giờ)?"""
        if not d["het"]:
            return False
        if not d.get("het_luc"):
            return True
        return self.bay_gio() - datetime.strptime(d["het_luc"], DINH_DANG_GIO) < timedelta(hours=HET_LUOT_GIO)

    def _con_luot(self, n: Nguon, luot: dict[str, dict]) -> bool:
        d = luot.get(n.ten, {"so_luot": 0, "het": False, "het_luc": None})
        return not self._dang_het(d) and d["so_luot"] < n.tran_ngay

    def con_luot(self) -> bool:
        luot = luot_hom_nay(self.db, self._ngay())
        return any(self._con_luot(n, luot) for n in self.nguon)

    def hoi(self, he_thong: str, nguoi_dung: str, nhan: str = "") -> KetQuaAI | None:
        """Hỏi nguồn đầu tiên còn lượt và trả lời được; None nếu không nguồn nào được. `nhan` chỉ để ghi log"""
        ngay = self._ngay()
        for n in self.nguon:
            if not self._con_luot(n, luot_hom_nay(self.db, ngay)) or self._loi_den.get(n.ten, datetime.min) > self.bay_gio():
                continue
            try:
                van_ban = n.hoi(he_thong, nguoi_dung)
            except HetLuot as e:
                ghi_luot(self.db, ngay, n.ten, het=True, bay_gio=self.bay_gio())
                self.log.warning("AI %s (%s): %s — nghỉ %d giờ rồi thử lại", n.ten, nhan, e, HET_LUOT_GIO)
                continue
            except Exception as e:   # nguồn AI là nơi bên ngoài: lỗi gì cũng chỉ có nghĩa "nguồn này hỏng", sang nguồn khác
                self._loi_den[n.ten] = self.bay_gio() + timedelta(minutes=LOI_NGHI_PHUT)
                self.log.warning("AI %s (%s): %s — thử nguồn khác", n.ten, nhan, e if isinstance(e, LoiAI) else type(e).__name__)
                continue
            ghi_luot(self.db, ngay, n.ten)
            return KetQuaAI(van_ban, n.ten)
        return None

    def trang_thai(self) -> list[dict]:
        luot = luot_hom_nay(self.db, self._ngay())
        trong = {"so_luot": 0, "het": False, "het_luc": None}
        return [{"nguon": n.ten, "tran": n.tran_ngay, "so_luot": luot.get(n.ten, trong)["so_luot"],
                 "het": self._dang_het(luot.get(n.ten, trong))} for n in self.nguon]


def _nguon_gemini(khoa: str, model: str, tran: int) -> Nguon:
    return Nguon("gemini", tran, lambda he_thong, nguoi_dung: hoi_gemini(khoa, model, he_thong, nguoi_dung))


def _nguon_openai(ten: str, url: str, khoa: str | None, model: str, tran: int) -> Nguon:
    return Nguon(ten, tran, lambda he_thong, nguoi_dung: hoi_openai(url, khoa, model, he_thong, nguoi_dung))


def tao_bo_ai(db: Database, config, hom_nay: Callable[[], date] = date.today,
              logger: logging.Logger | None = None) -> BoAI:
    """Dựng bộ AI từ cấu hình: chỉ nguồn nào có khóa / mô hình mới được bật. Thiếu cấu hình = không có nguồn nào"""
    tran = getattr(config, "CONG_TY_AI_TRAN", None) or {}
    nguon: list[Nguon] = []
    if getattr(config, "GEMINI_API_KEY", None):
        nguon.append(_nguon_gemini(config.GEMINI_API_KEY, getattr(config, "GEMINI_MODEL", GEMINI_MODEL_MAC_DINH),
                                   tran.get("gemini", TRAN_MAC_DINH)))
    if getattr(config, "GROQ_API_KEY", None):
        nguon.append(_nguon_openai("groq", "https://api.groq.com/openai/v1/chat/completions", config.GROQ_API_KEY,
                                   getattr(config, "GROQ_MODEL", "llama-3.3-70b-versatile"),
                                   tran.get("groq", TRAN_MAC_DINH)))
    if getattr(config, "OLLAMA_MODEL", None):
        nguon.append(_nguon_openai("ollama", getattr(config, "OLLAMA_URL", "http://127.0.0.1:11434/v1/chat/completions"),
                                   None, config.OLLAMA_MODEL, tran.get("ollama", 200)))
    return BoAI(db, nguon, hom_nay, logger)
