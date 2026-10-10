import os
import re
import sys
import json
import time
import schedule
import logging
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from config import Config
from modules.excel_reader import ExcelReader
from modules.image_manager import ImageManager
from modules.poster import FacebookPoster
from modules.commenter import FacebookCommenter
from modules.group_checker import GroupChecker, usable_groups, NOT_JOINED, UNAVAILABLE, PENDING as JOIN_PENDING
from modules.poster import NOT_JOINED_NOTE, UNAVAILABLE_NOTE, SKIP_HOURS
from modules.group_yield import rank_by_yield, posting_order
from modules.group_finder import find_groups, is_hanoi_group, normalize_group_url
from modules.group_lists import load_groups, group_priority, with_hot_groups, with_group_stats
from modules.group_stats import group_info
from modules.intent import classify_intent, load_rules
from modules.products import load_pool, pick_pool
from modules.watcher import GroupWatcher, daily_cap_reached, minutes_to_tomorrow
from modules.db import Database
from modules import browser
from modules.scanner import Scanner
from modules.queue_runner import QueueRunner

# ============ LOGGING ============
os.makedirs(Config.LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(Config.LOG_DIR, 'app.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

db = Database(Config.DB_FILE)


def create_driver(profile=None):
    """Khởi tạo Chrome với profile để giữ đăng nhập (mặc định chrome_profile; cửa sổ quét: SCAN_USER_DATA_DIR)"""
    profile = profile or Config.USER_DATA_DIR
    browser.close_leftover_chrome(profile, logger)
    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--start-maximized")
    # Chạy 3 Chrome cùng lúc: bộ phân giải tên miền riêng của Chrome hay báo ERR_NAME_NOT_RESOLVED (10/10) -> dùng
    # bộ phân giải của Windows (có bộ nhớ đệm chung), không tra trước tên miền của các link trên trang
    options.add_argument("--disable-features=AsyncDns,DnsOverHttps")
    options.add_argument("--dns-prefetch-disable")
    if Config.HEADLESS:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def login_facebook(driver):
    """Đăng nhập (chỉ chạy lần đầu, sau đó profile giữ session)"""
    driver.get("https://www.facebook.com")
    time.sleep(3)

    # Nếu đã đăng nhập, không cần login
    if "login" not in driver.current_url and not driver.find_elements(By.ID, "email"):
        logger.info("✓ Đã đăng nhập sẵn")
        return True

    if not Config.FB_EMAIL or not Config.FB_PASSWORD:
        logger.error("✗ Chưa đăng nhập và thiếu FB_EMAIL/FB_PASSWORD trong .env — hãy chạy: python main.py login")
        return False

    try:
        email_input = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "email"))
        )
        email_input.send_keys(Config.FB_EMAIL)
        driver.find_element(By.ID, "pass").send_keys(Config.FB_PASSWORD)
        driver.find_element(By.NAME, "login").click()
        time.sleep(8)

        if "login" not in driver.current_url:
            logger.info("✓ Đăng nhập thành công")
            return True
        else:
            logger.error("✗ Đăng nhập thất bại (có thể cần xác minh 2FA) — hãy chạy: python main.py login")
            return False
    except Exception as e:
        logger.error(f"Lỗi đăng nhập: {e}")
        return False


# Dòng chứa SĐT (vd 0902 189 751, 0902.189.751, 0902189751) — luôn bị bỏ khỏi bản an toàn
def load_comments_pool(warn=False):
    """Sản phẩm đang bật trên web (tab Sản phẩm) có mẫu bình luận: [{'name', 'image', 'variants'}] (kiểm tra trước vòng)"""
    return load_pool(db, Config, logger if warn else None)


def pick_comments(group=None):
    """Bình luận cho 1 bài: mỗi sản phẩm đang bật chọn ngẫu nhiên 1 mẫu (không trùng trong bài, tránh lặp trong nhóm).
    Trả về [{'text': bản đầy đủ, 'safe_text': bản không SĐT/địa chỉ, 'image', 'name', 'variant_id'}]"""
    return pick_pool(db, Config, group["group_url"] if group else None)


# ============ TASKS ============

