import os
import re
import time
import random
from datetime import datetime

import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

JOINED = "Đã tham gia"
PENDING = "Chờ duyệt"
NOT_JOINED = "Chưa tham gia"
UNAVAILABLE = "Không xem được nhóm"   # trang nhóm báo "Bạn hiện không xem được nội dung này" (thường do bị chặn khỏi nhóm)
UNKNOWN = "Không xác định"

# Cột "use" trong group_status.xlsx — bạn có thể sửa tay
USE_YES = "có"          # được đăng bài + comment
USE_NO = "không"        # bỏ qua
USE_REVIEW = "xem lại"  # nội quy có dấu hiệu cấm quảng cáo -> bỏ qua cho tới khi bạn đổi thành "có"

# Cụm từ trong nội quy cho thấy nhóm cấm quảng cáo/bán hàng/comment chào hàng
RULE_FLAGS = [
    "cấm quảng cáo", "không quảng cáo", "nghiêm cấm quảng cáo", "no ads", "no advertising",
    "cấm bán", "không bán hàng", "không mua bán", "cấm mua bán",
    "cấm chào hàng", "không chào hàng", "cấm seeding", "không seeding", "cấm seed",
    "cấm comment", "không comment quảng cáo", "cấm cmt", "không cmt", "cấm bình luận quảng cáo",
    "không bình luận quảng cáo", "cấm spam comment", "cấm link", "không chèn link",
    "cấm cướp khách", "không cướp khách", "cấm hớt",
]

STATUS_COLUMNS = ["group_url", "group_name", "category", "status", "use", "flags", "checked_at", "rules_file"]

# Selector Facebook (nút Tham gia / Đã tham gia, cửa sổ câu hỏi…) nằm trong modules/fb_selectors.py
from modules import fb_selectors as sel
from modules.fb_selectors import (XP_JOINED_BTN, XP_JOINED, XP_PENDING, XP_JOIN_BTN, XP_TEXT_FIELDS, XP_CHECKBOXES,
                                  XP_RADIOS, SUBMIT_TEXTS, CLOSE_TEXTS)


def _visible(driver, xpath, root=None):
    try:
        return [e for e in (root or driver).find_elements(By.XPATH, xpath) if e.is_displayed()]
    except Exception:
        return []


def detect_status(driver):
    # Nút "Đã tham gia" xét trước: sau khi vào nhóm, mục "Nhóm liên quan" có nút "Tham gia nhóm" của nhóm khác.
    # Ô "Bạn viết gì đi" xét sau cùng: nhóm công khai vẫn hiện ô này cho người chưa tham gia.
    if _visible(driver, XP_PENDING):
        return PENDING
    if _visible(driver, XP_JOINED_BTN):
        return JOINED
    if _join_button(driver):
        return NOT_JOINED
    if _visible(driver, XP_JOINED):
        return JOINED
    if is_unavailable(driver):
        return UNAVAILABLE
    return UNKNOWN


def page_has(driver, phrases):
    """Trang đang mở có 1 trong các cụm chữ (so chữ thường)"""
    try:
        text = driver.find_element(By.TAG_NAME, "body").text.lower()
    except Exception:
        return False
    return any(p in text for p in phrases)


def is_unavailable(driver):
    return page_has(driver, sel.UNAVAILABLE_PHRASES)


def _join_button(driver):
    """Nút "Tham gia nhóm" ở đầu trang nhóm (nút trên cùng — không lấy nút trong thẻ "Nhóm liên quan")"""
    btns = _visible(driver, XP_JOIN_BTN)
    return min(btns, key=lambda e: e.rect["y"]) if btns else None


def dismiss_welcome(driver):
    """Đóng cửa sổ "chào mừng bạn đến với nhóm" (nút Tiếp tục) nếu có"""
    for d in _visible(driver, sel.XP_DIALOG):
        btn = _button(driver, d, sel.WELCOME_TEXTS)
        if btn:
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(1.5)


def _button(driver, root, texts):
    """Nút (không bị khóa) có aria-label hoặc chữ đúng 1 trong texts, ưu tiên theo thứ tự texts"""
    for t in texts:
        els = _visible(driver, sel.xp_button(t), root)
        if els:
            return els[-1]
    return None


def _close_dialog(driver, dialog):
    btn = _button(driver, dialog, CLOSE_TEXTS)
    if btn:
        driver.execute_script("arguments[0].click();", btn)
    else:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
    time.sleep(2)
    for d in _visible(driver, sel.XP_DIALOG):  # hỏi "Bỏ câu trả lời?" -> đồng ý thoát
        btn = _button(driver, d, sel.DISCARD_TEXTS)
        if btn:
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(1)


