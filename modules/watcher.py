"""
Theo dõi bài viết mới trong các nhóm (sắp xếp "Bài viết mới"). Mỗi vòng: lần lượt từng nhóm theo thứ tự ưu tiên,
quét hết bài đăng trong vòng MAX_POST_AGE_MINUTES (bài màn hình trước, rồi máy tính) và bình luận hết, mỗi bài 3 bình
luận độc lập (mỗi sản phẩm 1 bình luận + 1 ảnh). Cuối vòng tự tham gia nhóm chưa tham gia. Mọi kết quả lưu vào SQLite.
"""
import os
import re
import time
import random
import dataclasses
from datetime import datetime, timedelta

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import StaleElementReferenceException

from modules.db import SENT, PENDING, BLOCKED, REJECTED, REJECTED_DELETED, FULL, SAFE, COMMENT, COMMENT_DRY, SKIP
from modules.commenter import _key, _norm
from modules import group_checker as gc
from modules.group_finder import normalize_group_url as gc_url, is_hanoi_group
from modules.topic import topic, MONITOR, PC, LAPTOP  # noqa: F401  (topic: dùng lại từ module khác)
from modules import fb_selectors as sel
from modules import filters as flt
from modules.engagement import parse_engagement
from modules.intent import text_key, plain_text as _plain
from modules.ai_intent import AiIntent
from modules.group_stats import group_info, is_fresh
from modules.group_yield import scan_due, is_low_yield, EMPTY


MIN_DEDUP_TEXT = 40   # bài ngắn hơn ... ký tự (vd "Cần mua màn 24 inch") dễ trùng chữ giữa nhiều người -> chỉ chống trùng theo link


def parse_age_minutes(text):
    """Tuổi bài viết (phút) từ chữ 'Vừa xong' / '5 phút' / '2 giờ' ở đầu bài; None nếu không rõ (coi là bài cũ)"""
    head = text[:200]
    if re.search(r"vừa xong|just now", head, re.IGNORECASE):
        return 0
    m = re.search(r"(\d+)\s*(phút|giờ|min|hr|h\b|m\b)", head, re.IGNORECASE)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    return n * 60 if unit in ("giờ", "hr", "h") else n


def normalize_post_url(href, group_url):
    """Đưa link về dạng https://www.facebook.com/groups/<nhóm>/posts/<id>/"""
    m = re.search(r"/groups/([^/?#]+)/(?:posts|permalink)/(\d+)", href or "")
    if m:
        return f"https://www.facebook.com/groups/{m.group(1)}/posts/{m.group(2)}/"
    m = re.search(r"set=pcb\.(\d+)", href or "")
    if m:
        slug = re.search(r"/groups/([^/?#]+)", group_url).group(1)
        return f"https://www.facebook.com/groups/{slug}/posts/{m.group(1)}/"
    return None


def daily_cap_reached(db, config):
    """Đã bình luận đủ MAX_COMMENTED_POSTS_PER_DAY bài hôm nay chưa (0 = không giới hạn)"""
    cap = config.MAX_COMMENTED_POSTS_PER_DAY
    return bool(cap) and db.commented_posts_today() >= cap


def minutes_to_tomorrow(now=None):
    """Số phút từ bây giờ tới 00:01 ngày mai (lúc bộ đếm bài/ngày về 0)"""
    now = now or datetime.now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0)
    return (tomorrow - now).total_seconds() / 60


