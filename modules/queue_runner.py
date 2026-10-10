"""
Cửa sổ BÌNH LUẬN khi chạy song song (Config.PARALLEL): lấy bài MỚI NHẤT trong hàng chờ (do cửa sổ QUÉT tìm) và bình
luận ngay — không tự quét nhóm nữa. Lúc rảnh (hàng chờ trống): tự tham gia nhóm cửa sổ quét báo chưa tham gia, kiểm tra
lại bài đã bình luận, đăng bài theo lịch (dùng chung Chrome này). Mọi giới hạn cũ giữ nguyên: số bài/ngày, nghỉ giữa
2 bài, nghỉ khi bị Facebook chặn, tạm dừng từ web.
"""
import random
import time
from datetime import datetime, timedelta

from modules import group_checker as gc
from modules.db import Q_DONE, Q_RUNNING, Q_SKIPPED, Q_WAITING

COMMENTED = ("Hoàn tất", "Một phần")
RETRY_MARK = "thử lại sau lần thất bại (chưa gửi được bình luận nào)"


class QueueRunner:
    def __init__(self, watcher, commenter, pick_comments, config, logger, db, between=None,
                 housekeeping_extra=None, sleep=time.sleep, clock=time.time):
        self.watcher, self.commenter, self.pick_comments = watcher, commenter, pick_comments
        self.config, self.logger, self.db = config, logger, db
        self.between = between or (lambda: None)                  # đăng bài theo lịch nếu đến giờ
        self.housekeeping_extra = housekeeping_extra or (lambda: None)  # vd tìm nhóm mới mỗi 24 giờ
        self.sleep, self.clock = sleep, clock
        self.housekept_at = None

    def _progress(self, **fields):
        try:
            self.db.set_progress(**fields)
        except Exception:
            pass

    def idle(self, seconds, phase, step=""):
        """Chờ ... giây; trong lúc chờ vẫn đăng bài theo lịch (mỗi phút xem 1 lần) và dừng sớm nếu bị tạm dừng"""
        self._progress(phase=phase, step=step, post_text="", post_url="",
                       next_at=(datetime.now() + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S"))
        end, next_post_check = self.clock() + seconds, self.clock() + 60
        pausing = self.db.is_paused()
        while self.clock() < end:
            if self.db.is_paused() != pausing:
                return  # vừa bấm Tạm dừng / Tiếp tục trên web: xử lý ngay, không chờ hết giờ
            if self.clock() >= next_post_check:
                self.between()
                next_post_check = self.clock() + 60
            self.sleep(min(5, max(0.0, end - self.clock())))

    def comment_next(self):
        """Bình luận 1 bài trong hàng chờ. Trả về None (hàng chờ trống), "no_products", "skip", "blocked"
        hoặc kết quả bình luận ("Hoàn tất" / "Một phần" / "Thất bại")"""
        item = self.db.next_queued(self.config.MAX_POST_AGE_MINUTES)
        if not item:
            return None
        group = {"group_url": item["group_url"], "group_name": item["group_name"] or ""}
        if self.db.has_post(item["post_url"]):
            self.db.set_queue_status(item["id"], Q_SKIPPED, "đã bình luận trước đó")
            return "skip"
        if self.db.is_stopped(item["group_url"]):
            self.db.set_queue_status(item["id"], Q_SKIPPED, "nhóm từ chối cả bản không SĐT/địa chỉ — ngừng nhóm")
            return "skip"
        pool = self.pick_comments(group)
        if not pool:
            return "no_products"  # để bài lại trong hàng chờ, bật sản phẩm trên web là bình luận tiếp
        posted = datetime.strptime(item["posted_at"], "%Y-%m-%d %H:%M:%S")
        age = max(0, int((datetime.now() - posted).total_seconds() // 60))
        text = item["post_text"] or ""
        self.logger.info(f"★ Bình luận ngay: {group['group_name'] or group['group_url']} — bài đăng {age} phút trước, "
                         f"quét thấy {item['found_at'][11:16]}: {' '.join(text.split())[:70]!r}")
        self.db.set_queue_status(item["id"], Q_RUNNING)
        self._progress(phase="Bình luận", step="Mở bài viết", group_name=group["group_name"],
                       group_url=group["group_url"], post_text=text[:400], post_url=item["post_url"],
                       post_topic=item["topic"] or "", post_age=age, post_i=1, post_total=1,
                       comment_i=0, comment_total=len(pool), product="", next_at="")
        result = self.watcher.comment_post(self.commenter, pool, group,
                                           {"url": item["post_url"], "text": text, "age": age})
        if result == "Thất bại" and item["result"] != RETRY_MARK and self.db.forget_failed_post(item["post_url"]):
            # chưa gửi được bình luận nào (thường do mạng chập chờn): trả lại hàng chờ, thử lại 1 lần
            self.db.set_queue_status(item["id"], Q_WAITING, RETRY_MARK)
            self.logger.warning(f"  ↻ Chưa gửi được bình luận nào — bài trả lại hàng chờ, thử lại 1 lần: {item['post_url']}")
            return result
        self.db.set_queue_status(item["id"], Q_DONE if result in COMMENTED else Q_SKIPPED, str(result))
        self.logger.info(f"  {'✓' if result in COMMENTED else '·'} {result}: {item['post_url']}")
        self._progress(last_result=f"{result}: {' '.join(text.split())[:80]}", last_url=item["post_url"],
                       commented=self.db.commented_posts_today())
        return result

    def housekeep(self, force=False):
        """Việc lúc rảnh (QUEUE_HOUSEKEEP_MINUTES phút 1 lần): tham gia nhóm chưa vào, kiểm tra lại bài đã bình luận"""
        if (not force and self.housekept_at is not None
                and self.clock() - self.housekept_at < self.config.QUEUE_HOUSEKEEP_MINUTES * 60):
            return
        self.housekept_at = self.clock()
        if self.config.AUTO_JOIN:
            todo = self.db.groups_with_status(gc.NOT_JOINED, retry_days=self.config.JOIN_RETRY_DAYS)
            for g in todo[:self.config.QUEUE_HOUSEKEEP_JOINS]:
                if self.db.is_paused():
                    return
                self._progress(phase="Tham gia nhóm", step=g["group_name"] or g["group_url"], post_text="")
                try:
                    self.watcher._join(g)
                except Exception as e:
                    self.logger.error(f"  ✗ Lỗi tham gia nhóm: {str(e).splitlines()[0][:150]}")
        self._progress(phase="Kiểm tra lại bài đã bình luận", step="Mở lại bài đã bình luận ~1 giờ trước", post_text="")
        self.watcher.verify(self.commenter, limit=None if force else self.config.QUEUE_HOUSEKEEP_VERIFY)
        self.housekeeping_extra()
        if not self.db.export_excel(self.config.COMMENT_LOG_FILE):
            self.logger.warning("Không ghi được nhat_ky_binh_luan.xlsx (đang mở trong Excel) — sẽ ghi lại lượt sau")

    def step(self, daily_full, blocked_until, minutes_to_tomorrow):
        """1 bước của vòng chạy. Trả về kết quả comment_next hoặc lý do đang chờ"""
        if self.db.is_paused():
            self.idle(60, "Tạm dừng từ web")
            return "paused"
        until = blocked_until()
        if until and datetime.now() < until:
            self.idle(min(30 * 60, (until - datetime.now()).total_seconds()),
                      f"Bị Facebook chặn — chờ tới {until:%H:%M %d/%m}")
            return "blocked"
        if daily_full():
            cap = self.config.MAX_COMMENTED_POSTS_PER_DAY
            self.logger.info(f"Đủ {cap} bài hôm nay — tham gia nhóm & kiểm tra lại bài đã bình luận rồi nghỉ tới 0 giờ")
            self.housekeep(force=True)
            self.idle(minutes_to_tomorrow() * 60, f"Đủ {cap} bài hôm nay — nghỉ tới ngày mai")
            return "daily_full"
        result = self.comment_next()
        if result in COMMENTED or result == "Thất bại":
            self.between()
            wait = random.uniform(self.config.MIN_DELAY, self.config.MAX_DELAY)
            self.idle(wait, "Nghỉ giữa 2 bài", "bài mới nhất trong hàng chờ sẽ được bình luận tiếp")
        elif result is None or result == "no_products":
            if result == "no_products":
                self.logger.warning("Chưa bật sản phẩm nào trên web (tab Sản phẩm) — bài vẫn nằm trong hàng chờ")
            self.housekeep()
            self.idle(self.config.QUEUE_IDLE_SECONDS, "Chờ bài mới từ cửa sổ quét")
        return result