def _fill_text(driver, el, answer):
    """Điền câu trả lời vào 1 ô (textarea / input / ô soạn contenteditable) nếu ô đang trống"""
    try:
        current = el.get_attribute("value") or (el.text if el.get_attribute("contenteditable") == "true" else "")
        if current.strip():
            return False
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].focus();", el)
        el.click()
        time.sleep(0.3)
        if el.get_attribute("contenteditable") == "true":
            driver.execute_cdp_cmd("Input.insertText", {"text": answer})
        else:
            el.send_keys(answer)
        time.sleep(0.5)
        return True
    except Exception:
        return False


def _tick(driver, el):
    """Tick 1 ô checkbox / radio nếu chưa tick"""
    try:
        if el.get_attribute("aria-checked") == "true" or el.is_selected():
            return False
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", el)
        time.sleep(0.4)
        return True
    except Exception:
        return False


def answer_questions(driver, dialog, answer):
    """Điền `answer` vào mọi ô cần điền, tick mọi checkbox, mỗi nhóm lựa chọn (radio) chọn ô đầu tiên.
    Trả về (số ô đã điền, số ô đã tick)"""
    filled = sum(_fill_text(driver, el, answer) for el in _visible(driver, XP_TEXT_FIELDS, dialog))
    ticked = sum(_tick(driver, el) for el in dialog.find_elements(By.XPATH, XP_CHECKBOXES))
    groups = dialog.find_elements(By.XPATH, sel.XP_RADIOGROUPS)
    for grp in groups:
        radios = grp.find_elements(By.XPATH, XP_RADIOS)
        if radios and not any(r.get_attribute("aria-checked") == "true" or r.is_selected() for r in radios):
            ticked += _tick(driver, radios[0])
    if not groups:  # radio không nằm trong radiogroup: chọn ô đầu tiên
        radios = dialog.find_elements(By.XPATH, XP_RADIOS)
        if radios and not any(r.get_attribute("aria-checked") == "true" or r.is_selected() for r in radios):
            ticked += _tick(driver, radios[0])
    return filled, ticked


def auto_join(driver, logger=None, answer="ok"):
    """Bấm Tham gia ở trang nhóm đang mở. Nếu có cửa sổ câu hỏi duyệt thành viên / đồng ý nội quy:
    điền `answer` vào mọi ô cần điền, tick mọi ô rồi bấm Gửi. Trả về (trạng thái, ghi chú)"""
    btn = _join_button(driver)
    if not btn:
        return detect_status(driver), "không thấy nút Tham gia nhóm"
    driver.execute_script("arguments[0].click();", btn)
    time.sleep(random.uniform(4, 6))

    note = ""
    for _ in range(3):  # có nhóm hỏi nhiều bước (câu hỏi -> nội quy -> gửi)
        dialogs = [d for d in _visible(driver, sel.XP_DIALOG)
                   if d.find_elements(By.XPATH, XP_TEXT_FIELDS + " | " + XP_CHECKBOXES + " | " + XP_RADIOS)
                   or _button(driver, d, SUBMIT_TEXTS)]
        if not dialogs:
            break
        dialog = dialogs[-1]
        filled, ticked = answer_questions(driver, dialog, answer)
        btn = _button(driver, dialog, SUBMIT_TEXTS)
        if not btn:
            time.sleep(2)  # nút Gửi có thể còn khóa vài giây sau khi điền
            btn = _button(driver, dialog, SUBMIT_TEXTS)
        if not btn:
            _close_dialog(driver, dialog)
            return UNKNOWN, f"điền {filled} ô, tick {ticked} ô nhưng không bấm được nút Gửi (còn ô bắt buộc?)"
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(random.uniform(4, 6))
        parts = [f"điền '{answer}' vào {filled} ô" if filled else "", f"tick {ticked} ô" if ticked else ""]
        if filled or ticked or not note:  # bước sau chỉ bấm "Xong" thì giữ ghi chú bước trả lời câu hỏi
            note = ", ".join(x for x in parts if x) or "đã bấm xác nhận"

    dismiss_welcome(driver)
    driver.refresh()
    time.sleep(random.uniform(5, 7))
    dismiss_welcome(driver)
    st = detect_status(driver)
    if st == PENDING:
        note = "; ".join(x for x in (note, "đã gửi yêu cầu, chờ quản trị viên duyệt") if x)
    elif st == NOT_JOINED:
        note = "; ".join(x for x in (note, "bấm Tham gia nhưng chưa thành công") if x)
    return st, note


def _group_id(url):
    m = re.search(r"/groups/([^/?#]+)", url)
    return m.group(1) if m else re.sub(r"\W+", "_", url)