class GroupWatcher:
    def __init__(self, driver, config, logger, db, dry_run=False, progress=None):
        self.driver = driver
        self.config = config
        self.logger = logger
        self.db = db
        self.progress_fn = progress or db.set_progress  # cửa sổ quét ghi tiến trình riêng (db.set_scan_progress)
        self.dry_run = dry_run              # True = quét & phân loại, KHÔNG bình luận / tham gia nhóm
        self.hot_groups = []                # nhóm tương tác cao (HOT_GROUPS): quét lại xen giữa vòng
        self.hot_scanned_at = time.time()
        self.force_stats = False            # bạn bấm "Cập nhật số thành viên": đọc lại trang Giới thiệu mọi nhóm 1 lần
        self.stats_refreshed = set()
        self.ai = AiIntent(db, config, logger)  # Gemini chấm lại bài từ khóa chưa chắc (INTENT_AI)

    def _group_check(self, g):
        """Nhóm có đủ chất lượng để quét không (GROUP_FILTERS) — số liệu lấy từ CSDL, cũ thì đọc lại trang Giới thiệu"""
        url = gc_url(g["group_url"])
        force = self.force_stats and url not in self.stats_refreshed
        if force or not is_fresh(self.db.get_group_stats(url), self.config):
            self._progress(step="Đọc số thành viên ở trang Giới thiệu của nhóm")
        stats = group_info(self.driver, self.db, self.config, {**g, "group_url": url}, force=force)
        self.stats_refreshed.add(url)
        return flt.run_filters(flt.GROUP_FILTERS, stats and {**stats, "hanoi": is_hanoi_group(g)}, self.config)

    def _my_uid(self):
        cookie = self.driver.get_cookie("c_user")
        return cookie["value"] if cookie else None

    def _post_url(self, item, group_url):
        """Lấy link bài viết của 1 ô trong bảng tin"""
        anchors = item.find_elements(By.XPATH, sel.XP_LINKS)
        # 1. Link có sẵn /posts/<id> (vd link thời gian của bình luận)
        for a in anchors:
            href = a.get_attribute("href") or ""
            url = normalize_post_url(href, group_url)
            if url and "/photo" not in href:
                return url
        # 2. Link thời gian đăng bị ẩn: href là link nhóm, rê chuột vào mới hiện link bài
        for a in anchors:
            href = a.get_attribute("href") or ""
            if re.search(r"/groups/[^/]+/?(\?|$)", href):
                try:
                    ActionChains(self.driver).move_to_element(a).perform()
                    time.sleep(1)
                except Exception:
                    continue
                url = normalize_post_url(a.get_attribute("href"), group_url)
                if url:
                    return url
        # 3. Ảnh trong bài có dạng set=pcb.<id bài viết>
        for a in anchors:
            url = normalize_post_url(a.get_attribute("href"), group_url)
            if url:
                return url
        return None

    def _author_uid(self, item):
        """ID người đăng = link /user/<id>/ đầu tiên trong ô bài viết"""
        for a in item.find_elements(By.XPATH, sel.XP_LINKS)[:4]:
            m = re.search(r"/user/(\d+)/", a.get_attribute("href") or "")
            if m:
                return m.group(1)
        return None

    def scan_group(self, group, limit=0, max_age=None):
        """Quét bảng tin 1 nhóm (sắp xếp "Bài viết mới") và chọn bài để bình luận.
        Mỗi bài qua chuỗi bộ lọc POST_FILTERS (chủ đề -> ý định MUA/BÁN -> điểm tương tác); mọi quyết định được ghi
        kèm lý do (bảng post_decisions + log chạy). Dừng khi gặp bài cũ hơn max_age phút (mặc định MAX_POST_AGE_MINUTES),
        hết GROUP_SCAN_MAX_SECONDS giây, hết WATCH_SCROLLS lần cuộn, hoặc đủ `limit` bài (0 = không giới hạn).
        Trả về (trạng thái thành viên, [bài sẽ bình luận {url, text, age, topic, score}]): bài màn hình trước, rồi PC,
        mỗi loại mới nhất trước."""
        max_age = max_age or self.config.MAX_POST_AGE_MINUTES
        group_url = group["group_url"].rstrip("/")
        started = time.time()
        self.driver.get(sel.GROUP_FEED_URL.format(group_url=group_url))
        time.sleep(random.uniform(6, 9))
        gc.dismiss_welcome(self.driver)
        self._remember_name(group)
        member = gc.detect_status(self.driver)
        if member in (gc.NOT_JOINED, gc.PENDING, gc.UNAVAILABLE):
            return member, []

        my_uid = self._my_uid()
        posts, seen, old_streak, timed_out = [], set(), 0, False
        self.scan_interactions = []  # tương tác (cảm xúc + bình luận + chia sẻ) mỗi bài thấy được -> ưu tiên nhóm
        for _ in range(self.config.WATCH_SCROLLS + 1):
            for item in self.driver.find_elements(By.XPATH, sel.XP_FEED_ITEMS):
                if time.time() - started > self.config.GROUP_SCAN_MAX_SECONDS:
                    timed_out = True
                    break
                if item.id in seen:
                    continue
                try:
                    full_text = item.text
                    if not full_text.strip():
                        continue  # ô chưa tải xong, lượt cuộn sau xem lại
                    seen.add(item.id)
                    if sel.FEED_SORT_BANNER in full_text.lower():
                        continue
                    self.scan_interactions.append(self._interactions(item, full_text))
                    age = parse_age_minutes(full_text)
                    if age is None or age > max_age:
                        old_streak += 1  # bài cũ (bài ghim ở đầu không tính: cần 3 bài cũ liền nhau mới dừng)
                        continue
                    old_streak = 0
                    post = self._consider(item, full_text, age, group, group_url, my_uid)
                    if post:
                        posts.append(post)
                        if limit and len(posts) >= limit:
                            break
                except StaleElementReferenceException:
                    continue  # phần tử bị Facebook vẽ lại, bỏ qua
                except Exception as e:  # lỗi khác (CSDL, file từ khóa…) không được nuốt im lặng
                    self.logger.warning(f"  ✗ Lỗi khi xét 1 bài: {type(e).__name__}: {str(e).splitlines()[0][:150]}")
                    continue
            if time.time() - started > self.config.GROUP_SCAN_MAX_SECONDS:
                timed_out = True
            if timed_out:
                self.logger.info(f"  ⏱ Đã quét {self.config.GROUP_SCAN_MAX_SECONDS} giây — dừng cuộn nhóm này "
                                 f"(bài mới nhất đã được xét trước)")
                break
            if old_streak >= 3 or (limit and len(posts) >= limit):
                break
            self.driver.execute_script("window.scrollBy(0, 1500)")
            time.sleep(random.uniform(2, 3))
        order = list(self.config.COMMENT_TOPICS) or [MONITOR, PC, LAPTOP]  # chủ đề đứng trước được bình luận trước
        posts.sort(key=lambda p: (order.index(p["topic"]) if p["topic"] in order else len(order), p["age"]))
        return member, posts

    @staticmethod
    def _interactions(item, full_text):
        """Tổng số cảm xúc + bình luận + chia sẻ ghi dưới 1 bài (đọc chữ, không gọi JS — chỉ để ước mức sôi động nhóm)"""
        msg = item.find_elements(By.XPATH, sel.XP_MESSAGE)
        e = parse_engagement(full_text, msg[0].text if msg else "", [])
        return e.reactions + e.comments + e.shares

    def avg_interactions(self):
        """Tương tác trung bình mỗi bài của lần quét vừa rồi (None nếu không thấy bài nào)"""
        values = getattr(self, "scan_interactions", [])
        return round(sum(values) / len(values), 1) if values else None

    def _read_engagement(self, item, full_text, message):
        """Số cảm xúc / bình luận / chia sẻ của 1 ô bài viết (đọc mọi aria-label trong 1 lần gọi JS)"""
        try:
            labels = self.driver.execute_script(sel.JS_ITEM_LABELS, item) or []
        except Exception:
            # không đọc được nhãn: số cảm xúc có thể bị đếm thành bình luận -> đánh dấu "không chắc"
            return dataclasses.replace(parse_engagement(full_text, message, []), known=False)
        return parse_engagement(full_text, message, labels)

    def _consider(self, item, full_text, age, group, group_url, my_uid):
        """Chạy bộ lọc cho 1 ô bài viết; đạt thì lấy link bài. Trả về bài để bình luận, hoặc None"""
        msg = item.find_elements(By.XPATH, sel.XP_MESSAGE)
        text = msg[0].text if msg else full_text[:400]
        key = text_key(text)
        if len(_plain(text)) >= MIN_DEDUP_TEXT and self.db.commented_text(gc_url(group_url), key):
            return None  # đã bình luận bài này trước đó (bài ngắn: chỉ nhận theo link, tránh nhầm bài khác cùng chữ)
        cand = flt.PostCandidate(text, age, self.config, lambda: self._read_engagement(item, full_text, text),
                                 ai=self.ai, hanoi_group=is_hanoi_group(group))
        verdict = flt.run_filters(flt.POST_FILTERS, cand, self.config)
        if not verdict.ok:
            self._decide(group, key, cand, verdict)
            return None
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
        time.sleep(0.5)
        url = self._post_url(item, group_url)
        if not url:
            self._decide(group, key, cand, flt.Verdict(False, "không lấy được link bài viết"))
            return None
        if self.db.has_post(url):
            return None  # đã bình luận trước đó
        if my_uid and self._author_uid(item) == my_uid:
            self._decide(group, key, cand, flt.Verdict(False, "bài của chính mình"), url)
            return None
        self._decide(group, key, cand, verdict, url)
        # điểm tương tác chỉ có khi bộ lọc tương tác đã đọc (POST_MIN_ENGAGEMENT > 0) — không đọc thêm cho bài MUA
        return {"url": url, "text": text, "age": age, "topic": cand.topic, "score": cand.computed("score")}

    def _decide(self, group, key, cand, verdict, url=None):
        """Ghi quyết định bình luận / bỏ qua (kèm lý do) vào CSDL; bài mới hoặc quyết định đổi thì ghi cả log chạy"""
        intent, engagement = cand.computed("intent"), cand.computed("engagement")
        decision = (COMMENT_DRY if self.dry_run else COMMENT) if verdict.ok else SKIP
        changed = self.db.log_decision(
            gc_url(group["group_url"]), group.get("group_name", ""), key, cand.text[:1000], decision, verdict.reason,
            post_url=url, post_age_min=cand.age, topic=cand.computed("topic"),
            intent=intent.label if intent else None, intent_detail=intent.reason if intent else None,
            engagement=engagement, score=cand.computed("score"))
        if changed:
            self.logger.info(f"    {'✔' if verdict.ok else '·'} {decision}: {verdict.reason[:170]} "
                             f"| {' '.join(cand.text.split())[:60]!r}")

    def _remember_name(self, group):
        """Lưu tên nhóm từ tiêu đề trang ('(3) Tên nhóm | Facebook') để web hiện tên cho link chưa có tên"""
        try:
            title = re.sub(r"^\(\d+\+?\)\s*", "", self.driver.title or "")
            title = re.sub(r"\s*\|\s*Facebook\s*$", "", title).strip()
            if title and title.lower() != "facebook":
                self.db.set_group_name(gc_url(group["group_url"]), title)
                if not group.get("group_name") or group["group_name"] == group["group_url"].rstrip("/").split("/")[-1]:
                    group["group_name"] = title
        except Exception:
            pass

    def _progress(self, **fields):
        try:
            self.progress_fn(**fields)
        except Exception:
            pass  # tiến trình chỉ để hiển thị, lỗi ghi không ảnh hưởng việc chạy

    def _join(self, group):
        """Nhóm chưa tham gia: tự bấm Tham gia (tối đa JOIN_PER_DAY nhóm/ngày). Trả về True nếu đã thành thành viên"""
        url, name = group["group_url"], group.get("group_name", "")
        if not self.config.AUTO_JOIN:
            self.logger.info("  ↷ Chưa tham gia nhóm — bỏ qua (AUTO_JOIN = False)")
            return False
        last = self.db.get_join(url)
        if last and last["status"] != gc.JOINED and last["clicked_at"]:
            clicked = datetime.strptime(last["clicked_at"], "%Y-%m-%d %H:%M:%S")
            if datetime.now() - clicked < timedelta(days=self.config.JOIN_RETRY_DAYS):
                self.logger.info(f"  ↷ Chưa tham gia nhóm — {last['status']} ({last['note']}), bỏ qua")
                return False
        if self.db.joins_today() >= self.config.JOIN_PER_DAY:
            self.logger.info(f"  ↷ Chưa tham gia nhóm — hôm nay đã tự tham gia đủ {self.config.JOIN_PER_DAY} nhóm")
            return False

        self.driver.get(url)
        time.sleep(random.uniform(5, 8))
        gc.dismiss_welcome(self.driver)
        current = gc.detect_status(self.driver)
        if current != gc.NOT_JOINED:
            return current == gc.JOINED
        status, note = gc.auto_join(self.driver, self.logger, self.config.JOIN_ANSWER)
        self.db.set_join(url, name, status, note, clicked=True)
        self.logger.info(f"  ➕ Tự tham gia nhóm: {status}" + (f" — {note}" if note else ""))
        time.sleep(random.uniform(self.config.JOIN_MIN_DELAY, self.config.JOIN_MAX_DELAY))
        return status == gc.JOINED

    def _recently_unavailable(self, group):
        """Nhóm vừa báo "không xem được nội dung này" (thường do bị quản trị viên chặn) trong
        GROUP_UNAVAILABLE_RETRY_HOURS giờ gần đây -> chưa thử lại (không tốn 2 phút cuộn trang trống)"""
        row = self.db.get_join(group["group_url"])
        if not row or row["status"] != gc.UNAVAILABLE or not row["checked_at"]:
            return False
        checked = datetime.strptime(row["checked_at"], "%Y-%m-%d %H:%M:%S")
        return datetime.now() - checked < timedelta(hours=self.config.GROUP_UNAVAILABLE_RETRY_HOURS)

    def _note_unavailable(self, g):
        name = g.get("group_name", "")
        if not self.dry_run:
            self.db.set_join(g["group_url"], name, gc.UNAVAILABLE,
                             "Facebook báo 'Bạn hiện không xem được nội dung này' — có thể đã bị chặn khỏi nhóm")
        self.logger.warning(f"  ⚠ Tài khoản KHÔNG XEM ĐƯỢC nhóm {name or g['group_url']} (Facebook báo 'Bạn hiện "
                            f"không xem được nội dung này' — thường do bị quản trị viên chặn khỏi nhóm). Bỏ qua "
                            f"nhóm này {self.config.GROUP_UNAVAILABLE_RETRY_HOURS} giờ rồi thử lại")

    def check_and_scan(self, g, max_age):
        """Cửa sổ QUÉT: kiểm tra nhóm (không xem được / số thành viên) rồi quét bài đăng trong max_age phút.
        Ghi trạng thái tham gia (nhóm chưa tham gia: cửa sổ bình luận sẽ tự tham gia) + lịch sử quét.
        Trả về (kết quả, bài): kết quả = "ok" nếu đã quét, ngược lại là lý do bỏ qua nhóm"""
        name = g.get("group_name", "")
        if self._recently_unavailable(g):
            return "tài khoản không xem được nhóm (chờ thử lại)", []
        verdict = self._group_check(g)
        if not verdict.ok:
            return verdict.reason, []
        member, posts = self.scan_group(g, 0, max_age)
        if member == gc.NOT_JOINED:
            self.db.set_join(g["group_url"], name, gc.NOT_JOINED, "phát hiện khi quét — cửa sổ bình luận sẽ tự tham gia")
            return "chưa tham gia nhóm — cửa sổ bình luận sẽ tự tham gia", []
        if member == gc.PENDING:
            self.db.set_join(g["group_url"], name, gc.PENDING, "đã gửi yêu cầu, chờ quản trị viên duyệt")
            return "đang chờ quản trị viên duyệt tham gia", []
        if member == gc.UNAVAILABLE:
            self._note_unavailable(g)
            return "tài khoản không xem được nhóm", []
        if member == gc.JOINED:
            self.db.set_join(g["group_url"], name, gc.JOINED)
        self.db.add_group_scan(gc_url(g["group_url"]), len(posts), self.avg_interactions())
        return "ok", posts

    def _blocked_until(self):
        value = self.db.get_setting("blocked_until")
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S") if value else None

    def _send_one(self, commenter, post_id, idx, c, safe, note=""):
        """Gửi 1 bình luận (bản đầy đủ hoặc an toàn). Bị từ chối thì xóa ngay. Lưu & trả về trạng thái"""
        variant = SAFE if safe else FULL
        text = c["safe_text"] if safe else c["text"]
        status, detail = commenter.send_comment({"text": text, "image": c["image"]})
        if status == REJECTED:
            if commenter.last_article is not None and commenter.delete_comment(commenter.last_article):
                status, detail = REJECTED_DELETED, "nhóm/Facebook từ chối — đã tự xóa bình luận"
            else:
                detail = "nhóm/Facebook từ chối — KHÔNG xóa được, cần xóa tay"
        detail = "; ".join(x for x in (note, detail) if x)
        self.db.add_comment(post_id, idx, text, os.path.basename(c["image"] or ""), status, detail, variant,
                            c.get("variant_id"))
        self.logger.info(f"  [{idx}] {status} ({variant})" + (f" — {detail}" if detail else ""))
        return status

    def comment_post(self, commenter, comments, group, p):
        """Gửi lần lượt 3 bình luận vào 1 bài, lưu kết quả. Trả về trạng thái bài.
        - Bản đầy đủ bị từ chối -> xóa ngay, gửi lại bản không SĐT/địa chỉ; nhóm này từ nay dùng bản không SĐT/địa chỉ.
        - Bản không SĐT/địa chỉ cũng bị từ chối -> xóa, ngừng bình luận bài này và nhóm này.
        - Chờ duyệt / không hiển thị -> các bình luận sau và nhóm này dùng bản không SĐT/địa chỉ.
        - Bị chặn -> dừng, mọi nhóm chuyển sang bản không SĐT/địa chỉ, nghỉ BLOCK_COOLDOWN_HOURS giờ."""
        group_url, group_name = group["group_url"], group.get("group_name", "")
        post_id = self.db.add_post(p["url"], group_name, group_url, p["text"][:500], p["age"])
        results = []
        try:
            commenter.open_post(p["url"])
            if commenter.already_commented():
                self.db.update_post(post_id, status="Bỏ qua: đã có bình luận")
                return "skip"

            rejected_here = False  # bài này đã bị từ chối 1 lần -> phần còn lại dùng bản an toàn
            for i, c in enumerate(comments, 1):
                if i > 1:
                    self._progress(step=f"Chờ {self.config.COMMENT_GAP_MIN}–{self.config.COMMENT_GAP_MAX} giây trước bình luận {i}")
                    time.sleep(random.uniform(self.config.COMMENT_GAP_MIN, self.config.COMMENT_GAP_MAX))
                self._progress(comment_i=i, comment_total=len(comments), product=c.get("name", ""),
                               step=f"Đang gửi bình luận {i}/{len(comments)}" + (f": {c['name']}" if c.get("name") else ""))
                safe = rejected_here or self.db.use_safe(group_url)
                status = self._send_one(commenter, post_id, i, c, safe)

                if status in (REJECTED, REJECTED_DELETED) and not safe:
                    rejected_here = True
                    if self.db.mark_safe(group_url, group_name, f"Bình luận {i} có SĐT/địa chỉ bị từ chối"):
                        self.logger.warning("  ⇢ Nhóm từ chối bình luận có SĐT/địa chỉ — từ nay dùng bản không SĐT/địa chỉ")
                    time.sleep(random.uniform(self.config.COMMENT_GAP_MIN, self.config.COMMENT_GAP_MAX))
                    status = self._send_one(commenter, post_id, i, c, True,
                                            note="gửi lại bản không SĐT/địa chỉ sau khi xóa bản bị từ chối")
                    safe = True

                if status in (REJECTED, REJECTED_DELETED) and safe:
                    self.db.mark_stop(group_url, group_name, f"Bản không SĐT/địa chỉ cũng bị từ chối (bình luận {i})")
                    self.logger.warning("  ⛔ Nhóm từ chối cả bản không SĐT/địa chỉ — ngừng bình luận nhóm này")
                    results.append(status)
                    break
                if status == PENDING and not safe:
                    rejected_here = True
                    self.db.mark_safe(group_url, group_name, f"Bình luận {i} chờ duyệt / không hiển thị")
                results.append(status)
                if status == BLOCKED:
                    self.db.mark_safe_all("Facebook báo bị chặn bình luận")
                    break  # bị chặn thì dừng ngay, không gửi tiếp
        except Exception as e:
            self.logger.error(f"  ✗ Lỗi khi bình luận: {e}")

        shot = commenter.screenshot(os.path.join(self.config.SCREENSHOT_DIR, f"{post_id}.png"))
        ok = sum(s in (SENT, PENDING) for s in results)
        status = "Hoàn tất" if ok == len(comments) else ("Một phần" if ok else "Thất bại")
        self.db.update_post(post_id, status=status, screenshot=shot)

        if BLOCKED in results:
            until = datetime.now() + timedelta(hours=self.config.BLOCK_COOLDOWN_HOURS)
            self.db.set_setting("blocked_until", until.strftime("%Y-%m-%d %H:%M:%S"))
            self.logger.error(f"  ⛔ Facebook chặn bình luận — tạm dừng tự bình luận tới {until:%H:%M %d/%m}, "
                              f"mọi nhóm chuyển sang bản không SĐT/địa chỉ")
            return "blocked"
        return status

    def review(self, commenter, post):
        """Mở lại 1 bài: xóa bình luận của mình bị từ chối muộn, cập nhật nhật ký. Trả về (đã xóa, còn lại)"""
        deleted, remaining = commenter.review_post(post["post_url"])
        if deleted is None:  # bài viết đã bị xóa/ẩn — không phải bình luận bị từ chối
            return None, 0
        rows = self.db.comments_of(post["id"])
        for text in deleted:
            for r in rows:
                if r["status"] in (SENT, PENDING) and _key(r["text"]) and _key(r["text"]) in _norm(text):
                    self.db.update_comment(r["id"], status=REJECTED_DELETED,
                                           detail="bị từ chối sau khi đăng — đã tự xóa khi kiểm tra lại")
                    if r["variant"] == SAFE:
                        self.db.mark_stop(post["group_url"], post["group_name"], "Bản không SĐT/địa chỉ bị từ chối")
                    break
        if deleted and self.db.mark_safe(post["group_url"], post["group_name"], "Bình luận bị từ chối (phát hiện khi kiểm tra lại)"):
            self.logger.warning(f"  ⇢ {post['group_name']}: từ nay dùng bản không SĐT/địa chỉ")
        return deleted, remaining

    def verify(self, commenter, limit=None):
        """Mở lại các bài đã bình luận ~1 giờ trước: xóa bình luận bị từ chối muộn, đếm bình luận còn hiển thị.
        limit: tối đa ... bài (mặc định VERIFY_PER_RUN)"""
        for p in self.db.posts_to_verify(self.config.VERIFY_AFTER_MINUTES, limit or self.config.VERIFY_PER_RUN):
            try:
                deleted, n = self.review(commenter, p)
                if deleted is None:
                    self.db.update_post(p["id"], verified_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        verify_result="Bài viết đã bị xóa/ẩn (không phải do bình luận bị từ chối)")
                    self.logger.info(f"  ↻ Kiểm tra lại {p['post_url']}: bài viết đã bị xóa/ẩn")
                    continue
                expected = len([r for r in self.db.comments_of(p["id"]) if r["status"] in (SENT, PENDING)])
                if n >= expected:
                    result = f"Còn đủ {n}/{expected}"
                elif n == 0:
                    result = f"Không thấy 0/{expected} — có thể đã bị xóa"
                else:
                    result = f"Chỉ còn {n}/{expected}"
                if deleted:
                    result += f" · đã xóa {len(deleted)} bình luận bị từ chối"
                self.db.update_post(p["id"], verified_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    verify_result=result)
                self.logger.info(f"  ↻ Kiểm tra lại {p['post_url']}: {result}")
                if n < expected and self.db.mark_safe(p["group_url"], p["group_name"],
                                                      f"Bình luận bị xóa khi kiểm tra lại ({result})"):
                    self.logger.warning(f"  ⇢ {p['group_name']}: bình luận bị xóa — từ nay dùng bản không SĐT/địa chỉ")
            except Exception as e:
                self.logger.error(f"  ✗ Lỗi kiểm tra lại: {e}")

    def cleanup(self, commenter, days=3):
        """Dọn bình luận bị từ chối trên mọi bài đã bình luận trong ... ngày gần đây"""
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        total = 0
        for p in self.db.query("SELECT * FROM posts WHERE found_at >= ? AND status NOT LIKE 'Bỏ qua%' "
                               "ORDER BY found_at", (since,)):
            try:
                deleted, n = self.review(commenter, p)
                if deleted is None:
                    self.logger.info(f"  {p['post_url']}: bài viết đã bị xóa/ẩn")
                    continue
                total += len(deleted)
                self.logger.info(f"  {p['post_url']}: đã xóa {len(deleted)} bình luận bị từ chối, còn {n} bình luận")
            except Exception as e:
                self.logger.error(f"  ✗ {p['post_url']}: {e}")
        self.logger.info(f"Dọn xong: đã xóa {total} bình luận bị từ chối")
        self.db.export_excel(self.config.COMMENT_LOG_FILE)

    def _daily_full(self):
        return daily_cap_reached(self.db, self.config)

    def _scan_and_comment(self, g, gi, total, commenter, comments, between, stats, rescan_age=None):
        """Quét 1 nhóm rồi bình luận hết bài mới của nhóm đó (bài màn hình trước, rồi máy tính).
        rescan_age: quét lại nhóm tương tác cao — chỉ xét bài đăng trong ... phút gần đây.
        stats: {'scanned', 'new', 'commented', 'not_joined'} của vòng, cập nhật tại chỗ.
        Trả về None để chạy tiếp, hoặc (giá trị trả về của run, ghi chú) để dừng vòng."""
        pct = lambda done=0.0: round(100 * ((gi - 1) + done) / max(total, 1), 1)
        name = g.get("group_name", "")
        if rescan_age:
            self.logger.info(f"⟳ Quét lại nhóm tương tác cao (bài ≤ {rescan_age} phút): {name or g['group_url']}")
        else:
            self.logger.info(f"→ [{gi}/{total}] Quét: {name or g['group_url']}"
                             + (" ★ tương tác cao" if g.get("hot") else ""))
        self._progress(phase="Quét lại nhóm tương tác cao" if rescan_age else "Quét nhóm",
                       step="Đang cuộn bảng tin tìm bài mới", group_i=gi, group_name=name,
                       group_url=g["group_url"], post_i=0, post_total=0, post_text="", post_url="",
                       comment_i=0, comment_total=0, product="", percent=pct())

        if self._recently_unavailable(g):
            if not rescan_age:
                self.logger.info(f"  ↷ Bỏ qua: tài khoản không xem được nhóm này (kiểm tra lại sau "
                                 f"{self.config.GROUP_UNAVAILABLE_RETRY_HOURS} giờ)")
            return None

        # 0) Nhóm đủ chất lượng? (số thành viên, số bài/ngày — đọc ở trang Giới thiệu, lưu CSDL 24 giờ)
        verdict = self._group_check(g)
        if not rescan_age:
            stats["checked"] = stats.get("checked", 0) + 1
            if verdict.reason.startswith("không lấy được số thành viên"):
                stats["no_members"] = stats.get("no_members", 0) + 1
        if not verdict.ok:
            if not rescan_age:
                self.logger.info(f"  ↷ Bỏ qua nhóm: {verdict.reason}")
            return None
        if not rescan_age:
            self.logger.info(f"  Nhóm đạt: {verdict.reason}")

        # 1) Quét hết bài mới trong nhóm
        try:
            member, posts = self.scan_group(g, self.config.MAX_POSTS_PER_GROUP, rescan_age)
        except Exception as e:
            self.logger.error(f"  ✗ Lỗi quét nhóm: {str(e).splitlines()[0][:150]}")
            return None
        if member == gc.NOT_JOINED:
            if g.get("hot") and not self.dry_run:
                self.logger.info("  ↷ Chưa tham gia nhóm tương tác cao — tham gia ngay")
                self._join(g)
            elif g not in stats["not_joined"]:
                stats["not_joined"].append(g)
                self.logger.info("  ↷ Chưa tham gia nhóm — sẽ tự tham gia cuối vòng")
            return None
        if member == gc.PENDING:
            if not self.dry_run:
                self.db.set_join(g["group_url"], name, gc.PENDING, "đã gửi yêu cầu, chờ quản trị viên duyệt")
            self.logger.info("  ↷ Đang chờ quản trị viên duyệt tham gia — bỏ qua")
            return None
        if member == gc.UNAVAILABLE:
            self._note_unavailable(g)
            return None
        if member == gc.JOINED and not self.dry_run:
            self.db.set_join(g["group_url"], name, gc.JOINED)
            if not rescan_age:  # lịch sử quét: xoay vòng nhóm (quét lại sau GROUP_RESCAN_MINUTES phút)
                self.db.add_group_scan(gc_url(g["group_url"]), len(posts), self.avg_interactions())
        stats["scanned"] += 1
        self.logger.info(f"  {len(posts)} bài đạt điều kiện để bình luận"
                         + (f" (chủ đề: {', '.join(self.config.COMMENT_TOPICS)})" if self.config.COMMENT_TOPICS else ""))
        stats["new"] += len(posts)
        self._progress(group_name=g.get("group_name", name), post_total=len(posts), posts_found=stats["new"],
                       step=f"Tìm thấy {len(posts)} bài mới", percent=pct(0.1 if posts else 1))

        # 2) Bình luận hết các bài của nhóm này
        for n, p in enumerate(posts, 1):
            if self.db.is_paused():
                return stats["commented"], "Dừng giữa chừng: tạm dừng từ web"
            if self._daily_full() or self.db.is_stopped(g["group_url"]):
                break  # đủ giới hạn ngày / nhóm vừa bị đánh dấu ngừng
            if self.db.has_post(p["url"]):
                continue  # đã bình luận trong lúc quét lại nhóm tương tác cao
            score = f" · điểm tương tác {p['score']:g}" if p.get("score") is not None else ""
            if self.dry_run:
                self.logger.info(f"  ★ (chạy thử — KHÔNG bình luận) {p['topic']}{score} — bài {p['age']} phút trước "
                                 f"— {p['url']}")
                continue
            # comments có thể là hàm: đọc lại sản phẩm đang bật trên web trước mỗi bài
            pool = comments(g) if callable(comments) else comments  # chọn mẫu bình luận ngẫu nhiên cho bài này
            if not pool:
                note = "Dừng: không còn sản phẩm nào được bật trên web"
                self.logger.warning(note)
                return stats["commented"], note
            self.logger.info(f"  ★ [{n}/{len(posts)}] {p['topic'] or ''}{score} "
                             f"— bài {p['age']} phút trước: {p['text'][:70]!r}")
            self._progress(phase="Bình luận", step="Mở bài viết", group_i=gi, group_name=g.get("group_name", name),
                           group_url=g["group_url"], post_i=n, post_total=len(posts),
                           post_text=p["text"][:400], post_url=p["url"], post_topic=p.get("topic") or "",
                           post_age=p["age"], comment_i=0, comment_total=len(pool), product="",
                           percent=pct(0.1 + 0.9 * (n - 1) / len(posts)))
            result = self.comment_post(commenter, pool, g, p)
            if result == "blocked":
                return "blocked", "Bị Facebook chặn"
            if result in ("Hoàn tất", "Một phần"):
                stats["commented"] += 1
                self.logger.info(f"  ✓ {result}: {p['url']}")
            self._progress(commented=stats["commented"], last_result=f"{result}: {p['text'][:80]}",
                           last_url=p["url"], percent=pct(0.1 + 0.9 * n / len(posts)))
            if between:
                between()
            if result in ("Hoàn tất", "Một phần") and n < len(posts):
                wait = random.uniform(self.config.MIN_DELAY, self.config.MAX_DELAY)
                self._progress(step=f"Nghỉ {wait:.0f} giây trước bài tiếp theo",
                               next_at=(datetime.now() + timedelta(seconds=wait)).strftime("%Y-%m-%d %H:%M:%S"))
                time.sleep(wait)
            # nhóm này nhiều bài: đến hạn thì quét lại nhóm tương tác cao xen giữa, xong bình luận tiếp bài còn lại
            stop = self._rescan_hot(gi, total, commenter, comments, between, stats)
            if stop:
                return stop
        if between:
            between()
        return None

    def _rescan_hot(self, gi, total, commenter, comments, between, stats):
        """Đã quá HOT_RESCAN_MINUTES phút từ lần quét trước -> quét lại các nhóm tương tác cao (HOT_GROUPS).
        Chỉ xét bài đăng sau lần quét trước (+ 30 phút dự phòng) nên cuộn ít. Trả về như _scan_and_comment."""
        elapsed = time.time() - self.hot_scanned_at
        if not self.hot_groups or elapsed < self.config.HOT_RESCAN_MINUTES * 60:
            return None
        self.hot_scanned_at = time.time()  # đặt trước: bình luận trong lúc quét lại không gọi lồng nhau
        age = min(int(elapsed / 60) + 30, self.config.MAX_POST_AGE_MINUTES)
        for g in self.hot_groups:
            if self.db.is_paused():
                return stats["commented"], "Dừng giữa chừng: tạm dừng từ web"
            if self._daily_full() or self.db.is_stopped(g["group_url"]):
                continue
            stop = self._scan_and_comment(g, gi, total, commenter, comments, between, stats, rescan_age=age)
            if stop:
                return stop
        return None

    def run(self, groups, commenter, comments, between=None):
        """1 vòng: lần lượt từng nhóm (đã xếp theo ưu tiên) quét hết bài mới trong MAX_POST_AGE_MINUTES rồi bình luận
        hết các bài đó (bài màn hình trước, rồi máy tính), xong mới sang nhóm sau. Nhóm tương tác cao (hot, đứng đầu
        danh sách) được quét lại mỗi HOT_RESCAN_MINUTES phút xen giữa các nhóm/bài khác. Cuối vòng tự tham gia các nhóm
        chưa tham gia (điền JOIN_ANSWER + tick) — vòng sau sẽ bình luận các nhóm đó.
        between(): gọi sau mỗi nhóm/bài (đăng bài theo lịch nếu đến giờ).
        Trả về số bài đã bình luận, hoặc "blocked" nếu đang bị Facebook chặn."""
        run_id = self.db.start_run()
        stats = {"scanned": 0, "new": 0, "commented": 0, "not_joined": [], "checked": 0, "no_members": 0}
        note = ""
        try:
            until = self._blocked_until()
            if until and datetime.now() < until and not self.dry_run:
                note = f"Đang tạm dừng do bị chặn tới {until:%H:%M %d/%m}"
                self.logger.warning(note)
                return "blocked"
            if not self.dry_run and self.db.fix_interrupted():
                self.logger.info("↻ Bài bị bỏ dở lần trước (script bị tắt giữa chừng) sẽ được bình luận lại")
            if self.db.get_setting("group_stats_refresh") == "1":  # bấm "Cập nhật số thành viên" trên web
                self.db.set_setting("group_stats_refresh", "0")
                self.force_stats = True
                self.logger.info("↻ Đọc lại số thành viên của mọi nhóm trong vòng này (yêu cầu từ web)")
            if self.dry_run:
                note = "Chạy thử — không bình luận"
                self.logger.info("=== CHẠY THỬ: chỉ quét & phân loại, KHÔNG bình luận, KHÔNG tham gia nhóm ===")

            total = len(groups)
            yields = self.db.group_yields(self.config.YIELD_DAYS)
            due = [g for g in groups if scan_due({**g, "group_url": gc_url(g["group_url"])}, yields, self.config)]
            low = sum(is_low_yield(yields.get(gc_url(g["group_url"]), EMPTY), self.config) for g in groups)
            if len(due) < total:
                self.logger.info(f"Xoay vòng nhóm: {len(due)}/{total} nhóm tới lượt quét — bỏ qua nhóm vừa quét "
                                 f"< {self.config.GROUP_RESCAN_MINUTES} phút; {low} nhóm ít khách (quét "
                                 f"{self.config.LOW_YIELD_MIN_SCANS}+ lần, 0 bài cần mua) chỉ quét "
                                 f"{self.config.LOW_YIELD_RESCAN_HOURS} giờ/lần")
            due_urls = {g["group_url"] for g in due}
            self.hot_groups = [g for g in groups if g.get("hot")]
            self.hot_scanned_at = time.time()  # nhóm tương tác cao đứng đầu danh sách: được quét ngay đầu vòng
            if self.hot_groups:
                self.logger.info(f"Nhóm tương tác cao (quét lại mỗi {self.config.HOT_RESCAN_MINUTES} phút): "
                                 + " | ".join(g.get("group_name", "") or g["group_url"] for g in self.hot_groups))
            self._progress(reset=True, phase="Quét & bình luận", round_started=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           group_total=total, commented=0, posts_found=0, percent=0)
            for gi, g in enumerate(groups, 1):
                if self.db.is_paused():
                    note = "Dừng giữa chừng: tạm dừng từ web"
                    return stats["commented"]
                if self._daily_full():
                    note = f"Đủ {self.config.MAX_COMMENTED_POSTS_PER_DAY} bài hôm nay"
                    self.logger.info(note + " — tham gia nhóm & kiểm tra lại bài đã bình luận rồi nghỉ")
                    break  # vẫn chạy bước cuối vòng (tự tham gia nhóm, kiểm tra lại bình luận)
                if self.db.is_stopped(g["group_url"]) or g["group_url"] not in due_urls:
                    continue  # nhóm từ chối cả bản không SĐT/địa chỉ / chưa tới lượt quét lại
                stop = self._rescan_hot(gi, total, commenter, comments, between, stats)
                if not stop:
                    stop = self._scan_and_comment(g, gi, total, commenter, comments, between, stats)
                if stop:
                    result, note = stop
                    return result

            # 3) Cuối vòng: tự tham gia các nhóm chưa tham gia (vòng sau bình luận các nhóm này)
            not_joined = stats["not_joined"]
            if self.dry_run:
                return stats["commented"]
            if not_joined and self.config.AUTO_JOIN:
                self.logger.info(f"=== Tự tham gia {len(not_joined)} nhóm chưa tham gia ===")
                for ji, g in enumerate(not_joined, 1):
                    if self.db.is_paused():
                        break
                    self.logger.info(f"→ Tham gia: {g.get('group_name', '') or g['group_url']}")
                    self._progress(phase="Tham gia nhóm", step=f"Tham gia nhóm {ji}/{len(not_joined)}",
                                   join_i=ji, join_total=len(not_joined), group_name=g.get("group_name", ""),
                                   group_url=g["group_url"], post_text="", post_url="", percent=100)
                    try:
                        self._join(g)
                    except Exception as e:
                        self.logger.error(f"  ✗ Lỗi tham gia nhóm: {str(e).splitlines()[0][:150]}")

            self._progress(phase="Kiểm tra lại bài đã bình luận", step="Mở lại bài đã bình luận ~1 giờ trước",
                           post_text="", post_url="", percent=100)
            self.verify(commenter)
            return stats["commented"]
        finally:
            scanned, new, commented = stats["scanned"], stats["new"], stats["commented"]
            self.db.finish_run(run_id, scanned, new, commented, note)
            if stats["no_members"] and stats["no_members"] * 2 > max(stats["checked"], 1):
                self.logger.warning(f"⚠ {stats['no_members']}/{stats['checked']} nhóm không đọc được số thành viên — "
                                    "có thể Facebook đổi giao diện trang Giới thiệu (sửa modules/fb_selectors.py)")
            if not self.dry_run and not self.db.export_excel(self.config.COMMENT_LOG_FILE):
                self.logger.warning("Không ghi được nhat_ky_binh_luan.xlsx (đang mở trong Excel) — sẽ ghi lại lượt sau")
            cap = self.config.MAX_COMMENTED_POSTS_PER_DAY
            self.logger.info(f"Kết quả vòng: {scanned} nhóm, {new} bài mới, {commented} bài đã bình luận"
                             f" | Hôm nay: {self.db.commented_posts_today()}" + (f"/{cap}" if cap else " bài"))
