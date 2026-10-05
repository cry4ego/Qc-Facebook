import os
import re
import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import ElementNotInteractableException, StaleElementReferenceException

from modules.db import SENT, PENDING, BLOCKED, ERROR, REJECTED

# Thông báo của Facebook (chữ thường)
BLOCKED_PHRASES = [
    "tạm thời bị chặn", "bị chặn", "temporarily blocked", "không thể bình luận", "can't comment",
    "bạn không thể", "you can't", "bị hạn chế", "restricted", "tiêu chuẩn cộng đồng", "community standards",
]
# Nhãn dưới bình luận bị nhóm/Facebook từ chối (chỉ người viết thấy): "Bị từ chối · Xem ý kiến đóng góp"
REJECTED_PHRASES = ["bị từ chối", "xem ý kiến đóng góp", "declined", "see feedback"]
PENDING_PHRASES = ["chờ phê duyệt", "đang chờ duyệt", "chờ quản trị viên", "pending"]

DELETE_BTN_LABELS = ("Chỉnh sửa hoặc xóa bình luận này", "Edit or delete this")


def _norm(s):
    """Gom khoảng trắng để so sánh nội dung"""
    return re.sub(r"\s+", " ", s or "").strip()


def _key(text):
    """Đoạn đầu của bình luận dùng để tìm lại nó trên trang"""
    return _norm(text.split("\n")[0])[:40]


