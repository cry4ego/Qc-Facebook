import os
import re
import sys
import json
import time
import random
import psutil
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
from modules.group_checker import GroupChecker, usable_groups
from modules.group_finder import find_groups
from modules.group_lists import load_groups, group_priority
from modules.products import load_pool, pick_pool
from modules.watcher import GroupWatcher
from modules.db import Database

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


def close_leftover_chrome():
    """Tắt Chrome còn sót từ lần chạy trước (vd bị Ctrl+C) đang giữ chrome_profile.
    Chỉ tắt tiến trình dùng đúng profile của script, không đụng Chrome cá nhân."""
    profile = os.path.normcase(Config.USER_DATA_DIR)
    killed = 0
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            if (proc.info['name'] or '').lower() != 'chrome.exe':
                continue
            if profile in os.path.normcase(' '.join(proc.info['cmdline'] or [])):
                proc.kill()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed:
        logger.info(f"Đã đóng {killed} tiến trình Chrome còn sót từ lần chạy trước")
        time.sleep(2)


def create_driver():
    """Khởi tạo Chrome với profile để giữ đăng nhập"""
    close_leftover_chrome()
    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={Config.USER_DATA_DIR}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--start-maximized")
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

def task_manual_login():
    """Mở Chrome để tự đăng nhập bằng tay (dùng khi có 2FA / checkpoint)"""
    driver = create_driver()
    try:
        driver.get("https://www.facebook.com")
        input("Đăng nhập Facebook trong cửa sổ Chrome vừa mở, xong thì nhấn Enter tại đây...")
        logger.info("✓ Đã lưu phiên đăng nhập vào chrome_profile/")
    finally:
        driver.quit()


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
    bỏ nhóm có use ≠ 'có' trong group_status.xlsx, xếp theo ưu tiên"""
    return group_priority(usable_groups(load_groups(db, Config), Config.STATUS_FILE), Config)


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
            groups = load_target_groups()
        history = load_post_history()
        img_mgr = ImageManager(Config.IMAGE_DIR)
        poster = FacebookPoster(driver, Config)

        for item in due_items:
            content = item.get('content', '')
            image_name = item.get('image') or None
            category = item.get('group_category')

            image_path = img_mgr.get_image(image_name)

            # Lọc nhóm theo category, bỏ nhóm đã đăng hôm nay (tối đa 1 bài/nhóm/ngày)
            target_groups = ExcelReader.get_groups_by_category(groups, category) \
                            if category and not single_url else list(groups)
            target_groups = [g for g in target_groups if history.get(g['group_url']) != today]
            # Xáo trộn để mỗi lượt đăng vào các nhóm khác nhau (post_batch chỉ đăng MAX_POSTS_PER_DAY nhóm đầu)
            random.shuffle(target_groups)
            if test_groups:
                target_groups = target_groups[:test_groups]

            if not target_groups:
                logger.info("Không còn nhóm nào để đăng (chưa tham gia / đã đăng hôm nay / use ≠ 'có')")
                continue

            logger.info(f"Đăng {len(target_groups)} nhóm | Ảnh: {image_path}")
            results = poster.post_batch(target_groups, content, image_path)
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


def task_watch_groups():
    """Task 2: 1 vòng: từng nhóm quét hết bài mới (≤ MAX_POST_AGE_MINUTES) rồi bình luận hết, mỗi bài 3 bình luận
    độc lập kèm ảnh; cuối vòng tự tham gia nhóm chưa tham gia. Bài trong lịch đến giờ được đăng xen giữa (dùng chung Chrome).
    Trả về số bài đã bình luận, hoặc "blocked" """
    if db.is_paused():
        logger.info("⏸ Đang tạm dừng (bật lại trên web quản lý) — bỏ qua lượt quét")
        return 0
    set_progress(phase="Chuẩn bị vòng mới", step="Đọc sản phẩm & danh sách nhóm", percent=0)
    comments = load_comments_pool(warn=True)
    if not comments:
        logger.warning("Chưa bật sản phẩm nào để bình luận (web → tab Sản phẩm) — bỏ qua lượt quét")
        return 0
    logger.info(f"=== BẮT ĐẦU VÒNG QUÉT BÀI MỚI — {len(comments)} sản phẩm: "
                + ", ".join(f"{c['name']} ({c['variants'] or 1} mẫu)" for c in comments) + " ===")
    missing = [c['name'] for c in comments if not c['image']]
    if missing:
        logger.warning(f"Sản phẩm không có ảnh: {', '.join(missing)}")
    groups = load_target_groups()
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
        result = GroupWatcher(driver, Config, logger, db).run(
            groups, commenter, pick_comments, between=lambda: post_due(driver))
        if result != "blocked" and not db.is_paused():
            maybe_find_groups(driver)  # nhóm mới tìm được: vòng sau tự tham gia & bình luận
        return result
    except Exception as e:
        logger.error(f"Lỗi quét bài mới: {e}")
        return 0
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
        schedule.run_pending()
        time.sleep(1)


def run_scheduler():
    """Chạy nền liên tục: vòng quét & bình luận nối tiếp nhau (không có bài mới thì chờ ROUND_IDLE_MINUTES phút),
    bài trong lịch đăng được đăng khi đến giờ (xen giữa các bài bình luận)"""
    schedule.every(1).minutes.at(":00").do(task_scheduled_post)  # dùng khi đang chờ giữa 2 vòng

    logger.info(f"🚀 Đang chạy nền liên tục: từng nhóm bình luận hết bài mới (≤ {Config.MAX_POST_AGE_MINUTES // 60} giờ), "
                f"cuối vòng tự tham gia nhóm, rồi quét lại ngay (Ctrl+C để dừng)")
    set_progress(reset=True, pid=os.getpid(), started=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), phase="Khởi động")
    while True:
        result = task_watch_groups()
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
  python main.py            Chạy nền liên tục: từng nhóm bình luận hết bài mới (≤ 24 giờ), tự tham gia nhóm, quét lại; đăng theo lịch
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
        task_manual_login()
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
    else:
        print(USAGE)
