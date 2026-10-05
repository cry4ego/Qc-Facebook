import os
import re
import time
import random
import logging
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

logger = logging.getLogger(__name__)

# Ô "Bạn viết gì đi..." ở đầu nhóm (chữ có thể đổi theo thời gian -> thêm vào đây)
COMPOSER_TEXTS = ["Bạn viết gì đi", "Viết gì đó", "Write something", "What's on your mind"]
XP_JOIN_BTN = ("//div[@role='main']//div[@role='button'][@aria-label='Tham gia nhóm' or @aria-label='Join group'"
               " or .//span[text()='Tham gia nhóm' or text()='Join group']]")
# Cửa sổ "Tạo bài viết": nhận theo nội dung (có ô soạn + nút Đăng), vì phần mang nhãn "Tạo bài viết" chỉ là thanh tiêu đề
XP_DIALOG = ("//div[@role='dialog'][.//div[@role='textbox' and @contenteditable='true']]"
             "[.//div[@role='button'][@aria-label='Đăng' or @aria-label='Post']]")


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

    def post_to_group(self, group_url, content, image_path=None, submit=True):
        """Đăng bài vào 1 nhóm. Trả về (thành công?, ghi chú)"""
        step = "mở nhóm"
        try:
            self.driver.get(group_url)
            time.sleep(random.uniform(5, 8))

            if [e for e in self.driver.find_elements(By.XPATH, XP_JOIN_BTN) if e.is_displayed()]:
                return False, "chưa tham gia nhóm"

            step = "tìm ô 'Bạn viết gì đi...'"
            cond = " or ".join(f"contains(text(), \"{t}\")" for t in COMPOSER_TEXTS)
            box = self._wait_visible(f"//div[@role='main']//div[@role='button'][.//span[{cond}]]", 15)
            self.driver.execute_script("arguments[0].click();", box)

            step = "mở cửa sổ 'Tạo bài viết'"
            dialog = self._wait_visible(XP_DIALOG, 15)
            editor = self._wait_visible(XP_DIALOG + "//div[@role='textbox' and @contenteditable='true']", 10)
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
                inputs = dialog.find_elements(By.XPATH, ".//input[@type='file' and contains(@accept, 'image')]")
                if inputs:
                    inputs[0].send_keys(os.path.abspath(image_path))
                    time.sleep(random.uniform(5, 7))  # chờ ảnh upload
                else:
                    note = "không tìm thấy nút gắn ảnh — đăng không ảnh"

            step = "bấm 'Đăng'"
            btn = self._wait_visible(XP_DIALOG + "//div[@role='button'][@aria-label='Đăng' or @aria-label='Post']"
                                     "[not(@aria-disabled='true')]", 20)
            if not submit:
                return True, "chế độ thử: đã soạn xong, KHÔNG đăng"
            self.driver.execute_script("arguments[0].click();", btn)

            step = "chờ đăng xong"
            end = time.time() + 30
            while time.time() < end:
                time.sleep(1)
                if not [e for e in self.driver.find_elements(By.XPATH, XP_DIALOG) if e.is_displayed()]:
                    page = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    if "chờ phê duyệt" in page or "pending" in page:
                        note = "; ".join(x for x in (note, "bài đang chờ quản trị viên duyệt") if x)
                    return True, note
            return False, "bấm Đăng nhưng cửa sổ không đóng (chưa đăng được)"

        except TimeoutException:
            return False, f"hết thời gian chờ ở bước: {step} (Facebook có thể đã đổi giao diện)"
        except Exception as e:
            return False, f"lỗi ở bước {step}: {str(e).splitlines()[0][:150]}"

    def post_batch(self, groups, content, image_path=None):
        """Đăng lần lượt vào tối đa MAX_POSTS_PER_DAY nhóm. Hỏng 3 nhóm liên tiếp (không tính nhóm chưa tham gia) thì dừng"""
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
            if note == "chưa tham gia nhóm":
                continue  # không tính vào số nhóm đã thử, không cần chờ
            results.append({"group": url, "success": ok})
            fails = 0 if ok else fails + 1
            if fails >= 3:
                logger.warning("  ⛔ Hỏng 3 nhóm liên tiếp — dừng đăng bài này (xem lỗi ở trên)")
                break
            self._human_delay()
        return results
