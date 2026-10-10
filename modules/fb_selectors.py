"""
MỌI selector / chữ giao diện Facebook mà bot dựa vào — Facebook đổi giao diện thì sửa ở ĐÂY.

Gồm: XPath tìm phần tử, aria-label của nút, và các cụm chữ Facebook hiển thị (tiếng Việt + tiếng Anh).
Các module khác chỉ import từ file này, không tự viết selector.
"""
import re

# ---------- Trang nhóm & bảng tin ----------
GROUP_FEED_URL = "{group_url}/?sorting_setting=CHRONOLOGICAL"     # bảng tin nhóm, sắp xếp "Bài viết mới"
GROUP_ABOUT_URL = "{group_url}/about"                              # trang Giới thiệu (số thành viên, hoạt động)
XP_MAIN = "//div[@role='main']"
XP_FEED_ITEMS = "//div[@role='feed']/div"                          # mỗi ô = 1 bài viết
FEED_SORT_BANNER = "sắp xếp bảng feed"                              # ô đầu bảng tin (không phải bài viết)
XP_MESSAGE = (".//div[@data-ad-rendering-role='story_message'] | .//div[@data-ad-preview='message']"
              " | .//div[@data-ad-comet-preview='message']")        # phần nội dung bài trong 1 ô
XP_LINKS = ".//a[@href]"
XP_DIALOG = "//div[@role='dialog']"

# ---------- Tương tác của bài trong bảng tin (đọc bằng JS trong 1 lần gọi) ----------
JS_ITEM_LABELS = """
const out = [];
for (const el of arguments[0].querySelectorAll('[aria-label]')) out.push(el.getAttribute('aria-label'));
return out;"""
# aria-label tổng cảm xúc của bài: "Thích: 2 người", "Tất cả cảm xúc: 12" ; nút mở danh sách cảm xúc
REACTION_LABEL = re.compile(r"^[^:]{1,40}:\s*([\d.,]+\s*[KkNnMm]?)\s*(người|people)?\s*$")
REACTION_SUMMARY_LABELS = ("Xem ai đã bày tỏ cảm xúc về tin này", "See who reacted to this")
# aria-label của 1 bình luận đang hiện: "Bình luận dưới tên <tên> vào 5 phút trước" (ô soạn của mình không có "vào")
COMMENT_LABEL = re.compile(r"^(Bình luận dưới tên|Comment by) .+ (vào|at|·) ", re.IGNORECASE)
# chữ đếm kiểu cũ: "45 bình luận", "6 lượt chia sẻ", "Tất cả cảm xúc:"
COMMENTS_TEXT = re.compile(r"^([\d.,]+\s*[KkNnMm]?)\s*(bình luận|comments?)$", re.IGNORECASE)
SHARES_TEXT = re.compile(r"^([\d.,]+\s*[KkNnMm]?)\s*(lượt chia sẻ|chia sẻ|shares?)$", re.IGNORECASE)
ALL_REACTIONS_TEXT = ("tất cả cảm xúc:", "all reactions:")
SEE_MORE_TEXTS = ("xem thêm", "see more", "đã chỉnh sửa", "edited", "·")

# ---------- Trang Giới thiệu nhóm ----------
ABOUT_TOTAL_MEMBERS = re.compile(r"(?:tổng cộng|total members:?)\s*([\d.,]+)\s*(?:thành viên)?", re.IGNORECASE)
ABOUT_MEMBERS = re.compile(r"([\d.,]+\s*(?:K|N|M|Tr|triệu)?)\s*(?:thành viên|members)", re.IGNORECASE)
ABOUT_POSTS_TODAY = re.compile(r"(?:hôm nay có\s*([\d.,]+)\s*bài viết mới|([\d.,]+)\s*new posts? today)",
                               re.IGNORECASE)
ABOUT_POSTS_PERIOD = re.compile(r"([\d.,]+)\s*bài viết(?: mới)? trong (tháng|tuần) trước|"
                                r"([\d.,]+)\s*posts? (?:in the )?(?:last|past) (month|week)", re.IGNORECASE)