class FacebookCommenter:
    # Ô soạn bình luận thật (aria-label "Bình luận dưới tên <tên>" / "Comment as <name>")
    XP_EDITOR = ("//div[@role='textbox' and @contenteditable='true' and ("
                 "starts-with(@aria-label, 'Bình luận') or starts-with(@aria-label, 'Viết bình luận') or "
                 "starts-with(@aria-label, 'Comment') or starts-with(@aria-label, 'Write a comment'))]")
    # Nút "Viết bình luận" — chỉ là nút bấm để hiện ô soạn, không gõ chữ vào được
    XP_COMMENT_BTN = "//div[@role='button' and (@aria-label='Viết bình luận' or @aria-label='Write a comment')]"

    def __init__(self, driver, config):
        self.driver = driver
        self.config = config
        self.last_article = None  # bình luận vừa gửi (để xóa nếu bị từ chối)

    # ---------- tìm phần tử ----------
    def _visible(self, xpath):
        """Phần tử hiển thị khớp xpath, ưu tiên phần tử nằm trong cửa sổ nổi (dialog) trên cùng"""
        els = [e for e in self.driver.find_elements(By.XPATH, xpath) if e.is_displayed()]
        in_dialog = [e for e in els if e.find_elements(By.XPATH, "./ancestor::div[@role='dialog']")]
        return (in_dialog or els or [None])[-1 if in_dialog else 0]

    def _find_editor(self):
        """Tìm ô soạn bình luận; nếu chưa hiện thì bấm nút 'Viết bình luận' để mở"""
        for _ in range(10):
            editor = self._visible(self.XP_EDITOR)
            if editor:
                return editor
            btn = self._visible(self.XP_COMMENT_BTN)
            if btn:
                # click bằng JS để không bị lớp phủ của dialog chặn
                self.driver.execute_script("arguments[0].click();", btn)
            time.sleep(1.5)
        raise RuntimeError("Không tìm thấy ô soạn bình luận")

    def _my_uid(self):
        cookie = self.driver.get_cookie("c_user")
        return cookie["value"] if cookie else None

    def _my_comments(self):
        """Các bình luận của mình đang hiển thị (nhận theo link tới tài khoản; bỏ phần tử rỗng/ẩn trùng lặp)"""
        uid = self._my_uid()
        if not uid:
            return []
        xp = f"//div[@role='article'][.//a[contains(@href, '/user/{uid}/') or contains(@href, 'id={uid}')]]"
        result = []
        for a in self.driver.find_elements(By.XPATH, xp):
            try:
                if a.is_displayed() and a.text.strip():
                    result.append(a)
            except StaleElementReferenceException:
                continue
        return result

    def find_comment(self, text):
        """Tìm bình luận trên trang có đoạn đầu trùng với text (kể cả bình luận vừa gửi chưa có link tài khoản)"""
        key = _key(text)
        found = None
        for a in self.driver.find_elements(By.XPATH, "//div[@role='article']"):
            try:
                if key and key in _norm(a.text):
                    found = a
            except StaleElementReferenceException:
                continue
        return found

    @staticmethod
    def is_rejected(article):
        try:
            t = article.text.lower()
        except StaleElementReferenceException:
            return False
        return any(p in t for p in REJECTED_PHRASES)

    def _notices(self):
        """Chữ trong các thông báo/hộp thoại ngắn (để dò thông báo bị chặn)"""
        texts = []
        for el in self.driver.find_elements(By.XPATH, "//div[@role='alert' or @role='alertdialog'] | //div[@role='dialog']"):
            try:
                t = el.text
                if t and len(t) < 600:
                    texts.append(t)
            except Exception:
                continue
        return "\n".join(texts).lower()

    # ---------- thao tác ----------
    def _attach_image(self, editor, image_path):
        """Gắn ảnh vào ô bình luận đang mở (tìm input file trong form chứa ô bình luận)"""
        try:
            inputs = editor.find_elements(By.XPATH, "./ancestor::form[1]//input[@type='file']")
            if not inputs:
                inputs = self.driver.find_elements(By.XPATH, "//input[@type='file' and contains(@accept, 'image')]")
            if not inputs:
                return "không tìm thấy nút gắn ảnh"
            inputs[-1].send_keys(os.path.abspath(image_path))
            time.sleep(random.uniform(4, 6))  # chờ ảnh upload
            return ""
        except Exception as e:
            return f"không gắn được ảnh: {e}"

    def _wait_editor_cleared(self, editor, timeout=20):
        """Chờ ô soạn bình luận trống trở lại (dấu hiệu đã gửi xong, kể cả upload ảnh)"""
        end = time.time() + timeout
        while time.time() < end:
            time.sleep(1)
            try:
                if not editor.text.strip():
                    return True
            except Exception:
                # ô soạn bị Facebook vẽ lại sau khi gửi -> lấy ô mới
                editor = self._visible(self.XP_EDITOR)
                if editor is None or not editor.text.strip():
                    return True
        return False

    def open_post(self, post_url):
        self.current_url = post_url
        self.driver.get(post_url)
        time.sleep(random.uniform(4, 7))

    def post_unavailable(self):
        """Bài viết đã bị xóa / ẩn ("Bạn hiện không xem được nội dung này")"""
        body = self.driver.find_element(By.TAG_NAME, "body").text.lower()
        return any(p in body for p in ("không xem được nội dung này", "content isn't available",
                                       "nội dung này hiện không hiển thị", "this content isn't available"))

    def already_commented(self):
        """Bài đã có bình luận của mình chưa (chỉ thấy được bình luận đang hiển thị)"""
        self._find_editor()  # chờ phần bình luận tải xong
        time.sleep(1.5)
        return bool(self._my_comments())

    def _clear_editor(self, editor):
        editor.send_keys(Keys.CONTROL, "a")
        editor.send_keys(Keys.BACKSPACE)
        time.sleep(0.5)

    def _focus_editor(self):
        """Đưa con trỏ vào ô soạn; trả về ô soạn tìm lại SAU khi bấm (ô nở rộng ra, có thể bị thay phần tử)"""
        editor = self._find_editor()
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", editor)
        time.sleep(0.5)
        self.driver.execute_script("arguments[0].focus();", editor)
        try:
            editor.click()
        except Exception:
            pass  # đã focus bằng JS
        time.sleep(1)
        editor = self._find_editor()
        if editor.text.strip():  # còn bản nháp cũ (Facebook giữ nháp cả khi tải lại trang) -> xóa
            self._clear_editor(editor)
        return editor

    def _send_keys(self, editor, *keys):
        """Gõ phím; nếu ô soạn bị Facebook vẽ lại thì tìm lại và gõ tiếp (tối đa 3 lần)"""
        for attempt in range(3):
            try:
                editor.send_keys(*keys)
                return editor
            except (ElementNotInteractableException, StaleElementReferenceException):
                if attempt == 2:
                    raise
                time.sleep(1)
                editor = self._find_editor()
                self.driver.execute_script("arguments[0].focus();", editor)
        return editor

    def _type_text(self, editor, text):
        """Chèn từng dòng nguyên khối (không gõ từng ký tự -> không bị rơi/lẫn chữ), xuống dòng bằng Shift+Enter"""
        for i, line in enumerate(text.split("\n")):
            if i > 0:
                editor = self._send_keys(editor, Keys.SHIFT, Keys.ENTER)
            if line:
                self.driver.execute_cdp_cmd("Input.insertText", {"text": line})
            time.sleep(random.uniform(0.4, 1.0))
        return editor

    def send_comment(self, comment, submit=True):
        """Gửi 1 bình luận vào bài đang mở. comment = {'text': ..., 'image': ...}
        Trả về (trạng thái, ghi chú): Đã đăng / Bị từ chối / Chờ duyệt / Bị chặn / Lỗi.
        Bình luận vừa gửi được giữ ở self.last_article (để xóa nếu bị từ chối)."""
        self.last_article = None
        try:
            # Gõ, rồi đối chiếu nội dung trong ô soạn với nội dung gốc — sai thì gõ lại, vẫn sai thì không gửi
            for attempt in range(2):
                try:
                    editor = self._focus_editor()
                except RuntimeError:
                    # không thấy ô soạn (thường sau khi vừa gửi bình luận trước) -> tải lại bài, thử lại 1 lần
                    if attempt == 1 or not getattr(self, "current_url", None):
                        raise
                    self.open_post(self.current_url)
                    continue
                editor = self._type_text(editor, comment['text'])
                time.sleep(1)
                editor = self._find_editor()
                if _norm(editor.text) == _norm(comment['text']):
                    break
                self._clear_editor(editor)
            else:
                return ERROR, "gõ sai nội dung (đã thử 2 lần), không gửi"

            detail = self._attach_image(editor, comment['image']) if comment.get('image') else ""
            time.sleep(1)

            if not submit:
                return SENT, "chế độ thử: đã gõ xong, KHÔNG gửi"

            editor = self._send_keys(editor, Keys.ENTER)
            cleared = self._wait_editor_cleared(editor)
            time.sleep(2)

            if any(p in self._notices() for p in BLOCKED_PHRASES):
                return BLOCKED, "Facebook báo bị chặn / hạn chế bình luận"
            if not cleared:
                return ERROR, "không gửi được (ô soạn vẫn còn chữ)"

            # Tìm lại bình luận vừa gửi; chờ thêm vài giây vì nhãn "Bị từ chối" có thể hiện chậm
            art = None
            end = time.time() + 15
            while time.time() < end:
                art = self.find_comment(comment['text'])
                if art and self.is_rejected(art):
                    break
                time.sleep(2)
            self.last_article = art
            if art is None:
                return PENDING, "đã gửi nhưng không thấy hiển thị (có thể chờ duyệt hoặc bị ẩn)"
            if self.is_rejected(art):
                return REJECTED, "nhóm/Facebook từ chối bình luận"
            if any(p in art.text.lower() for p in PENDING_PHRASES):
                return PENDING, "bình luận đang chờ quản trị viên duyệt"
            return SENT, detail

        except Exception as e:
            return ERROR, str(e)[:200]

    def delete_comment(self, article):
        """Xóa 1 bình luận của mình: nút '...' -> Xóa -> xác nhận Xóa. Trả về True nếu đã xóa"""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", article)
            time.sleep(1)
            ActionChains(self.driver).move_to_element(article).perform()
            time.sleep(1.5)
            label_xp = " or ".join(f"@aria-label='{l}'" for l in DELETE_BTN_LABELS)
            btns = article.find_elements(By.XPATH, f".//div[@role='button'][{label_xp}]")
            if not btns:
                return False
            ActionChains(self.driver).move_to_element(btns[0]).click().perform()
            time.sleep(1.5)

            # Menu: "Chỉnh sửa" / "Xóa"
            items = [e for e in self.driver.find_elements(
                By.XPATH, "//div[@role='menu']//*[normalize-space(text())='Xóa' or normalize-space(text())='Delete']")
                if e.is_displayed()]
            if not items:
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                return False
            ActionChains(self.driver).move_to_element(items[-1]).click().perform()
            time.sleep(1.5)

            # Hộp thoại xác nhận "Xóa bình luận?" -> nút Xóa
            confirm = [e for e in self.driver.find_elements(
                By.XPATH, "//div[@role='dialog']//div[@role='button'][@aria-label='Xóa' or @aria-label='Delete'"
                          " or .//span[normalize-space(text())='Xóa' or normalize-space(text())='Delete']]")
                if e.is_displayed()]
            if not confirm:
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                return False
            ActionChains(self.driver).move_to_element(confirm[-1]).click().perform()

            # Chờ bình luận biến mất
            end = time.time() + 10
            while time.time() < end:
                time.sleep(1)
                try:
                    if not article.is_displayed():
                        return True
                except StaleElementReferenceException:
                    return True
            return False
        except Exception:
            return False

    def delete_rejected(self):
        """Xóa mọi bình luận của mình đang mang nhãn 'Bị từ chối' trên bài đang mở. Trả về nội dung đã xóa"""
        deleted = []
        for _ in range(10):
            rejected = [a for a in self._my_comments() if self.is_rejected(a)]
            if not rejected:
                break
            text = rejected[0].text
            if not self.delete_comment(rejected[0]):
                break
            deleted.append(text)
            time.sleep(1.5)
        return deleted

    def screenshot(self, path):
        """Chụp màn hình bài viết (cuộn tới bình luận cuối của mình nếu có)"""
        try:
            mine = self._my_comments()
            if mine:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", mine[-1])
                time.sleep(1)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self.driver.save_screenshot(path)
            return os.path.basename(path)
        except Exception:
            return None

    def review_post(self, post_url):
        """Mở lại bài: xóa bình luận bị từ chối, trả về (danh sách nội dung đã xóa, số bình luận của mình còn lại).
        Bài viết đã bị xóa/ẩn -> trả về (None, 0)"""
        self.open_post(post_url)
        if self.post_unavailable():
            return None, 0
        try:
            self._find_editor()
            time.sleep(1.5)
        except Exception:
            pass
        deleted = self.delete_rejected()
        return deleted, len(self._my_comments())
