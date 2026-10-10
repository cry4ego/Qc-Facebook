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
    # (08/10: tập trung nhóm MÀN HÌNH ở Hà Nội — nhóm tên có "màn hình", hoặc chợ máy tính Hà Nội)
    GROUP_KEYWORDS = ["màn hình", "Hà Nội", "màn hình cũ", "thanh lý màn hình", "mua bán màn hình"]
    GROUP_SEARCH_QUERIES = ["màn hình máy tính Hà Nội", "mua bán màn hình Hà Nội", "màn hình cũ Hà Nội",
                            "thanh lý màn hình Hà Nội", "chợ màn hình máy tính Hà Nội", "màn hình Hà Nội",
                            "mua bán màn hình máy tính cũ"]
    GROUP_SEARCH_EVERY_HOURS = 24     # bao lâu tìm nhóm mới 1 lần (cuối vòng quét)
    MIN_GROUP_MEMBERS = 5000          # tìm nhóm mới: bỏ nhóm ít hơn ... thành viên (để bằng GROUP_MIN_MEMBERS bên dưới;
                                      # nhóm Hà Nội dùng GROUP_MIN_MEMBERS_HANOI)
    MAX_FOUND_GROUPS = 30             # giữ tối đa ... nhóm tự tìm (Hà Nội & đông thành viên trước)

    # Giới hạn hành động
    MIN_DELAY = 30          # chờ giữa 2 bài (đăng hoặc bình luận), giây
    MAX_DELAY = 120
    MAX_POSTS_PER_DAY = 10  # số nhóm tối đa cho mỗi bài trong lịch đăng

    # Theo dõi bài mới & tự bình luận (chạy liên tục: từng nhóm quét hết bài mới -> bình luận hết -> sang nhóm sau;
    # hết nhóm thì tự tham gia các nhóm chưa tham gia, rồi quét lại từ đầu)
    # chỉ bình luận bài đăng trong vòng 6 giờ: bài cũ hơn thường đã có nhiều shop trả lời -> để dành lượt/ngày cho bài mới
    MAX_POST_AGE_MINUTES = 6 * 60
    MAX_POSTS_PER_GROUP = 0           # mỗi vòng 1 nhóm tối đa ... bài; 0 = không giới hạn (bình luận hết)
    # chủ đề được bình luận: chủ shop chỉ muốn bài TÌM MÀN HÌNH (08/10: bỏ bài tìm PC / linh kiện lẻ — SSD, VGA, CPU…).
    # Bài build PC có kèm màn hình vẫn tính là "Màn hình". Thêm "PC" / "Laptop" nếu muốn; [] = mọi bài
    COMMENT_TOPICS = ["Màn hình"]
    MAX_COMMENTED_POSTS_PER_DAY = 40  # giới hạn số bài/ngày (05/10 bị chặn sau 121 bài); 0 = không giới hạn
    ROUND_IDLE_MINUTES = 5            # vòng quét không có bài mới -> chờ ... phút rồi quét lại
    WATCH_SCROLLS = 60                # số lần cuộn tối đa mỗi nhóm (dừng sớm khi gặp bài cũ hơn MAX_POST_AGE_MINUTES)
    COMMENT_GAP_MIN = 15              # chờ giữa 3 bình luận trong cùng 1 bài, giây
    COMMENT_GAP_MAX = 40
    BLOCK_COOLDOWN_HOURS = 6          # Facebook báo chặn -> ngừng tự bình luận trong ... giờ
    VERIFY_AFTER_MINUTES = 60         # sau ... phút mở lại bài kiểm tra bình luận còn hay bị xóa
    VERIFY_PER_RUN = 40               # số bài kiểm tra lại cuối mỗi vòng

    # Nhóm tương tác cao: luôn quét đầu vòng, rồi cứ HOT_RESCAN_MINUTES phút quét lại 1 lần (xen giữa các nhóm/bài
    # khác) để bình luận sớm bài mới. Không cần có trong danh sách nhóm trên web. Chưa tham gia thì tự tham gia ngay.
    HOT_GROUPS = [
        "https://www.facebook.com/groups/manhinhmaytinh/",
        "https://www.facebook.com/groups/760589759199370/",
    ]
    HOT_RESCAN_MINUTES = 2            # bài cần mua: phát hiện & bình luận càng sớm càng tốt

    # ===== Chạy song song (10/10): cửa sổ QUÉT (python main.py quet) tìm bài -> hàng chờ; cửa sổ BÌNH LUẬN
    # (python main.py) lấy bài MỚI NHẤT trong hàng chờ bình luận ngay. chay-ngam.bat mở cả 2 =====
    PARALLEL = True                   # False = cách cũ: 1 cửa sổ tự quét từng nhóm rồi bình luận
    SCAN_USER_DATA_DIR = os.path.join(BASE_DIR, "chrome_profile_quet")  # Chrome của cửa sổ quét (python main.py taophienquet)
    SCAN_WINDOWS = 2                  # số cửa sổ QUÉT chạy cùng lúc (chia nhau các nhóm, không quét trùng); cửa sổ thứ 2
                                      # dùng Chrome chrome_profile_quet2
    SCAN_ACTIVE_MINUTES = 5           # nhóm có khách tìm màn hình / nhiều bài mỗi ngày: quét lại mỗi ... phút
    SCAN_ACTIVE_POSTS_PER_DAY = 100   # nhóm có từ ... bài mới/ngày (trang Giới thiệu) tính là nhóm hoạt động mạnh
    SCAN_OVERLAP_MINUTES = 10         # quét lại chỉ xét bài đăng sau lần quét trước + ... phút dự phòng (nên quét rất nhanh)
    SCAN_PAUSE_SECONDS = (3, 8)       # nghỉ ngẫu nhiên giữa 2 lần quét nhóm (giây)
    QUEUE_IDLE_SECONDS = 15           # hàng chờ trống: ... giây sau xem lại
    QUEUE_HOUSEKEEP_MINUTES = 30      # lúc rảnh, cứ ... phút tự tham gia nhóm chưa vào + kiểm tra lại bài đã bình luận 1 lần
    QUEUE_HOUSEKEEP_VERIFY = 5        # ... mỗi lần chỉ kiểm tra lại ... bài
    QUEUE_HOUSEKEEP_JOINS = 2         # ... và tham gia tối đa ... nhóm (để bài mới không phải chờ lâu)

    # ===== Lọc nhóm theo chất lượng (đọc ở trang Giới thiệu của nhóm, lưu trong CSDL) =====
    GROUP_MIN_MEMBERS = 5000          # chỉ quét nhóm có từ ... thành viên (không đọc được số thành viên = bỏ qua nhóm)
    # nhóm Hà Nội (tên có "Hà Nội"/"HN" hoặc cột khu vực = Hà Nội): nhỏ nhưng đúng khách -> chỉ cần từ ... thành viên
    # (10/10: chủ shop cho quét nhóm Hà Nội từ ~500; nhóm toàn quốc giữ GROUP_MIN_MEMBERS). Tìm nhóm mới cũng dùng mức này
    GROUP_MIN_MEMBERS_HANOI = 500
    GROUP_MIN_POSTS_PER_DAY = 0       # chỉ quét nhóm có từ ... bài mới mỗi ngày; 0 = không xét tiêu chí này
    GROUP_STATS_CACHE_HOURS = 24      # số thành viên đọc được dùng lại ... giờ rồi mới đọc lại
    GROUP_STATS_RETRY_MINUTES = 10    # trang Giới thiệu không thấy số thành viên -> ... phút sau đọc lại
    GROUP_SCAN_MAX_SECONDS = 45       # quét bảng tin 1 nhóm tối đa ... giây (bài mới nhất được xét trước)

    # ===== Xoay vòng nhóm theo số bài cần mua tìm được (để lần lượt quét tới cả các nhóm cuối danh sách) =====
    # Thứ tự quét: nhóm tương tác cao -> nhóm "Ưu tiên" trên web -> nhóm có nhiều bài cần mua -> nhóm chưa quét lần nào
    # -> nhóm đã quét nhiều lần mà không có bài cần mua nào (quét thưa hơn)
    GROUP_RESCAN_MINUTES = 60         # nhóm thường: quét xong thì ... phút sau mới quét lại (nhường lượt cho nhóm khác)
    YIELD_DAYS = 7                    # đếm bài cần mua của mỗi nhóm trong ... ngày gần nhất
    LOW_YIELD_MIN_SCANS = 3           # nhóm quét >= ... lần trong YIELD_DAYS ngày mà 0 bài cần mua = nhóm ít khách
    LOW_YIELD_OBSERVE_HOURS = 24      # ... và đã theo dõi ít nhất ... giờ (quét dày không bị đánh giá vội)
    LOW_YIELD_RESCAN_HOURS = 24       # nhóm ít khách: ... giờ mới quét lại 1 lần
    GROUP_UNAVAILABLE_RETRY_HOURS = 24  # nhóm báo "không xem được nội dung này" (bị chặn?): ... giờ sau mới thử lại

    # ===== Lọc bài viết trước khi bình luận (thứ tự: chủ đề -> ý định MUA/BÁN -> khu vực -> điểm tương tác) =====
    INTENT_FILTER = True              # True = chỉ bình luận bài của người cần MUA; bỏ bài BÁN và bài không rõ ý định
    INTENT_KEYWORDS_FILE = os.path.join(DATA_DIR, "tu_khoa_mua_ban.txt")  # danh sách từ khóa MUA / BÁN (sửa file này)
    INTENT_MIN_SCORE = 3              # bài là MUA khi điểm MUA >= ... và
    INTENT_MARGIN = 2                 # ... hơn điểm BÁN ít nhất ... điểm
    # Khách ghi rõ ở khu vực xa (TP.HCM, miền Nam, miền Trung, tỉnh xa…) mà không nhắc Hà Nội / tỉnh lân cận -> bỏ qua.
    # Bài không ghi khu vực vẫn bình luận. Danh sách tỉnh GẦN / XA sửa trong file REGION_FILE
    REGION_FILTER = True
    REGION_FILE = os.path.join(DATA_DIR, "khu_vuc.txt")
    # Nhóm toàn quốc (tên nhóm không có "Hà Nội", vd MÀN HÌNH MÁY TÍNH): chỉ bình luận bài GHI RÕ Hà Nội / tỉnh lân cận
    # (bài không ghi khu vực ở nhóm toàn quốc ~ một nửa là khách tỉnh xa). Nhóm Hà Nội: bài không ghi khu vực vẫn bình luận.
    # False = nhóm toàn quốc cũng bình luận bài không ghi khu vực
    REGION_REQUIRED_IN_NATIONAL_GROUPS = True
    # Bài người cần MUA thì bình luận CÀNG SỚM CÀNG TỐT, không chờ có like / bình luận (bài mới 0 tương tác là cơ hội
    # tốt nhất — chưa shop nào trả lời) -> 0 = không xét tương tác, cũng không tốn công đọc số tương tác.
    POST_MIN_ENGAGEMENT = 0           # chỉ bình luận bài có điểm tương tác từ ... trở lên; 0 = không xét
    ENGAGEMENT_WEIGHTS = {"reaction": 1, "comment": 2, "share": 3}  # điểm = cảm xúc x1 + bình luận x2 + chia sẻ x3

    # ===== AI (Gemini): chấm lại bài mà từ khóa chưa đủ chắc (KHÔNG XÁC ĐỊNH) =====
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # đặt trong file .env (KHÔNG ghi khóa vào file này)
    INTENT_AI = True                  # True = bài KHÔNG XÁC ĐỊNH theo từ khóa thì hỏi Gemini MUA hay BÁN (cần GEMINI_API_KEY)
    GEMINI_MODEL = "gemini-flash-lite-latest"   # model nhanh, rẻ; tên "latest" tự dùng bản mới nhất
    GEMINI_MAX_CALLS_PER_DAY = 500    # tối đa ... lần hỏi Gemini mỗi ngày (mỗi nội dung chỉ hỏi 1 lần, có lưu lại)

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
