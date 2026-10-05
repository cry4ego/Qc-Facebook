"""
Theo dõi bài viết mới trong các nhóm (sắp xếp "Bài viết mới"). Mỗi vòng: lần lượt từng nhóm theo thứ tự ưu tiên,
quét hết bài đăng trong vòng MAX_POST_AGE_MINUTES (bài màn hình trước, rồi máy tính) và bình luận hết, mỗi bài 3 bình
luận độc lập (mỗi sản phẩm 1 bình luận + 1 ảnh). Cuối vòng tự tham gia nhóm chưa tham gia. Mọi kết quả lưu vào SQLite.
"""
import os
import re
import time
import random
from datetime import datetime, timedelta

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

from modules.db import SENT, PENDING, BLOCKED, REJECTED, REJECTED_DELETED, FULL, SAFE
from modules.commenter import _key, _norm
from modules import group_checker as gc
from modules.group_finder import normalize_group_url as gc_url

# ---- Bộ lọc nội dung — CHỈ dùng khi Config.FILTER_BUY_POSTS = True (mặc định tắt: bình luận mọi bài) ----
BUY_PATTERNS = [
    r"cần tìm", r"tìm màn", r"tìm mua", r"cần mua", r"mua màn", r"cần màn", r"cần \d+ màn",
    r"cần (con|em|chiếc|cái) màn", r"ai (có|bán|pass|để lại) màn", r"cần (gấp )?1 màn",
]
SKIP_PATTERNS = [r"cần bán", r"thu mua", r"bán gấp", r"^bán\b", r"cần pass", r"\bdư \d+ màn"]
MONITOR_PATTERN = r"màn|man hinh|monitor|\bmh\b"
OTHER_REGION_PATTERNS = [
    r"\bhcm\b", r"tphcm", r"tp\.?\s?hcm", r"sài gòn", r"saigon", r"\bsg\b", r"hồ chí minh",
    r"đà nẵng", r"bình dương", r"đồng nai", r"cần thơ", r"biên hòa", r"thủ đức", r"nha trang",
]

# ---- Chủ đề bài viết (Config.COMMENT_TOPICS): bình luận bài màn hình trước, rồi bài PC; bài laptop bỏ qua ----
MONITOR_TOPIC = re.compile(
    r"màn|man hinh|monitor|\bmh\b|\d+\s?hz\b|\binch\b|\d{2}\s?in\b|ultrasharp|\b[upse]\d{4}[a-z]*\b", re.IGNORECASE)
