import os
import re
import time
import random
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException

logger = logging.getLogger(__name__)

# Selector Facebook (ô "Bạn viết gì đi…", cửa sổ Tạo bài viết, nút Đăng) nằm trong modules/fb_selectors.py
from modules import fb_selectors as sel
from modules import group_checker as gc
from modules.fb_selectors import COMPOSER_TEXTS, XP_JOIN_BTN, XP_POST_DIALOG as XP_DIALOG

# Nhóm KHÔNG đăng được vì lý do của nhóm (không phải lỗi giao diện): không tính vào "hỏng 3 nhóm liên tiếp",
# không chờ MIN_DELAY..MAX_DELAY, và ... giờ sau mới thử đăng lại vào nhóm đó (SKIP_HOURS)
NOT_JOINED_NOTE = "chưa tham gia nhóm"
UNAVAILABLE_NOTE = "không xem được nhóm (Facebook báo 'không xem được nội dung này' — có thể đã bị chặn khỏi nhóm)"
PENDING_LIMIT_NOTE = "nhóm đang giữ quá nhiều bài/bình luận chờ duyệt của bạn — Facebook ẩn ô viết bài"
SELL_ONLY_NOTE = "nhóm chỉ cho đăng tin bán ('Bán gì đó'), không có ô 'Bạn viết gì đi'"
SKIP_HOURS = {PENDING_LIMIT_NOTE: 24, SELL_ONLY_NOTE: 30 * 24}
GROUP_NOTES = (NOT_JOINED_NOTE, UNAVAILABLE_NOTE, PENDING_LIMIT_NOTE, SELL_ONLY_NOTE)
POST_WAIT_SECONDS = 45  # chờ cửa sổ đăng bài đóng lại sau khi bấm Đăng (có ảnh thì tải lên lâu hơn)


def _norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