# ---------- Trạng thái thành viên & tham gia nhóm ----------
XP_JOINED_BTN = "//div[@role='main']//div[@role='button'][@aria-label='Đã tham gia' or @aria-label='Joined']"
XP_JOINED = ("//div[@aria-label='Đã tham gia' or @aria-label='Joined']"
             " | //div[@role='main']//span[contains(text(), 'Bạn viết gì đi') or contains(text(), 'Viết gì đó')"
             " or contains(text(), 'Write something')]")
XP_PENDING = ("//div[@aria-label='Hủy yêu cầu' or @aria-label='Cancel request']"
              " | //span[text()='Hủy yêu cầu' or text()='Cancel request']")
XP_JOIN_BTN = ("//div[@role='main']//div[@role='button'][@aria-label='Tham gia nhóm' or @aria-label='Join group'"
               " or .//span[text()='Tham gia nhóm' or text()='Join group']]")
# Cửa sổ hiện ra sau khi bấm Tham gia: câu hỏi duyệt thành viên và/hoặc ô "Tôi đồng ý với nội quy nhóm"
XP_TEXT_FIELDS = (".//textarea | .//input[@type='text' or not(@type)]"
                  " | .//*[@role='textbox' and @contenteditable='true']")
XP_CHECKBOXES = ".//input[@type='checkbox'] | .//*[@role='checkbox']"
XP_RADIOS = ".//input[@type='radio'] | .//*[@role='radio']"
XP_RADIOGROUPS = ".//*[@role='radiogroup']"
SUBMIT_TEXTS = ["Gửi", "Submit", "Tôi đồng ý", "Đồng ý", "I agree", "Agree", "Tham gia nhóm", "Join group",
                "Tham gia", "Join", "Tiếp", "Next", "Xong", "Done"]
CLOSE_TEXTS = ["Đóng", "Close", "Hủy", "Cancel", "Thoát", "Rời khỏi", "Bỏ", "Discard", "Leave", "Exit"]
DISCARD_TEXTS = ["Thoát", "Rời khỏi", "Bỏ", "Discard", "Leave", "Exit"]
WELCOME_TEXTS = ["Tiếp tục", "Continue", "Đóng", "Close"]


def xp_button(text):
    """Nút (không bị khóa) có aria-label hoặc chữ đúng bằng text"""
    return (f".//div[@role='button' or self::button][not(@aria-disabled='true')]"
            f"[@aria-label='{text}' or .//span[normalize-space(text())='{text}']]")


# ---------- Bình luận ----------
# Ô soạn bình luận thật (aria-label "Bình luận dưới tên <tên>" / "Comment as <name>")
XP_EDITOR = ("//div[@role='textbox' and @contenteditable='true' and ("
             "starts-with(@aria-label, 'Bình luận') or starts-with(@aria-label, 'Viết bình luận') or "
             "starts-with(@aria-label, 'Comment') or starts-with(@aria-label, 'Write a comment'))]")
# Nút "Viết bình luận" — chỉ là nút bấm để hiện ô soạn, không gõ chữ vào được
XP_COMMENT_BTN = "//div[@role='button' and (@aria-label='Viết bình luận' or @aria-label='Write a comment')]"
XP_IN_DIALOG = "./ancestor::div[@role='dialog']"
XP_ARTICLES = "//div[@role='article']"
XP_NOTICES = "//div[@role='alert' or @role='alertdialog'] | //div[@role='dialog']"
XP_FORM_FILE_INPUT = "./ancestor::form[1]//input[@type='file']"
XP_IMAGE_FILE_INPUT = "//input[@type='file' and contains(@accept, 'image')]"
XP_MENU_DELETE = "//div[@role='menu']//*[normalize-space(text())='Xóa' or normalize-space(text())='Delete']"
XP_CONFIRM_DELETE = ("//div[@role='dialog']//div[@role='button'][@aria-label='Xóa' or @aria-label='Delete'"
                     " or .//span[normalize-space(text())='Xóa' or normalize-space(text())='Delete']]")
