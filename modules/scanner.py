"""
Cửa sổ QUÉT (python main.py quet [số] — chạy song song với cửa sổ BÌNH LUẬN, mỗi cửa sổ 1 Chrome riêng).
Có thể chạy SCAN_WINDOWS cửa sổ quét cùng lúc: chia nhau các nhóm qua bảng scan_claims (không quét trùng nhóm).

Lặp liên tục: chọn nhóm nên quét nhất (group_yield.next_group — nhóm tương tác cao 2 phút/lần, nhóm có khách / đông
bài 5 phút/lần…), chỉ xét bài đăng sau lần quét trước (quét lại rất nhanh), bài đạt mọi bộ lọc -> hàng chờ
(post_queue). Cửa sổ bình luận lấy bài MỚI NHẤT trong hàng chờ ra bình luận ngay.
Không bình luận, không tham gia nhóm — chỉ đọc (nhóm chưa tham gia được ghi lại để cửa sổ bình luận tự tham gia).
"""
import random
import time
from datetime import datetime

from modules.group_yield import EMPTY, group_score, next_group, scan_window

GROUPS_RELOAD_SECONDS = 600   # đọc lại danh sách nhóm (web có thể vừa bật / tắt danh sách) mỗi ... giây
NETWORK_ERRORS = ("ERR_NAME_NOT_RESOLVED", "ERR_INTERNET_DISCONNECTED", "ERR_NETWORK_CHANGED",
                  "ERR_CONNECTION_RESET", "ERR_CONNECTION_CLOSED", "ERR_TIMED_OUT", "ERR_CONNECTION_TIMED_OUT")
NETWORK_RETRY_SECONDS = 20    # mạng chập chờn: chờ ... giây rồi quét tiếp (Chrome vẫn dùng được, không cần mở lại)
NOTHING_DUE_SECONDS = 10      # chưa nhóm nào tới lượt: ... giây sau xem lại
CLAIM_STALE_MINUTES = 3       # nhóm cửa sổ quét khác giữ chỗ quá ... phút chưa xong (bị tắt giữa chừng) -> quét được


class Scanner:
    def __init__(self, watcher, config, logger, db, load_groups, daily_full, blocked_until, sleep=time.sleep,
                 scanner_id=1):
        self.watcher = watcher              # GroupWatcher dùng Chrome của cửa sổ quét này
        self.config, self.logger, self.db = config, logger, db
        self.load_groups = load_groups      # () -> danh sách nhóm đã xếp ưu tiên (main.load_target_groups)
        self.daily_full = daily_full        # () -> đủ số bài bình luận hôm nay chưa
        self.blocked_until = blocked_until  # () -> datetime | None (Facebook chặn bình luận)
        self.sleep = sleep
        self.id, self.tag = scanner_id, f"[Quét {scanner_id}]"
        self.groups, self.loaded_at = [], 0.0
        self.last_reason = {}               # lý do bỏ qua lần trước (chỉ ghi log khi lý do đổi)

    def _progress(self, **fields):
        try:
            self.db.set_scan_progress(self.id, **fields)
        except Exception:
            pass  # chỉ để web hiển thị

    def _waiting_reason(self):
        """Lý do tạm ngừng quét (None = quét được)"""
        if self.db.is_paused():
            return "Tạm dừng từ web"
        until = self.blocked_until()
        if until and datetime.now() < until:
            return f"Facebook đang chặn bình luận tới {until:%H:%M %d/%m} — tạm ngừng quét"
        if self.daily_full():
            return f"Đủ {self.config.MAX_COMMENTED_POSTS_PER_DAY} bài hôm nay — tạm ngừng quét tới ngày mai"
        return None

    def _pick(self, stats, yields):
        """Nhóm nên quét ngay mà cửa sổ quét khác không đang quét; giữ chỗ được thì trả về nhóm đó"""
        busy = self.db.busy_groups(self.id, CLAIM_STALE_MINUTES)
        free = [g for g in self.groups if g["group_url"] not in busy]
        g = next_group(free, stats, yields, self.config, self.db.scan_attempts())
        if g and self.db.claim_group(g["group_url"], self.id, CLAIM_STALE_MINUTES):
            return g
        return None

    def step(self):
        """1 bước: quét 1 nhóm (hoặc chờ). Trả về số bài mới đưa vào hàng chờ"""
        reason = self._waiting_reason()
        if reason:
            self._progress(phase=reason, group_name="", step="")
            self.sleep(30)
            return 0
        if not self.groups or time.time() - self.loaded_at > GROUPS_RELOAD_SECONDS:
            self.groups, self.loaded_at = self.load_groups(), time.time()
        stats = {s["group_url"]: s for s in self.db.all_group_stats()}
        yields = self.db.group_yields(self.config.YIELD_DAYS)
        g = self._pick(stats, yields)
        if not g:
            self._progress(phase="Chờ nhóm tới lượt quét", group_name="", step="")
            self.sleep(NOTHING_DUE_SECONDS)
            return 0
        try:
            added = self.scan(g, yields.get(g["group_url"]) or EMPTY, stats.get(g["group_url"]))
        finally:
            self.db.finish_claim(g["group_url"], self.id)  # cũng là "lần thử gần nhất" — nhóm bị bỏ qua chờ lượt sau
        self.sleep(random.uniform(*self.config.SCAN_PAUSE_SECONDS))
        return added

    def scan(self, g, y, stats):
        url, name = g["group_url"], g.get("group_name") or g["group_url"]
        window = scan_window(y, self.config)
        self._progress(phase="Quét nhóm", group_name=name, group_url=url, step=f"bài đăng trong {window} phút")
        started = time.time()
        try:
            result, posts = self.watcher.check_and_scan(g, window)
        except Exception as e:
            message = str(e).splitlines()[0][:150]
            if any(code in message for code in NETWORK_ERRORS):
                self.logger.warning(f"{self.tag} ⚠ Mạng chập chờn ({message.split('::')[-1]}) — "
                                    f"{NETWORK_RETRY_SECONDS} giây sau quét tiếp")
                self.sleep(NETWORK_RETRY_SECONDS)
                return 0
            self.logger.error(f"{self.tag} ✗ {name}: {message}")
            raise  # Chrome hỏng: vòng ngoài (main.task_scan) mở lại Chrome
        if result != "ok":
            if self.last_reason.get(url) != result:
                self.logger.info(f"{self.tag} ↷ {name}: {result}")
            self.last_reason[url] = result
            return 0
        self.last_reason.pop(url, None)
        score = group_score(g, stats, y)
        added = sum(self.db.enqueue_post(url, g.get("group_name", ""), p, score) for p in posts)
        secs = time.time() - started
        if added:
            self.logger.info(f"{self.tag} ★ {name}: {added} bài mới vào hàng chờ (bài ≤ {window} phút, {secs:.0f} giây)")
        self._progress(phase="Quét nhóm", group_name=name, step=f"xong trong {secs:.0f} giây, {added} bài mới",
                       last_scan_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        return added

    def run(self):
        while True:
            self.step()