# Tên / dòng laptop (bài laptop hay ghi "màn 15.6", "165hz" — là màn của laptop, không phải bài màn hình)
LAPTOP_TOPIC = re.compile(
    r"laptop|lap top|latop|macbook|thinkpad|latitude|inspiron|insprion|vostro|legion|precision|yoga|elitebook|probook"
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
MONITOR, PC, LAPTOP = "Màn hình", "PC", "Laptop"


def topic(text):
    """Chủ đề bài viết: 'Màn hình' / 'PC' / 'Laptop' / None (không liên quan)"""
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


XP_MESSAGE = (".//div[@data-ad-rendering-role='story_message'] | .//div[@data-ad-preview='message']"
              " | .//div[@data-ad-comet-preview='message']")


def classify(text):
    """Trả về (True, '') nếu là bài tìm mua màn hình, ngược lại (False, lý do)"""
    t = text.lower()
    if any(re.search(p, t) for p in SKIP_PATTERNS):
        return False, "bài bán / thu mua"
    if not re.search(MONITOR_PATTERN, t):
        return False, "không nhắc tới màn hình"
    if not any(re.search(p, t) for p in BUY_PATTERNS):
        return False, "không phải bài tìm mua"
    if any(re.search(p, t) for p in OTHER_REGION_PATTERNS):
        return False, "khu vực khác"
    return True, ""


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


class GroupWatcher:
    def __init__(self, driver, config, logger, db):
        self.driver = driver
        self.config = config
        self.logger = logger
        self.db = db

    def _my_uid(self):
        cookie = self.driver.get_cookie("c_user")
        return cookie["value"] if cookie else None

    def _post_url(self, item, group_url):
        """Lấy link bài viết của 1 ô trong bảng tin"""
        anchors = item.find_elements(By.XPATH, ".//a[@href]")
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
        for a in item.find_elements(By.XPATH, ".//a[@href]")[:4]:
            m = re.search(r"/user/(\d+)/", a.get_attribute("href") or "")
            if m:
                return m.group(1)
        return None

    def scan_group(self, group, limit=0):
        """Trả về (trạng thái thành viên, [bài mới chưa bình luận {url, text, age, author, topic}]):
        bài màn hình trước, rồi bài máy tính, mỗi loại mới nhất trước.
        Cuộn dần tới khi gặp bài cũ hơn MAX_POST_AGE_MINUTES, hết WATCH_SCROLLS lần cuộn, hoặc đủ `limit` bài (0 = hết)."""
        group_url = group["group_url"].rstrip("/")
        self.driver.get(group_url + "/?sorting_setting=CHRONOLOGICAL")
        time.sleep(random.uniform(6, 9))
        gc.dismiss_welcome(self.driver)
        self._remember_name(group)
        member = gc.detect_status(self.driver)
        if member in (gc.NOT_JOINED, gc.PENDING):
            return member, []

        my_uid = self._my_uid()
        posts, seen, old_streak = [], set(), 0
        for _ in range(self.config.WATCH_SCROLLS + 1):
            for item in self.driver.find_elements(By.XPATH, "//div[@role='feed']/div"):
                if item.id in seen:
                    continue
                try:
                    full_text = item.text
                    if not full_text.strip():
                        continue  # ô chưa tải xong, lượt cuộn sau xem lại
                    seen.add(item.id)
                    if "sắp xếp bảng feed" in full_text.lower():
                        continue
                    age = parse_age_minutes(full_text)
                    if age is None or age > self.config.MAX_POST_AGE_MINUTES:
                        old_streak += 1  # bài cũ (bài ghim ở đầu không tính: cần 3 bài cũ liền nhau mới dừng)
                        continue
                    old_streak = 0
                    msg = item.find_elements(By.XPATH, XP_MESSAGE)
                    text = msg[0].text if msg else full_text[:400]
                    kind = topic(text)
                    if self.config.COMMENT_TOPICS and kind not in self.config.COMMENT_TOPICS:
                        continue  # không phải chủ đề cần bình luận (mặc định: chỉ bài màn hình)

                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                    time.sleep(0.5)
                    url = self._post_url(item, group_url)
                    if not url or self.db.has_post(url):
                        continue
                    author = self._author_uid(item)
                    if my_uid and author == my_uid:
                        continue  # bài của chính mình
                    if self.config.FILTER_BUY_POSTS and not classify(text)[0]:
                        continue
                    posts.append({"url": url, "text": text, "age": age, "author": author, "topic": kind})
                    if limit and len(posts) >= limit:
                        break
                except Exception:
                    continue  # phần tử bị Facebook vẽ lại, bỏ qua
            if old_streak >= 3 or (limit and len(posts) >= limit):
                break
            self.driver.execute_script("window.scrollBy(0, 1500)")
            time.sleep(random.uniform(2, 3))
        order = list(self.config.COMMENT_TOPICS) or [MONITOR, PC, LAPTOP]  # chủ đề đứng trước được bình luận trước
        posts.sort(key=lambda p: (order.index(p["topic"]) if p["topic"] in order else len(order), p["age"]))
        return member, posts

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
            self.db.set_progress(**fields)
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

    def verify(self, commenter):
        """Mở lại các bài đã bình luận ~1 giờ trước: xóa bình luận bị từ chối muộn, đếm bình luận còn hiển thị"""
        for p in self.db.posts_to_verify(self.config.VERIFY_AFTER_MINUTES, self.config.VERIFY_PER_RUN):
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
        cap = self.config.MAX_COMMENTED_POSTS_PER_DAY
        return bool(cap) and self.db.commented_posts_today() >= cap

    def run(self, groups, commenter, comments, between=None):
        """1 vòng: lần lượt từng nhóm (đã xếp theo ưu tiên) quét hết bài mới trong MAX_POST_AGE_MINUTES rồi bình luận
        hết các bài đó (bài màn hình trước, rồi máy tính), xong mới sang nhóm sau. Cuối vòng tự tham gia các nhóm
        chưa tham gia (điền JOIN_ANSWER + tick) — vòng sau sẽ bình luận các nhóm đó.
        between(): gọi sau mỗi nhóm/bài (đăng bài theo lịch nếu đến giờ).
        Trả về số bài đã bình luận, hoặc "blocked" nếu đang bị Facebook chặn."""
        run_id = self.db.start_run()
        scanned = new = commented = 0
        note = ""
        try:
            until = self._blocked_until()
            if until and datetime.now() < until:
                note = f"Đang tạm dừng do bị chặn tới {until:%H:%M %d/%m}"
                self.logger.warning(note)
                return "blocked"
            if self.db.fix_interrupted():
                self.logger.info("↻ Bài bị bỏ dở lần trước (script bị tắt giữa chừng) sẽ được bình luận lại")

            total = len(groups)
            pct = lambda gi, done=0.0: round(100 * ((gi - 1) + done) / max(total, 1), 1)
            self._progress(reset=True, phase="Quét & bình luận", round_started=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           group_total=total, commented=0, posts_found=0, percent=0)
            not_joined = []
            for gi, g in enumerate(groups, 1):
                if self.db.is_paused():
                    note = "Dừng giữa chừng: tạm dừng từ web"
                    return commented
                if self._daily_full():
                    note = f"Đủ {self.config.MAX_COMMENTED_POSTS_PER_DAY} bài hôm nay"
                    self.logger.info(note)
                    return commented
                if self.db.is_stopped(g["group_url"]):
                    continue  # nhóm từ chối cả bản không SĐT/địa chỉ
                name = g.get("group_name", "")
                self.logger.info(f"→ [{gi}/{len(groups)}] Quét: {name or g['group_url']}")
                self._progress(phase="Quét nhóm", step="Đang cuộn bảng tin tìm bài mới", group_i=gi, group_name=name,
                               group_url=g["group_url"], post_i=0, post_total=0, post_text="", post_url="",
                               comment_i=0, comment_total=0, product="", percent=pct(gi))

                # 1) Quét hết bài mới trong nhóm
                try:
                    member, posts = self.scan_group(g, self.config.MAX_POSTS_PER_GROUP)
                except Exception as e:
                    self.logger.error(f"  ✗ Lỗi quét nhóm: {str(e).splitlines()[0][:150]}")
                    continue
                if member == gc.NOT_JOINED:
                    not_joined.append(g)
                    self.logger.info("  ↷ Chưa tham gia nhóm — sẽ tự tham gia cuối vòng")
                    continue
                if member == gc.PENDING:
                    self.db.set_join(g["group_url"], name, gc.PENDING, "đã gửi yêu cầu, chờ quản trị viên duyệt")
                    self.logger.info("  ↷ Đang chờ quản trị viên duyệt tham gia — bỏ qua")
                    continue
                if member == gc.JOINED:
                    self.db.set_join(g["group_url"], name, gc.JOINED)
                scanned += 1
                self.logger.info(f"  {len(posts)} bài mới chưa bình luận"
                                 + (f" (chủ đề: {', '.join(self.config.COMMENT_TOPICS)})" if self.config.COMMENT_TOPICS else ""))
                new += len(posts)
                self._progress(group_name=g.get("group_name", name), post_total=len(posts), posts_found=new,
                               step=f"Tìm thấy {len(posts)} bài mới", percent=pct(gi, 0.1 if posts else 1))

                # 2) Bình luận hết các bài của nhóm này
                for n, p in enumerate(posts, 1):
                    if self.db.is_paused():
                        note = "Dừng giữa chừng: tạm dừng từ web"
                        return commented
                    if self._daily_full() or self.db.is_stopped(g["group_url"]):
                        break  # đủ giới hạn ngày / nhóm vừa bị đánh dấu ngừng
                    # comments có thể là hàm: đọc lại sản phẩm đang bật trên web trước mỗi bài
                    pool = comments(g) if callable(comments) else comments  # chọn mẫu bình luận ngẫu nhiên cho bài này
                    if not pool:
                        note = "Dừng: không còn sản phẩm nào được bật trên web"
                        self.logger.warning(note)
                        return commented
                    self.logger.info(f"  ★ [{n}/{len(posts)}] {p['topic'] or ''} — bài {p['age']} phút trước: "
                                     f"{p['text'][:70]!r}")
                    self._progress(phase="Bình luận", step="Mở bài viết", post_i=n, post_total=len(posts),
                                   post_text=p["text"][:400], post_url=p["url"], post_topic=p.get("topic") or "",
                                   post_age=p["age"], comment_i=0, comment_total=len(pool), product="",
                                   percent=pct(gi, 0.1 + 0.9 * (n - 1) / len(posts)))
                    result = self.comment_post(commenter, pool, g, p)
                    if result == "blocked":
                        note = "Bị Facebook chặn"
                        return "blocked"
                    if result in ("Hoàn tất", "Một phần"):
                        commented += 1
                        self.logger.info(f"  ✓ {result}: {p['url']}")
                    self._progress(commented=commented, last_result=f"{result}: {p['text'][:80]}",
                                   last_url=p["url"], percent=pct(gi, 0.1 + 0.9 * n / len(posts)))
                    if between:
                        between()
                    if result in ("Hoàn tất", "Một phần") and n < len(posts):
                        wait = random.uniform(self.config.MIN_DELAY, self.config.MAX_DELAY)
                        self._progress(step=f"Nghỉ {wait:.0f} giây trước bài tiếp theo",
                                       next_at=(datetime.now() + timedelta(seconds=wait)).strftime("%Y-%m-%d %H:%M:%S"))
                        time.sleep(wait)
                if between:
                    between()

            # 3) Cuối vòng: tự tham gia các nhóm chưa tham gia (vòng sau bình luận các nhóm này)
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
            return commented
        finally:
            self.db.finish_run(run_id, scanned, new, commented, note)
            if not self.db.export_excel(self.config.COMMENT_LOG_FILE):
                self.logger.warning("Không ghi được nhat_ky_binh_luan.xlsx (đang mở trong Excel) — sẽ ghi lại lượt sau")
            cap = self.config.MAX_COMMENTED_POSTS_PER_DAY
            self.logger.info(f"Kết quả vòng: {scanned} nhóm, {new} bài mới, {commented} bài đã bình luận"
                             f" | Hôm nay: {self.db.commented_posts_today()}" + (f"/{cap}" if cap else " bài"))