def load_status(path):
    if not os.path.exists(path):
        return {}
    df = pd.read_excel(path).fillna("")
    return {row["group_url"]: row for row in df.to_dict("records")}


def save_status(path, status_map):
    df = pd.DataFrame(list(status_map.values()), columns=STATUS_COLUMNS)
    df.to_excel(path, index=False)


def usable_groups(groups, status_path):
    """Loại các nhóm đã kiểm tra mà use ≠ 'có' (chưa tham gia / chờ duyệt / nội quy cần xem lại).
    Nhóm chưa từng kiểm tra bằng lệnh 'join' vẫn được dùng."""
    status = load_status(status_path)
    return [g for g in groups
            if g["group_url"] not in status or status[g["group_url"]].get("use") == USE_YES]


class GroupChecker:
    def __init__(self, driver, config, logger):
        self.driver = driver
        self.config = config
        self.logger = logger
        os.makedirs(config.RULES_DIR, exist_ok=True)

    def detect_status(self):
        return detect_status(self.driver)

    def fetch_rules(self, group_url):
        """Lưu nội dung trang Giới thiệu (có phần nội quy) ra file .txt, trả về (đường dẫn, các cờ cảnh báo)"""
        self.driver.get(group_url.rstrip("/") + "/about")
        time.sleep(random.uniform(4, 7))
        mains = self.driver.find_elements(By.XPATH, sel.XP_MAIN)
        text = mains[0].text if mains else self.driver.find_element(By.TAG_NAME, "body").text

        path = os.path.join(self.config.RULES_DIR, f"{_group_id(group_url)}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{group_url}\n\n{text}")

        lower = text.lower()
        flags = [p for p in RULE_FLAGS if p in lower]
        return path, flags

    def join(self):
        """Bấm Tham gia (nhóm có câu hỏi duyệt thành viên thì bỏ qua)"""
        st, note = auto_join(self.driver, self.logger, self.config.JOIN_ANSWER)
        if note:
            self.logger.info(f"  {st}: {note}")
        return st != UNKNOWN

    def run(self, groups, status_path):
        status = load_status(status_path)
        # Bỏ qua nhóm đã tham gia & đã lưu nội quy; ưu tiên nhóm Màn hình trước
        todo = [g for g in groups if status.get(g["group_url"], {}).get("status") != JOINED]
        todo.sort(key=lambda g: g.get("category") != "Màn hình")

        joined_clicks = 0
        for i, g in enumerate(todo[:self.config.CHECK_PER_RUN]):
            url = g["group_url"]
            self.logger.info(f"[{i + 1}/{min(len(todo), self.config.CHECK_PER_RUN)}] {g.get('group_name', '')}")
            try:
                self.driver.get(url)
                time.sleep(random.uniform(4, 8))
                st = self.detect_status()

                clicked = False
                if st == NOT_JOINED and joined_clicks < self.config.JOIN_PER_RUN:
                    if self.join():
                        clicked = True
                        joined_clicks += 1
                        self.driver.get(url)
                        time.sleep(random.uniform(4, 6))
                        st = self.detect_status()

                rules_file, flags = self.fetch_rules(url)

                old = status.get(url, {})
                if st != JOINED:
                    use = USE_NO
                elif old.get("status") == JOINED and old.get("use"):
                    use = old["use"]  # giữ lựa chọn bạn đã sửa tay
                else:
                    use = USE_REVIEW if flags else USE_YES

                status[url] = {
                    "group_url": url,
                    "group_name": g.get("group_name", ""),
                    "category": g.get("category", ""),
                    "status": st,
                    "use": use,
                    "flags": ", ".join(flags),
                    "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "rules_file": os.path.relpath(rules_file, self.config.BASE_DIR),
                }
                save_status(status_path, status)  # lưu ngay để không mất kết quả nếu bị dừng giữa chừng
                self.logger.info(f"  {st} | use={use}" + (f" | ⚠ {', '.join(flags)}" if flags else ""))

                if clicked:
                    time.sleep(random.uniform(self.config.JOIN_MIN_DELAY, self.config.JOIN_MAX_DELAY))
                else:
                    time.sleep(random.uniform(5, 15))

            except Exception as e:
                self.logger.error(f"  ✗ Lỗi: {e}")

        counts = pd.Series([s["status"] for s in status.values()]).value_counts().to_dict()
        self.logger.info(f"Đã bấm tham gia {joined_clicks} nhóm. Tổng trạng thái: {counts}")
        self.logger.info(f"Còn {max(0, len(todo) - self.config.CHECK_PER_RUN)} nhóm chưa kiểm tra — chạy lại lệnh join lần sau")