class FacebookPoster:
    def __init__(self, driver, config):
        self.driver = driver
        self.config = config

    def _human_delay(self):
        time.sleep(random.uniform(self.config.MIN_DELAY, self.config.MAX_DELAY))

    def _short_delay(self):
        time.sleep(random.uniform(2, 4))

    def _wait_visible(self, xpath, timeout):
        end = time.time() + timeout
        while time.time() < end:
            els = [e for e in self.driver.find_elements(By.XPATH, xpath) if e.is_displayed()]
            if els:
                return els[0]
            time.sleep(0.5)
        raise TimeoutException(xpath)

    def _visible_els(self, xpath):
        return [e for e in self.driver.find_elements(By.XPATH, xpath) if e.is_displayed()]

    def _group_problem(self):
        """Vì sao trang nhóm không có ô 'Bạn viết gì đi' (None = không rõ, có thể Facebook đổi giao diện)"""
        if gc.is_unavailable(self.driver):
            return UNAVAILABLE_NOTE
        if gc.page_has(self.driver, sel.PENDING_LIMIT_PHRASES):
            return PENDING_LIMIT_NOTE
        if self._visible_els(sel.XP_SELL_ONLY_BUTTON):
            return SELL_ONLY_NOTE
        return None

    def _notice(self):
        """Chữ trong thông báo / cửa sổ đang hiện (trừ cửa sổ soạn bài) — lý do Facebook không cho đăng"""
        texts = []
        for e in self.driver.find_elements(By.XPATH, sel.XP_NOTICE_TEXTS):
            try:
                if e.is_displayed() and e.text.strip():
                    texts.append(_norm(e.text))
            except Exception:
                continue
        return " | ".join(texts)[:300]

    def _screenshot(self, name):
        try:
            os.makedirs(self.config.SCREENSHOT_DIR, exist_ok=True)
            path = os.path.join(self.config.SCREENSHOT_DIR, f"{name}_{time.strftime('%Y%m%d_%H%M%S')}.png")
            self.driver.save_screenshot(path)
            return path
        except Exception:
            return None

    def close_composer(self):
        """Đóng cửa sổ Tạo bài viết còn mở (bỏ bản nháp) để nhóm sau bắt đầu sạch"""
        try:
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(1.5)
            for text in sel.DISCARD_TEXTS:
                for btn in self._visible_els("//div[@role='dialog']" + sel.xp_button(text)[1:]):
                    self.driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1)
        except Exception:
            pass  # chỉ là dọn dẹp: trang nhóm sau vẫn được mở lại từ đầu

    def post_to_group(self, group_url, content, image_path=None, submit=True):
        """Đăng bài vào 1 nhóm. Trả về (thành công?, ghi chú)"""
        step = "mở nhóm"
        try:
            self.driver.get(group_url)
            time.sleep(random.uniform(5, 8))

            if [e for e in self.driver.find_elements(By.XPATH, XP_JOIN_BTN) if e.is_displayed()]:
                return False, NOT_JOINED_NOTE

            step = "tìm ô 'Bạn viết gì đi...'"
            try:
                box = self._wait_visible(sel.xp_composer_button(), 15)
            except TimeoutException:
                problem = self._group_problem()
                if problem:
                    return False, problem
                raise
            self.driver.execute_script("arguments[0].click();", box)

            step = "mở cửa sổ 'Tạo bài viết'"
            dialog = self._wait_visible(XP_DIALOG, 15)
            editor = self._wait_visible(sel.XP_POST_DIALOG_EDITOR, 10)
            self.driver.execute_script("arguments[0].focus();", editor)
            editor.click()
            time.sleep(1)

            # Chèn nguyên từng dòng (Enter xuống dòng trong ô đăng bài), rồi đối chiếu nội dung
            step = "gõ nội dung"
            for i, line in enumerate(content.split("\n")):
                if i > 0:
                    editor.send_keys("\n")
                if line:
                    self.driver.execute_cdp_cmd("Input.insertText", {"text": line})
                time.sleep(random.uniform(0.4, 1.0))
            time.sleep(1)
            if _norm(editor.text) != _norm(content):
                return False, "gõ sai nội dung, không đăng"

            note = ""
            if image_path and os.path.exists(image_path):
                step = "gắn ảnh"
                inputs = dialog.find_elements(By.XPATH, sel.XP_DIALOG_IMAGE_INPUT)
                if inputs:
                    inputs[0].send_keys(os.path.abspath(image_path))
                    time.sleep(random.uniform(5, 7))  # chờ ảnh upload
                else:
                    note = "không tìm thấy nút gắn ảnh — đăng không ảnh"

            step = "bấm 'Đăng'"
            btn = self._wait_visible(sel.XP_POST_DIALOG_SUBMIT, 20)
            if not submit:
                return True, "chế độ thử: đã soạn xong, KHÔNG đăng"
            self.driver.execute_script("arguments[0].click();", btn)

            step = "chờ đăng xong"
            end = time.time() + POST_WAIT_SECONDS
            while time.time() < end:
                time.sleep(1)
                if not [e for e in self.driver.find_elements(By.XPATH, XP_DIALOG) if e.is_displayed()]:
                    page = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    if "chờ phê duyệt" in page or "pending" in page:
                        note = "; ".join(x for x in (note, "bài đang chờ quản trị viên duyệt") if x)
                    return True, note
            # Cửa sổ không đóng: ghi lại Facebook báo gì + chụp màn hình để biết nguyên nhân
            notice = self._notice()
            if any(p in notice.lower() for p in sel.PENDING_LIMIT_PHRASES):
                return False, PENDING_LIMIT_NOTE
            shot = self._screenshot("dang_bai_loi")
            return False, ("bấm Đăng nhưng cửa sổ không đóng (chưa đăng được)"
                           + (f" — Facebook báo: {notice}" if notice else " — không có thông báo nào")
                           + (f" — ảnh chụp: {os.path.basename(shot)}" if shot else ""))

        except TimeoutException:
            return False, f"hết thời gian chờ ở bước: {step} (Facebook có thể đã đổi giao diện)"
        except Exception as e:
            return False, f"lỗi ở bước {step}: {str(e).splitlines()[0][:150]}"

    def post_batch(self, groups, content, image_path=None, on_result=None):
        """Đăng lần lượt vào tối đa MAX_POSTS_PER_DAY nhóm. Hỏng 3 nhóm liên tiếp (không tính nhóm chưa tham gia) thì dừng.
        on_result(nhóm, thành công?, ghi chú): gọi sau mỗi nhóm (vd ghi nhớ nhóm chưa tham gia)"""
        results = []
        fails = 0
        for group in groups:
            if len(results) >= self.config.MAX_POSTS_PER_DAY:
                logger.info(f"Đã thử đủ {self.config.MAX_POSTS_PER_DAY} nhóm cho bài này (MAX_POSTS_PER_DAY)")
                break
            url = group.get('group_url')
            ok, note = self.post_to_group(url, content, image_path)
            logger.info(f"  {'✓ Đã đăng' if ok else '✗ Không đăng được'}: {group.get('group_name') or url}"
                        + (f" — {note}" if note else ""))
            if on_result:
                on_result(group, ok, note)
            if note in GROUP_NOTES:
                continue  # lý do của nhóm (chưa tham gia, chỉ đăng tin bán…): không tính là hỏng, không cần chờ
            if not ok:
                self.close_composer()  # bỏ bản nháp còn mở, nhóm sau bắt đầu sạch
            results.append({"group": url, "success": ok})
            fails = 0 if ok else fails + 1
            if fails >= 3:
                logger.warning("  ⛔ Hỏng 3 nhóm liên tiếp — dừng đăng bài này (xem lỗi ở trên)")
                break
            self._human_delay()
        return results