DELETE_BTN_LABELS = ("Chỉnh sửa hoặc xóa bình luận này", "Edit or delete this")


def xp_my_comments(uid):
    """Bình luận của tài khoản có id uid (nhận theo link tới trang cá nhân)"""
    return f"//div[@role='article'][.//a[contains(@href, '/user/{uid}/') or contains(@href, 'id={uid}')]]"


def xp_delete_button(article_labels=DELETE_BTN_LABELS):
    cond = " or ".join(f"@aria-label='{l}'" for l in article_labels)
    return f".//div[@role='button'][{cond}]"


# Thông báo của Facebook (so khớp chữ thường)
BLOCKED_PHRASES = [
    "tạm thời bị chặn", "bị chặn", "temporarily blocked", "không thể bình luận", "can't comment",
    "bạn không thể", "you can't", "bị hạn chế", "restricted", "tiêu chuẩn cộng đồng", "community standards",
]
# Nhãn dưới bình luận bị nhóm/Facebook từ chối (chỉ người viết thấy): "Bị từ chối · Xem ý kiến đóng góp"
REJECTED_PHRASES = ["bị từ chối", "xem ý kiến đóng góp", "declined", "see feedback"]
PENDING_PHRASES = ["chờ phê duyệt", "đang chờ duyệt", "chờ quản trị viên", "pending"]
UNAVAILABLE_PHRASES = ("không xem được nội dung này", "content isn't available",
                       "nội dung này hiện không hiển thị", "this content isn't available")
# Nhóm ẩn ô viết bài vì mình đang có quá nhiều bài / bình luận chờ quản trị viên duyệt
PENDING_LIMIT_PHRASES = ("đạt giới hạn nội dung đang chờ", "limit for pending content", "reached the pending content limit")

# ---------- Đăng bài vào nhóm ----------
COMPOSER_TEXTS = ["Bạn viết gì đi", "Viết gì đó", "Write something", "What's on your mind"]
# Cửa sổ "Tạo bài viết": nhận theo nội dung (có ô soạn + nút Đăng), vì phần mang nhãn "Tạo bài viết" chỉ là thanh tiêu đề
XP_POST_DIALOG = ("//div[@role='dialog'][.//div[@role='textbox' and @contenteditable='true']]"
                  "[.//div[@role='button'][@aria-label='Đăng' or @aria-label='Post']]")
XP_POST_DIALOG_EDITOR = XP_POST_DIALOG + "//div[@role='textbox' and @contenteditable='true']"
XP_POST_DIALOG_SUBMIT = (XP_POST_DIALOG + "//div[@role='button'][@aria-label='Đăng' or @aria-label='Post']"
                         "[not(@aria-disabled='true')]")
XP_DIALOG_IMAGE_INPUT = ".//input[@type='file' and contains(@accept, 'image')]"
# Nhóm "Mua và bán" chỉ có nút "Bán gì đó" (đăng tin niêm yết), không có ô "Bạn viết gì đi"
XP_SELL_ONLY_BUTTON = ("//div[@role='main']//div[@role='button']"
                       "[.//span[contains(text(), 'Bán gì đó') or contains(text(), 'Sell something')]]")
# Thông báo / cửa sổ đang hiện, trừ cửa sổ soạn bài (có ô nhập chữ) — đọc lý do Facebook không cho đăng
XP_NOTICE_TEXTS = ("//div[@role='alert'] | //div[@role='alertdialog']"
                   " | //div[@role='dialog'][not(.//div[@role='textbox'])]")


def xp_composer_button(texts=COMPOSER_TEXTS):
    """Ô "Bạn viết gì đi…" ở đầu nhóm (bấm để mở cửa sổ Tạo bài viết)"""
    cond = " or ".join(f'contains(text(), "{t}")' for t in texts)
    return f"//div[@role='main']//div[@role='button'][.//span[{cond}]]"

# ---------- Tìm nhóm ----------
GROUP_SEARCH_URL = "https://www.facebook.com/search/groups/?q={query}"
XP_GROUP_LINKS = ".//a[contains(@href, '/groups/')]"