def task_manual_login(profile=None):
    """Mở Chrome để tự đăng nhập bằng tay (dùng khi có 2FA / checkpoint). profile: thư mục Chrome (mặc định bình luận)"""
    profile = profile or Config.USER_DATA_DIR
    driver = create_driver(profile)
    try:
        driver.get("https://www.facebook.com")
        input("Đăng nhập Facebook trong cửa sổ Chrome vừa mở, xong thì nhấn Enter tại đây...")
        logger.info(f"✓ Đã lưu phiên đăng nhập vào {os.path.basename(profile)}/")
    finally:
        driver.quit()


def scan_profile(n=1):
    """Thư mục Chrome của cửa sổ quét số n: chrome_profile_quet, chrome_profile_quet2, …"""
    return Config.SCAN_USER_DATA_DIR + ("" if n == 1 else str(n))


def task_make_scan_profile():
    """Tạo Chrome cho SCAN_WINDOWS cửa sổ QUÉT: chép phiên đăng nhập từ chrome_profile (khỏi đăng nhập lại).
    Cửa sổ bình luận (Chrome dùng chrome_profile) và các cửa sổ quét phải đang tắt"""
    if browser.profile_in_use(Config.USER_DATA_DIR):
        logger.error("✗ Chrome của bot đang chạy — đóng cửa sổ \"QC-Facebook\" trước rồi chạy lại lệnh này")
        return False
    ok = True
    for n in range(1, Config.SCAN_WINDOWS + 1):
        profile = scan_profile(n)
        if browser.profile_in_use(profile):
            logger.error(f"✗ Cửa sổ quét {n} đang chạy — đóng cửa sổ \"QC-Facebook Quet\" trước rồi chạy lại lệnh này")
            ok = False
            continue
        logger.info(f"Đang chép phiên đăng nhập sang {os.path.basename(profile)}/ …")
        browser.copy_profile(Config.USER_DATA_DIR, profile)
        driver = create_driver(profile)
        try:
            logged_in = login_facebook(driver)
        finally:
            driver.quit()
        if logged_in:
            logger.info(f"✓ Cửa sổ quét {n} đã đăng nhập Facebook")
        else:
            logger.error(f"✗ Cửa sổ quét {n}: chép xong nhưng chưa đăng nhập được — chạy: python main.py login quet {n}")
            ok = False
    if ok:
        logger.info("✓ Xong — bấm đúp chay-ngam.bat để chạy song song")
    return ok


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_post_history():
    """{group_url: 'YYYY-MM-DD'} — ngày đăng gần nhất của từng nhóm"""
    return load_json(Config.POST_HISTORY_FILE)


def save_post_history(history):
    save_json(Config.POST_HISTORY_FILE, history)


def load_target_groups():
    """Nhóm dùng để đăng/comment: gộp các danh sách nhóm đang bật trên web (tab Danh sách nhóm),
    bỏ nhóm có use ≠ 'có' trong group_status.xlsx, xếp theo ưu tiên (số thành viên / bài mỗi ngày đọc ở trang Giới
    thiệu nhóm nếu đã có); nhóm tương tác cao (HOT_GROUPS) đứng đầu, rồi nhóm có nhiều bài cần mua (YIELD_DAYS ngày)"""
    groups = with_group_stats(usable_groups(load_groups(db, Config), Config.STATUS_FILE), db)
    groups = with_hot_groups(group_priority(groups, Config), db, Config)
    return rank_by_yield(groups, db.group_yields(Config.YIELD_DAYS), Config)


