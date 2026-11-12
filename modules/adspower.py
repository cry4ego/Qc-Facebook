"""
Kết nối Chrome của AdsPower — trình duyệt chống phát hiện vân tay (anti-detect).

Mỗi profile AdsPower có 1 vân tay (fingerprint) + 1 proxy dân cư riêng, nên Facebook thấy acc chạy
từ đúng 1 "thiết bị" như người thật, không bị tính là bot/spam. 1 tài khoản = 1 profile = 1 cửa sổ.

Cách hoạt động: AdsPower chạy 1 API cục bộ (mặc định http://local.adspower.net:50325).
  - start(config, user_id): mở trình duyệt của profile đó, trả về (địa_chỉ_debug, đường_dẫn_chromedriver)
    Selenium nối vào trình duyệt đã mở qua "debuggerAddress" (không tự mở Chrome, không dùng chrome_profile/).
  - stop(config, user_id): đóng trình duyệt.

Chuẩn bị (làm 1 lần trong app AdsPower):
  1. Tạo 1 profile, gán proxy dân cư Việt Nam (mua riêng, hoặc proxy có sẵn của AdsPower).
  2. Settings -> Local API -> bật (Enable), cổng mặc định 50325.
  3. Lấy "Profile ID" của profile (vd "j8x9k2a") -> dán vào Config.ADSPOWER_USER_IDS["default"].
AdsPower giới hạn ~1 lệnh API / giây nên các hàm dưới tự thử lại khi báo "too many request".
"""
import time
import json
import urllib.parse
import urllib.request

_RETRY = 6
_RETRY_WAIT = 2.0


def _get(base, path, params):
    url = base.rstrip("/") + path + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def _id_param(user_id):
    """AdsPower nhận profile theo "user_id" (chuỗi chữ-số như j8x9k2a) hoặc "serial_number" (số thứ tự trong danh sách
    Hồ sơ). Gói Free không gọi được API liệt kê hồ sơ, nên cho phép dùng luôn serial_number cho dễ lấy từ giao diện."""
    s = str(user_id).strip()
    return {"serial_number": s} if s.isdigit() else {"user_id": s}


def start(config, user_id):
    """Mở trình duyệt AdsPower của profile `user_id`. Trả về (debugger_address, webdriver_path).
    Nếu profile đã mở sẵn, AdsPower trả lại địa chỉ đang chạy. Lỗi -> ném RuntimeError (tiếng Việt)."""
    base = config.ADSPOWER_API
    last = None
    for _ in range(_RETRY):
        try:
            data = _get(base, "/api/v1/browser/start", {
                **_id_param(user_id),
                "open_tabs": 1,                         # không mở tab mặc định (quảng cáo) của AdsPower
                "headless": 1 if config.HEADLESS else 0,
            })
        except Exception as e:
            raise RuntimeError(
                f"Không gọi được API AdsPower ({base}). Hãy mở app AdsPower và bật Local API "
                f"(Settings -> Local API). Chi tiết: {e}")
        if data.get("code") == 0:
            d = data["data"]
            return d["ws"]["selenium"], d["webdriver"]
        last = data.get("msg", data)
        time.sleep(_RETRY_WAIT)                         # thường do giới hạn ~1 lệnh/giây -> chờ rồi thử lại
    raise RuntimeError(f"AdsPower không mở được profile '{user_id}': {last}")


def stop(config, user_id):
    """Đóng trình duyệt AdsPower của profile. Không ném lỗi (đóng được hay không cũng không sao)."""
    try:
        _get(config.ADSPOWER_API, "/api/v1/browser/stop", _id_param(user_id))
    except Exception:
        pass


def is_active(config, user_id):
    """Trình duyệt của profile này đang mở không."""
    try:
        data = _get(config.ADSPOWER_API, "/api/v1/browser/active", _id_param(user_id))
        return data.get("code") == 0 and data.get("data", {}).get("status") == "Active"
    except Exception:
        return False


def resolve_user_id(config, profile):
    """Lấy user_id AdsPower cho 1 thư mục profile; không có thì dùng "default"."""
    ids = getattr(config, "ADSPOWER_USER_IDS", {}) or {}
    user_id = ids.get(profile) or ids.get("default")
    if not user_id:
        raise RuntimeError(
            "Chưa khai báo user_id AdsPower. Mở config.py, dán Profile ID của AdsPower vào "
            "Config.ADSPOWER_USER_IDS[\"default\"] rồi chạy lại.")
    return user_id
