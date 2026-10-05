import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Facebook credentials (dùng .env để bảo mật)
    FB_EMAIL = os.getenv("FB_EMAIL")
    FB_PASSWORD = os.getenv("FB_PASSWORD")

    # Đường dẫn
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    LOG_DIR = os.path.join(BASE_DIR, "logs")
    IMAGE_DIR = os.path.join(DATA_DIR, "images")
    GROUPS_FILE = os.path.join(DATA_DIR, "groups.xlsx")
    GROUPS_FOUND_FILE = os.path.join(DATA_DIR, "groups_found.xlsx")  # nhóm script tự tìm theo từ khóa (xóa dòng = bỏ nhóm)
    SCHEDULE_FILE = os.path.join(DATA_DIR, "schedule.xlsx")
    COMMENTS_FILE = os.path.join(DATA_DIR, "comments.txt")       # 3 bình luận độc lập, mỗi cái 1 ảnh
    STATUS_FILE = os.path.join(DATA_DIR, "group_status.xlsx")    # trạng thái tham gia + nội quy
    RULES_DIR = os.path.join(DATA_DIR, "group_rules")            # nội quy từng nhóm (.txt)
    POST_HISTORY_FILE = os.path.join(DATA_DIR, "post_history.json")
    SCHEDULE_DONE_FILE = os.path.join(DATA_DIR, "schedule_done.json")  # bài trong lịch đã đăng hôm nay
    DB_FILE = os.path.join(DATA_DIR, "qc_facebook.db")                 # mọi hoạt động bình luận (web đọc)
    SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots")             # ảnh chụp bài sau khi bình luận
    COMMENT_LOG_FILE = os.path.join(DATA_DIR, "nhat_ky_binh_luan.xlsx")  # bản Excel của nhật ký

    # Chỉ đăng bài/comment vào nhóm thuộc khu vực này (cột region trong groups.xlsx). Để "" = tất cả
    TARGET_REGION = "Hà Nội"
    # Thứ tự ưu tiên nhóm: nhóm thuộc khu vực này trước, rồi nhóm hoạt động mạnh (cột activity) + đông thành viên
    PRIORITY_REGION = "Hà Nội"

    # Tìm & tham gia nhóm mới theo từ khóa (nhóm nhiều khách hàng tiềm năng)
    GROUP_KEYWORDS = ["PC", "màn hình", "Hà Nội", "setup pc", "phụ kiện màn hình", "đồ công nghệ", "chợ đồ cũ", "2nd"]
    GROUP_SEARCH_QUERIES = ["màn hình Hà Nội", "màn hình máy tính Hà Nội", "PC Hà Nội", "setup pc Hà Nội", "setup pc",
                            "phụ kiện màn hình", "đồ công nghệ Hà Nội", "chợ đồ cũ Hà Nội", "đồ cũ 2nd Hà Nội"]
    GROUP_SEARCH_EVERY_HOURS = 24     # bao lâu tìm nhóm mới 1 lần (cuối vòng quét)
    MIN_GROUP_MEMBERS = 1000          # bỏ nhóm ít hơn ... thành viên
    MAX_FOUND_GROUPS = 30             # giữ tối đa ... nhóm tự tìm (Hà Nội & đông thành viên trước)

    # Giới hạn hành động
    MIN_DELAY = 30          # chờ giữa 2 bài (đăng hoặc bình luận), giây
    MAX_DELAY = 120
    MAX_POSTS_PER_DAY = 10  # số nhóm tối đa cho mỗi bài trong lịch đăng

    # Theo dõi bài mới & tự bình luận (chạy liên tục: từng nhóm quét hết bài mới -> bình luận hết -> sang nhóm sau;
    # hết nhóm thì tự tham gia các nhóm chưa tham gia, rồi quét lại từ đầu)
    MAX_POST_AGE_MINUTES = 24 * 60    # chỉ bình luận bài đăng trong vòng 24 giờ
    MAX_POSTS_PER_GROUP = 0           # mỗi vòng 1 nhóm tối đa ... bài; 0 = không giới hạn (bình luận hết)
    COMMENT_TOPICS = ["Màn hình", "PC"]  # chủ đề được bình luận, theo thứ tự ưu tiên; thêm "Laptop" = cả bài laptop; [] = mọi bài
    MAX_COMMENTED_POSTS_PER_DAY = 0   # giới hạn số bài/ngày; 0 = không giới hạn
    ROUND_IDLE_MINUTES = 5            # vòng quét không có bài mới -> chờ ... phút rồi quét lại
    WATCH_SCROLLS = 60                # số lần cuộn tối đa mỗi nhóm (dừng sớm khi gặp bài cũ hơn 24 giờ)
    COMMENT_GAP_MIN = 15              # chờ giữa 3 bình luận trong cùng 1 bài, giây
    COMMENT_GAP_MAX = 40
    FILTER_BUY_POSTS = False          # True = chỉ bình luận bài TÌM MUA màn hình (bộ lọc trong modules/watcher.py)
    BLOCK_COOLDOWN_HOURS = 6          # Facebook báo chặn -> ngừng tự bình luận trong ... giờ
    VERIFY_AFTER_MINUTES = 60         # sau ... phút mở lại bài kiểm tra bình luận còn hay bị xóa
    VERIFY_PER_RUN = 40               # số bài kiểm tra lại cuối mỗi vòng

    SCHEDULE_WINDOW_MINUTES = 60  # bài trong lịch bị trễ (máy bận) tối đa ... phút vẫn đăng bù

    # Web quản lý: http://127.0.0.1:5000
    WEB_PORT = 5000

    # Ẩn cửa sổ Chrome khi chạy (True = chạy ngầm hoàn toàn; nên để False lúc mới dùng để quan sát)
    HEADLESS = False

    # Tham gia nhóm: tự động khi quét gặp nhóm chưa tham gia (và lệnh python main.py join)
    AUTO_JOIN = True        # cuối mỗi vòng tự bấm "Tham gia nhóm" các nhóm chưa tham gia
    JOIN_ANSWER = "ok"      # câu trả lời điền vào mọi ô câu hỏi khi tham gia (ô tick thì tick hết)
    JOIN_PER_DAY = 20       # số nhóm tối đa tự bấm Tham gia mỗi ngày
    JOIN_RETRY_DAYS = 1     # tham gia không thành công: ... ngày sau mới thử lại
    JOIN_PER_RUN = 15       # (lệnh join) số nhóm tối đa bấm "Tham gia" mỗi lượt
    CHECK_PER_RUN = 40      # (lệnh join) số nhóm tối đa kiểm tra mỗi lượt
    JOIN_MIN_DELAY = 60     # chờ sau mỗi lần bấm Tham gia (giây)
    JOIN_MAX_DELAY = 180

    # Chrome profile (giữ đăng nhập)
    USER_DATA_DIR = os.path.join(BASE_DIR, "chrome_profile")