def maybe_find_groups(driver, force=False):
    """Tìm nhóm mới theo từ khóa, GROUP_SEARCH_EVERY_HOURS giờ 1 lần (lưu groups_found.xlsx)"""
    last = db.get_setting("groups_searched_at")
    if not force and last and datetime.now() - datetime.strptime(last, "%Y-%m-%d %H:%M:%S") \
            < timedelta(hours=Config.GROUP_SEARCH_EVERY_HOURS):
        return
    logger.info("=== TÌM NHÓM MỚI THEO TỪ KHÓA ===")
    set_progress(phase="Tìm nhóm mới theo từ khóa", step="Tìm trên Facebook theo GROUP_SEARCH_QUERIES",
                 post_text="", post_url="")
    try:
        # + nhóm bạn đã xóa khỏi danh sách tự tìm trên web: không thêm lại
        known = [g['group_url'] for g in load_groups(db, Config, enabled_only=False)] + list(db.removed_urls())
        n = find_groups(driver, Config, logger, known)
        db.set_setting("groups_searched_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logger.info(f"Đã thêm {n} nhóm mới vào groups_found.xlsx — vòng sau tự tham gia & bình luận")
    except Exception as e:
        logger.error(f"Lỗi tìm nhóm mới: {e}")


def task_find_groups():
    driver = create_driver()
    try:
        if login_facebook(driver):
            maybe_find_groups(driver, force=True)
    finally:
        driver.quit()


def task_join_groups():
    """Kiểm tra trạng thái thành viên, lưu nội quy và bấm Tham gia (có giới hạn)"""
    logger.info("=== BẮT ĐẦU TASK THAM GIA NHÓM ===")
    driver = create_driver()
    try:
        if not login_facebook(driver):
            return
        groups = ExcelReader.read_groups(Config.GROUPS_FILE)
        GroupChecker(driver, Config, logger).run(groups, Config.STATUS_FILE)
    except Exception as e:
        logger.error(f"Lỗi task tham gia nhóm: {e}")
    finally:
        driver.quit()


def task_scheduled_post(force=False, test_groups=None, driver=None):
    """Task 1: Đăng bài theo lịch từ Excel
    force=True: đăng ngay tất cả các dòng trong lịch, bỏ qua cột time
    test_groups: chạy thử — chỉ đăng bài đầu tiên trong lịch,
                 vào N nhóm ngẫu nhiên (số) hoặc vào đúng 1 nhóm (link)
    driver: dùng Chrome đang mở (đang trong vòng bình luận) thay vì mở Chrome mới
    """
    if not force and db.is_paused():
        return
    schedule_data = ExcelReader.read_schedule(Config.SCHEDULE_FILE)
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    done = load_json(Config.SCHEDULE_DONE_FILE)

    def is_due(item):
        """Đến giờ (hoặc trễ tối đa SCHEDULE_WINDOW_MINUTES do máy bận) và hôm nay chưa đăng"""
        t = str(item.get('time', ''))[:5]
        try:
            hh, mm = map(int, t.split(':'))
        except ValueError:
            return False
        late = (now - now.replace(hour=hh, minute=mm, second=0, microsecond=0)).total_seconds() / 60
        return 0 <= late <= Config.SCHEDULE_WINDOW_MINUTES and done.get(f"{today} {t}") is None

    # Lọc các bài đến giờ đăng — chỉ mở Chrome khi thực sự có bài cần đăng
    due_items = [item for item in schedule_data if force or is_due(item)]
    if test_groups:
        due_items = due_items[:1]
    if not due_items:
        return
    if not force:
        for item in due_items:
            done[f"{today} {str(item.get('time', ''))[:5]}"] = now.strftime("%H:%M")
        done = {k: v for k, v in done.items() if k.startswith(today)}
        save_json(Config.SCHEDULE_DONE_FILE, done)

    logger.info("=== BẮT ĐẦU TASK ĐĂNG BÀI THEO LỊCH ===")
    set_progress(step=f"Đăng bài theo lịch ({len(due_items)} bài đến giờ)")
    own = driver is None
    if own:
        driver = create_driver()
    try:
        if own and not login_facebook(driver):
            return

        single_url = isinstance(test_groups, str)
        if single_url:
            groups = [{'group_url': test_groups}]
            test_groups = 1
        else:
            # bỏ nhóm đã biết là không đăng được: chưa tham gia / chờ duyệt tham gia / không xem được nhóm /
            # nhóm chỉ cho đăng tin bán / đầy bài chờ duyệt (đăng chắc chắn hỏng, tốn thời gian mỗi nhóm)
            joins, skips = db.join_statuses(), db.posting_skips()
            all_groups = load_target_groups()
            groups = [g for g in all_groups if joins.get(g['group_url']) not in (NOT_JOINED, JOIN_PENDING, UNAVAILABLE)
                      and g['group_url'] not in skips]
            if len(groups) < len(all_groups):
                logger.info(f"Bỏ qua {len(all_groups) - len(groups)} nhóm không đăng được "
                            "(chưa tham gia / không xem được / chỉ cho đăng tin bán / đầy bài chờ duyệt)")
        history = load_post_history()
        img_mgr = ImageManager(Config.IMAGE_DIR)
        poster = FacebookPoster(driver, Config)
        yields = db.group_yields(Config.YIELD_DAYS)

        def remember(group, ok, note):
            """Nhóm không đăng được vì lý do của nhóm: lần sau bỏ qua (tới khi tham gia được / hết hạn)"""
            url, name = group['group_url'], group.get('group_name', '')
            if note == NOT_JOINED_NOTE:
                db.set_join(url, name, NOT_JOINED, "phát hiện khi đăng bài")
            elif note == UNAVAILABLE_NOTE:
                db.set_join(url, name, UNAVAILABLE, note)
            elif note in SKIP_HOURS:
                db.skip_posting(url, name, note, SKIP_HOURS[note])

        for item in due_items:
            content = item.get('content', '')
            image_name = item.get('image') or None
            category = item.get('group_category')

            image_path = img_mgr.get_image(image_name)

            # Lọc nhóm theo category, bỏ nhóm đã đăng hôm nay (tối đa 1 bài/nhóm/ngày)
            target_groups = ExcelReader.get_groups_by_category(groups, category) \
                            if category and not single_url else list(groups)
            target_groups = [g for g in target_groups if history.get(g['group_url']) != today]
            # Nhóm có nhiều bài cần mua trước (khách đang tìm ở đó), còn lại xáo trộn
            # (post_batch chỉ đăng MAX_POSTS_PER_DAY nhóm đầu)
            target_groups = posting_order(target_groups, yields)
            if test_groups:
                target_groups = target_groups[:test_groups]

            if not target_groups:
                logger.info("Không còn nhóm nào để đăng (chưa tham gia / đã đăng hôm nay / use ≠ 'có')")
                continue

            logger.info(f"Đăng tối đa {Config.MAX_POSTS_PER_DAY}/{len(target_groups)} nhóm | Ảnh: {image_path}")
            results = poster.post_batch(target_groups, content, image_path, on_result=remember)
            for r in results:
                if r['success']:
                    history[r['group']] = today
            save_post_history(history)
            ok = sum(r['success'] for r in results)
            logger.info(f"Kết quả: {ok}/{len(results)} nhóm thành công")

    except Exception as e:
        logger.error(f"Lỗi task đăng bài: {e}")
    finally:
        if own:
            driver.quit()


def task_test_comment(post_url, number=None):
    """Bình luận tay vào đúng 1 bài viết (kết quả cũng được lưu, xem trên web).
    number: chỉ gửi bình luận của sản phẩm thứ mấy (theo tab Sản phẩm); None = mọi sản phẩm đang bật"""
    pool = pick_comments()
    if number is not None and not 1 <= number <= len(pool):
        logger.error(f"Chỉ có {len(pool)} sản phẩm đang bật, không có số {number}")
        return
    comments = [pool[number - 1]] if number else pool
    if db.has_post(post_url):
        logger.info(f"↷ Bài này đã có trong nhật ký, không bình luận lại: {post_url}")
        return

    driver = create_driver()
    try:
        if not login_facebook(driver):
            return
        commenter = FacebookCommenter(driver, Config)
        watcher = GroupWatcher(driver, Config, logger, db)
        result = watcher.comment_post(commenter, comments, {"group_name": "(chạy tay)", "group_url": ""},
                                      {"url": post_url, "text": "", "age": None})
        if result == "skip":
            logger.info(f"↷ Bài đã có bình luận của bạn, không bình luận thêm: {post_url}")
        else:
            logger.info(f"Kết quả: {result} — {post_url}")
        db.export_excel(Config.COMMENT_LOG_FILE)
        time.sleep(3)  # để Facebook kịp lưu trước khi đóng Chrome
    finally:
        driver.quit()


def task_cleanup(days=3):
    """Mở lại các bài đã bình luận trong ... ngày, xóa mọi bình luận của mình đang bị từ chối"""
    logger.info("=== DỌN BÌNH LUẬN BỊ TỪ CHỐI ===")
    driver = create_driver()
    try:
        if not login_facebook(driver):
            return
        GroupWatcher(driver, Config, logger, db).cleanup(FacebookCommenter(driver, Config), days)
    finally:
        driver.quit()


def post_due(driver):
    """Đăng bài trong lịch nếu đến giờ, dùng Chrome đang mở (gọi xen giữa vòng bình luận)"""
    try:
        task_scheduled_post(driver=driver)
    except Exception as e:
        logger.error(f"Lỗi đăng bài theo lịch: {e}")


def task_watch_groups(dry_run=False, only=None):
    """Task 2: 1 vòng: từng nhóm quét hết bài mới (≤ MAX_POST_AGE_MINUTES) rồi bình luận hết, mỗi bài 3 bình luận
    độc lập kèm ảnh; cuối vòng tự tham gia nhóm chưa tham gia. Bài trong lịch đến giờ được đăng xen giữa (dùng chung Chrome).
    dry_run=True: chạy thử — quét & phân loại, KHÔNG bình luận / tham gia nhóm / đăng bài.
    only: chỉ chạy N nhóm đầu (số) hoặc đúng 1 nhóm (link).
    Trả về số bài đã bình luận, hoặc "blocked" """
    if db.is_paused() and not dry_run:
        logger.info("⏸ Đang tạm dừng (bật lại trên web quản lý) — bỏ qua lượt quét")
        return 0
    set_progress(phase="Chuẩn bị vòng mới", step="Đọc sản phẩm & danh sách nhóm", percent=0)
    comments = load_comments_pool(warn=True)
    if not comments and not dry_run:
        logger.warning("Chưa bật sản phẩm nào để bình luận (web → tab Sản phẩm) — bỏ qua lượt quét")
        return 0
    logger.info(f"=== BẮT ĐẦU VÒNG QUÉT BÀI MỚI — {len(comments)} sản phẩm: "
                + ", ".join(f"{c['name']} ({c['variants'] or 1} mẫu)" for c in comments) + " ===")
    missing = [c['name'] for c in comments if not c['image']]
    if missing:
        logger.warning(f"Sản phẩm không có ảnh: {', '.join(missing)}")
    groups = load_target_groups()
    if isinstance(only, int):
        groups = groups[:only]
    elif only:
        groups = [{"group_url": normalize_group_url(only), "group_name": ""}]
    if not groups:
        logger.warning("Chưa bật danh sách nhóm nào (web → tab Danh sách nhóm) — bỏ qua lượt quét")
        return 0
    set_progress(step="Mở Chrome & đăng nhập Facebook")
    driver = create_driver()
    try:
        if not login_facebook(driver):
            set_progress(phase="Lỗi", step="Chưa đăng nhập được Facebook — chạy: python main.py login")
            return 0
        logger.info(f"{len(groups)} nhóm, thứ tự ưu tiên: " + " | ".join(g.get('group_name', '')[:25] for g in groups[:5])
                    + (" | …" if len(groups) > 5 else ""))
        commenter = FacebookCommenter(driver, Config)
        # mỗi bài chọn lại mẫu bình luận: bật/tắt/thêm trên web có hiệu lực từ bài tiếp theo
        result = GroupWatcher(driver, Config, logger, db, dry_run=dry_run).run(
            groups, commenter, pick_comments, between=None if dry_run else lambda: post_due(driver))
        if result != "blocked" and not db.is_paused() and not dry_run:
            maybe_find_groups(driver)  # nhóm mới tìm được: vòng sau tự tham gia & bình luận
        return result
    except Exception as e:
        logger.error(f"Lỗi quét bài mới: {e}")
        return 0
    finally:
        driver.quit()


def task_classify(text):
    """In kết quả chấm 1 câu y như bot: MUA / BÁN (từ khóa trong data/tu_khoa_mua_ban.txt trước, chưa chắc thì hỏi
    Gemini nếu bật INTENT_AI), rồi quyết định cuối (chủ đề, khu vực…) khi bài nằm trong nhóm Hà Nội / nhóm toàn quốc"""
    from modules.filters import POST_FILTERS, PostCandidate, run_filters
    from modules.ai_intent import AiIntent
    from modules.engagement import Engagement
    ai = AiIntent(db, Config, logger)
    no_counts = lambda: Engagement(0, 0, 0, known=False)  # câu gõ tay: không có số tương tác
    print(PostCandidate(text, 0, Config, no_counts, ai=ai).intent.reason)
    for label, hanoi in (("Trong nhóm Hà Nội", True), ("Trong nhóm toàn quốc", False)):
        v = run_filters(POST_FILTERS, PostCandidate(text, 0, Config, no_counts, ai=ai, hanoi_group=hanoi), Config)
        print(f"{label}: {'BÌNH LUẬN' if v.ok else 'BỎ QUA'} — {v.reason}")


def task_group_stats():
    """Đọc lại ngay số thành viên / bài mỗi ngày của mọi nhóm đang dùng (bỏ qua cache) và cho biết nhóm nào đạt"""
    from modules.filters import GROUP_FILTERS, run_filters
    groups = load_target_groups()
    driver = create_driver()
    try:
        if not login_facebook(driver):
            return
        for i, g in enumerate(groups, 1):
            stats = group_info(driver, db, Config, {**g, "group_url": normalize_group_url(g["group_url"])}, force=True)
            v = run_filters(GROUP_FILTERS, stats and {**stats, "hanoi": is_hanoi_group(g)}, Config)
            logger.info(f"[{i}/{len(groups)}] {'✓ quét' if v.ok else '✗ bỏ qua'} — {v.reason or 'đạt'} — "
                        f"{stats.get('activity') or ''} — {g.get('group_name') or g['group_url']}")
    finally:
        driver.quit()


# ============ SCHEDULER ============

def set_progress(**fields):
    """Ghi tiến trình cho khung "Tiến trình" trên web (lỗi ghi không ảnh hưởng việc chạy)"""
    try:
        db.set_progress(**fields)
    except Exception:
        pass


def wait_minutes(minutes, phase=None):
    """Chờ ... phút, trong lúc chờ vẫn đăng bài theo lịch nếu đến giờ"""
    end = time.time() + minutes * 60
    if phase:
        set_progress(phase=phase, step="", post_text="", post_url="",
                     next_at=(datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S"))
    while time.time() < end:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error(f"Lỗi đăng bài theo lịch: {e}")
        time.sleep(1)


def blocked_until():
    """Facebook chặn bình luận tới lúc nào (None = không bị chặn)"""
    value = db.get_setting("blocked_until")
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S") if value else None


def _quit(driver):
    try:
        driver.quit()
    except Exception:
        pass  # Chrome đã hỏng / đã đóng


def task_scan(n=1):
    """Cửa sổ QUÉT số n (chạy song song với cửa sổ bình luận, Chrome riêng scan_profile(n)): liên tục tìm bài mới ->
    hàng chờ; các cửa sổ quét chia nhau nhóm (không quét trùng). Chrome hỏng thì tự mở lại"""
    if not Config.PARALLEL:
        logger.info("PARALLEL = False trong config.py — không dùng cửa sổ quét riêng (cửa sổ QC-Facebook tự quét)")
        return
    profile = scan_profile(n)
    if not os.path.isdir(profile):
        logger.error(f"✗ Chưa có Chrome cho cửa sổ quét {n} — đóng cửa sổ \"QC-Facebook\" rồi chạy: "
                     "python main.py taophienquet")
        return
    progress = lambda **fields: db.set_scan_progress(n, **fields)
    progress(started=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), phase="Khởi động")
    logger.info(f"🔎 [Quét {n}] Cửa sổ QUÉT {n}/{Config.SCAN_WINDOWS}: tìm bài mới liên tục (nhóm tương tác cao mỗi "
                f"{Config.HOT_RESCAN_MINUTES} phút), bài đạt điều kiện vào hàng chờ cho cửa sổ bình luận")
    while True:
        driver = None
        try:
            driver = create_driver(profile)
            if not login_facebook(driver):
                progress(phase=f"Chưa đăng nhập Facebook — chạy: python main.py login quet {n}")
                return
            watcher = GroupWatcher(driver, Config, logger, db, progress=progress)
            Scanner(watcher, Config, logger, db, load_target_groups, lambda: daily_cap_reached(db, Config),
                    blocked_until, scanner_id=n).run()
        except Exception:
            logger.exception(f"[Quét {n}] Lỗi — 30 giây sau mở lại Chrome")
            time.sleep(30)
        finally:
            if driver:
                _quit(driver)


def run_queue_scheduler():
    """Chạy song song — cửa sổ BÌNH LUẬN: lấy bài mới nhất trong hàng chờ (cửa sổ QUÉT tìm) bình luận ngay; lúc rảnh
    tham gia nhóm, kiểm tra lại bài cũ, tìm nhóm mới, đăng bài theo lịch. Chrome hỏng thì tự mở lại"""
    logger.info("🚀 Cửa sổ BÌNH LUẬN (chạy song song): bài mới nhất trong hàng chờ được bình luận ngay — cửa sổ "
                "\"QC-Facebook Quet\" lo tìm bài (Ctrl+C để dừng)")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    set_progress(reset=True, pid=os.getpid(), started=now, round_started=now, phase="Khởi động", group_total=0)
    if db.fix_interrupted():
        logger.info("↻ Bài bị bỏ dở lần trước (script bị tắt giữa chừng) sẽ được bình luận lại")
    if db.requeue_interrupted():
        logger.info("↻ Bài đang bình luận dở trong hàng chờ được trả lại hàng chờ")
    while True:
        driver = None
        try:
            driver = create_driver()
            if not login_facebook(driver):
                set_progress(phase="Lỗi", step="Chưa đăng nhập Facebook — chạy: python main.py login")
                time.sleep(300)
                continue
            commenter = FacebookCommenter(driver, Config)
            runner = QueueRunner(GroupWatcher(driver, Config, logger, db), commenter, pick_comments, Config, logger, db,
                                 between=lambda: post_due(driver),
                                 housekeeping_extra=lambda: maybe_find_groups(driver))
            while True:
                runner.step(lambda: daily_cap_reached(db, Config), blocked_until, minutes_to_tomorrow)
        except Exception:
            logger.exception("Lỗi trong cửa sổ bình luận — 1 phút sau mở lại Chrome")
            time.sleep(60)
        finally:
            if driver:
                _quit(driver)


def run_scheduler():
    """Chạy nền liên tục: vòng quét & bình luận nối tiếp nhau (không có bài mới thì chờ ROUND_IDLE_MINUTES phút),
    bài trong lịch đăng được đăng khi đến giờ (xen giữa các bài bình luận).
    Đủ MAX_COMMENTED_POSTS_PER_DAY bài -> nghỉ tới 0 giờ (không mở Chrome), vẫn đăng bài theo lịch.
    PARALLEL = True (và đã có Chrome cửa sổ quét): chạy song song — xem run_queue_scheduler"""
    if Config.PARALLEL:
        if os.path.isdir(Config.SCAN_USER_DATA_DIR):
            return run_queue_scheduler()
        logger.warning("⚠ PARALLEL = True nhưng chưa có Chrome cho cửa sổ quét — tạm chạy cách cũ (1 cửa sổ tự quét). "
                       "Đóng cửa sổ này rồi chạy: python main.py taophienquet")
    schedule.every(1).minutes.at(":00").do(task_scheduled_post)  # dùng khi đang chờ giữa 2 vòng

    logger.info(f"🚀 Đang chạy nền liên tục: từng nhóm bình luận hết bài mới (≤ {Config.MAX_POST_AGE_MINUTES // 60} giờ), "
                f"cuối vòng tự tham gia nhóm, rồi quét lại ngay (Ctrl+C để dừng)")
    set_progress(reset=True, pid=os.getpid(), started=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), phase="Khởi động")
    while True:
        try:
            if daily_cap_reached(db, Config):
                cap = Config.MAX_COMMENTED_POSTS_PER_DAY
                logger.info(f"Đủ {cap} bài hôm nay — nghỉ tới 0 giờ (vẫn đăng bài theo lịch)")
                wait_minutes(minutes_to_tomorrow(), f"Đủ {cap} bài hôm nay — nghỉ tới ngày mai")
                continue
            result = task_watch_groups()
        except Exception:  # lỗi bất ngờ (đọc file, CSDL, Chrome…) không được làm dừng chạy nền
            logger.exception("Lỗi không mong muốn trong vòng quét — 2 phút sau chạy lại")
            wait_minutes(2, "Gặp lỗi — chờ chạy lại vòng quét")
            continue
        if result == "blocked":
            logger.info("Đang bị Facebook chặn — 30 phút sau kiểm tra lại")
            wait_minutes(30, "Bị Facebook chặn — chờ kiểm tra lại")
        elif db.is_paused():
            wait_minutes(1, "Tạm dừng từ web")
        elif not result:
            logger.info(f"Vòng này không bình luận được bài nào — chờ {Config.ROUND_IDLE_MINUTES} phút rồi quét lại")
            wait_minutes(Config.ROUND_IDLE_MINUTES, "Chờ vòng sau (vòng vừa rồi không có bài mới)")
        else:
            logger.info("Xong vòng — quét lại các nhóm ngay để tìm bài mới")
            wait_minutes(0.5, "Xong vòng — sắp quét lại")


USAGE = """Cách dùng:
  python main.py            Chạy nền liên tục. PARALLEL = True: cửa sổ BÌNH LUẬN — bình luận ngay bài mới nhất trong
                            hàng chờ; cách cũ: từng nhóm quét rồi bình luận hết bài mới (≤ 6 giờ). Đăng theo lịch
  python main.py quet [2]   Cửa sổ QUÉT số 1 / 2 (chạy song song, Chrome riêng): tìm bài mới liên tục -> hàng chờ
  python main.py taophienquet   Tạo Chrome cho cửa sổ quét (chép phiên đăng nhập; tắt cửa sổ QC-Facebook trước)
  python main.py login quet [2] Đăng nhập tay cho Chrome của cửa sổ quét số 1 / 2 (nếu taophienquet báo chưa đăng nhập được)
  python main.py watch      Chạy đúng 1 vòng: từng nhóm quét & bình luận hết bài mới, cuối vòng tự tham gia nhóm
  python web.py             Mở web quản lý: http://127.0.0.1:5000
  python main.py login      Mở Chrome để đăng nhập thủ công lần đầu
  python main.py join       Kiểm tra/tham gia nhóm + lưu nội quy (khi chạy nền script cũng tự tham gia)
  python main.py findgroups Tìm nhóm mới theo từ khóa (GROUP_SEARCH_QUERIES) -> data/groups_found.xlsx
  python main.py test [N]   Đăng thử bài đầu tiên trong lịch vào N nhóm (mặc định 1)
  python main.py test URL   Đăng thử bài đầu tiên trong lịch vào đúng nhóm có link URL
  python main.py post       Đăng ngay tất cả bài trong schedule.xlsx (bỏ qua giờ)
  python main.py testcomment URL [SỐ]   Gửi cả 3 bình luận vào đúng 1 bài (SỐ = chỉ gửi bình luận thứ mấy)
  python main.py cleanup [N]  Xóa mọi bình luận bị từ chối trên các bài đã bình luận trong N ngày (mặc định 3)
  python main.py thuquet [N|URL]  CHẠY THỬ: quét & phân loại N nhóm đầu (hoặc 1 nhóm), KHÔNG bình luận — xem kết quả
                                  trên web, tab "Phân loại bài"
  python main.py phanloai "nội dung bài"   Xem 1 câu được chấm MUA / BÁN / KHÔNG XÁC ĐỊNH (thử từ khóa)
  python main.py capnhatnhom  Đọc lại ngay số thành viên của mọi nhóm (bình thường tự đọc lại sau 24 giờ)
"""


if __name__ == "__main__":
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    os.makedirs(Config.IMAGE_DIR, exist_ok=True)

    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "run":
        try:
            run_scheduler()
        finally:
            set_progress(phase="Đã tắt", step="", pid=None)
    elif mode == "login":
        n = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 1
        task_manual_login(scan_profile(n) if sys.argv[2:3] == ["quet"] else None)
    elif mode == "quet":
        n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 1
        try:
            task_scan(n)
        finally:
            db.set_scan_progress(n, phase="Đã tắt", step="", group_name="")
    elif mode == "taophienquet":
        task_make_scan_profile()
    elif mode == "join":
        task_join_groups()
    elif mode == "test":
        arg = sys.argv[2] if len(sys.argv) > 2 else "1"
        task_scheduled_post(force=True, test_groups=int(arg) if arg.isdigit() else arg)
    elif mode == "post":
        task_scheduled_post(force=True)
    elif mode in ("watch", "comment"):
        task_watch_groups()
    elif mode == "findgroups":
        task_find_groups()
    elif mode == "cleanup":
        task_cleanup(int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    elif mode == "testcomment" and len(sys.argv) > 2:
        task_test_comment(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else None)
    elif mode == "thuquet":
        arg = sys.argv[2] if len(sys.argv) > 2 else ""
        task_watch_groups(dry_run=True, only=int(arg) if arg.isdigit() else (arg or None))
    elif mode == "phanloai" and len(sys.argv) > 2:
        task_classify(" ".join(sys.argv[2:]))
    elif mode == "capnhatnhom":
        task_group_stats()
    else:
        print(USAGE)
