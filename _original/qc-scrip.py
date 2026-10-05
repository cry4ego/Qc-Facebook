Script Tự động hóa Facebook với 3 tính năng chính
Tôi sẽ giúp bạn xây dựng script Python với 3 tính năng bạn yêu cầu. Lưu ý quan trọng trước khi bắt đầu:

⚠️ Cảnh báo pháp lý & chính sách:

Việc tự động đăng bài/comment hàng loạt vi phạm Điều khoản dịch vụ của Facebook, có thể dẫn đến khóa tài khoản vĩnh viễn

Spam comment quảng cáo có thể vi phạm pháp luật về quảng cáo

Nên dùng cho mục đích học tập/nghiên cứu, không nên chạy production với tài khoản chính

📋 Kiến trúc tổng thể
text
facebook_automation/
├── config.py              # Cấu hình
├── main.py                # Entry point
├── modules/
│   ├── poster.py          # Đăng bài theo lịch
│   ├── commenter.py       # Auto comment
│   ├── image_manager.py   # Quản lý ảnh
│   └── excel_reader.py    # Đọc file Excel
├── data/
│   ├── groups.xlsx        # Danh sách nhóm
│   ├── schedule.xlsx      # Lịch đăng bài
│   ├── comments.txt       # Nội dung comment
│   └── images/            # Ảnh sản phẩm
├── logs/
└── requirements.txt
1️⃣ Cài đặt môi trường
requirements.txt

txt
selenium==4.15.0
webdriver-manager==4.0.1
pandas==2.1.3
openpyxl==3.1.2
schedule==1.2.0
python-dotenv==1.0.0
Pillow==10.1.0
Cài đặt:

bash
pip install -r requirements.txt
2️⃣ File cấu hình config.py
python
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
    SCHEDULE_FILE = os.path.join(DATA_DIR, "schedule.xlsx")
    COMMENTS_FILE = os.path.join(DATA_DIR, "comments.txt")
    
    # Cấu hình chống detect
    MIN_DELAY = 30          # delay tối thiểu giữa các action (giây)
    MAX_DELAY = 120         # delay tối đa
    MAX_POSTS_PER_DAY = 10  # giới hạn bài/ngày
    MAX_COMMENTS_PER_DAY = 30
    
    # Chrome profile (giữ đăng nhập)
    USER_DATA_DIR = os.path.join(BASE_DIR, "chrome_profile")
.env (tạo file này, KHÔNG commit lên git)

text
FB_EMAIL=your_email@gmail.com
FB_PASSWORD=your_password
3️⃣ Đọc file Excel modules/excel_reader.py
Cấu trúc groups.xlsx:

group_url	group_name	category
https://facebook.com/groups/123	Nhóm ABC	Điện tử
https://facebook.com/groups/456	Nhóm XYZ	Gia dụng
Cấu trúc schedule.xlsx:

time	content	image	group_category
08:00	Khuyến mãi hôm nay...	sp1.jpg	Điện tử
12:30	Sản phẩm mới...	sp2.jpg	Gia dụng
python
import pandas as pd
import os

class ExcelReader:
    @staticmethod
    def read_groups(file_path):
        """Đọc danh sách nhóm từ Excel"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Không tìm thấy: {file_path}")
        df = pd.read_excel(file_path)
        return df.to_dict('records')
    
    @staticmethod
    def read_schedule(file_path):
        """Đọc lịch đăng bài"""
        df = pd.read_excel(file_path)
        return df.to_dict('records')
    
    @staticmethod
    def get_groups_by_category(groups, category):
        return [g for g in groups if g.get('category') == category]
4️⃣ Module quản lý ảnh modules/image_manager.py
python
import os
import random
from PIL import Image

class ImageManager:
    def __init__(self, image_dir):
        self.image_dir = image_dir
        os.makedirs(image_dir, exist_ok=True)
    
    def get_image(self, filename=None):
        """Lấy đường dẫn ảnh, nếu không chỉ định thì random"""
        if filename:
            path = os.path.join(self.image_dir, filename)
            if os.path.exists(path):
                return path
            return None
        
        images = [f for f in os.listdir(self.image_dir) 
                  if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        if not images:
            return None
        return os.path.join(self.image_dir, random.choice(images))
    
    def optimize_image(self, image_path, max_size=(1200, 1200)):
        """Resize ảnh để upload nhanh hơn"""
        try:
            img = Image.open(image_path)
            img.thumbnail(max_size, Image.LANCZOS)
            optimized_path = image_path.replace('.', '_opt.')
            img.save(optimized_path, optimize=True, quality=85)
            return optimized_path
        except Exception as e:
            print(f"Lỗi xử lý ảnh: {e}")
            return image_path
5️⃣ Module đăng bài modules/poster.py
python
import time
import random
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class FacebookPoster:
    def __init__(self, driver, config):
        self.driver = driver
        self.config = config
    
    def _human_delay(self):
        time.sleep(random.uniform(self.config.MIN_DELAY, self.config.MAX_DELAY))
    
    def _short_delay(self):
        time.sleep(random.uniform(2, 5))
    
    def post_to_group(self, group_url, content, image_path=None):
        """Đăng bài vào 1 group"""
        try:
            print(f"→ Đang đăng vào: {group_url}")
            self.driver.get(group_url)
            self._short_delay()
            
            # Click vào ô "Viết gì đó..." 
            # Selector có thể thay đổi - cần cập nhật
            post_box = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//span[contains(text(), 'Viết gì đó') or contains(text(), 'Write something')]")
                )
            )
            post_box.click()
            self._short_delay()
            
            # Nhập nội dung
            editor = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[@role='textbox' and @contenteditable='true']")
                )
            )
            for char in content:
                editor.send_keys(char)
                time.sleep(random.uniform(0.02, 0.08))  # gõ như người thật
            
            self._short_delay()
            
            # Upload ảnh nếu có
            if image_path and os.path.exists(image_path):
                try:
                    file_input = self.driver.find_element(
                        By.XPATH, "//input[@type='file' and @accept='image/*']"
                    )
                    file_input.send_keys(os.path.abspath(image_path))
                    time.sleep(5)  # chờ ảnh upload
                except Exception as e:
                    print(f"  ⚠ Không upload được ảnh: {e}")
            
            # Click nút Đăng
            post_btn = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//div[@aria-label='Đăng' or @aria-label='Post']")
                )
            )
            post_btn.click()
            
            print(f"  ✓ Đã đăng thành công")
            self._human_delay()
            return True
            
        except Exception as e:
            print(f"  ✗ Lỗi đăng bài: {e}")
            return False
    
    def post_batch(self, groups, content, image_path=None):
        """Đăng hàng loạt với delay ngẫu nhiên"""
        results = []
        for i, group in enumerate(groups):
            if i >= self.config.MAX_POSTS_PER_DAY:
                print(f"Đã đạt giới hạn {self.config.MAX_POSTS_PER_DAY} bài/ngày")
                break
            
            url = group.get('group_url')
            success = self.post_to_group(url, content, image_path)
            results.append({"group": url, "success": success})
            
            if i < len(groups) - 1:
                self._human_delay()
        
        return results
6️⃣ Module auto comment modules/commenter.py
python
import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class FacebookCommenter:
    def __init__(self, driver, config, comments_pool):
        self.driver = driver
        self.config = config
        self.comments_pool = comments_pool
        self.commented_posts = set()  # tránh comment trùng
    
    def _get_random_comment(self):
        return random.choice(self.comments_pool)
    
    def _human_delay(self):
        time.sleep(random.uniform(self.config.MIN_DELAY, self.config.MAX_DELAY))
    
    def comment_on_post(self, post_url, custom_comment=None):
        """Comment vào 1 bài viết cụ thể"""
        try:
            if post_url in self.commented_posts:
                return False
            
            self.driver.get(post_url)
            time.sleep(random.uniform(3, 6))
            
            comment_text = custom_comment or self._get_random_comment()
            
            # Tìm ô comment
            comment_box = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//div[@aria-label='Viết bình luận' or @aria-label='Write a comment']")
                )
            )
            comment_box.click()
            time.sleep(1)
            
            # Nhập comment
            editor = self.driver.switch_to.active_element
            for char in comment_text:
                editor.send_keys(char)
                time.sleep(random.uniform(0.03, 0.1))
            
            time.sleep(1)
            
            # Enter để gửi
            editor.send_keys('\n')
            time.sleep(3)
            
            self.commented_posts.add(post_url)
            print(f"  ✓ Đã comment: {comment_text[:50]}...")
            return True
            
        except Exception as e:
            print(f"  ✗ Lỗi comment: {e}")
            return False
    
    def scan_and_comment(self, group_url, keywords=None, max_comments=5):
        """
        Quét newsfeed 1 group và comment các bài viết
        keywords: chỉ comment bài có chứa từ khóa (None = comment tất cả)
        """
        print(f"→ Quét group: {group_url}")
        self.driver.get(group_url)
        time.sleep(5)
        
        # Scroll để load bài
        for _ in range(3):
            self.driver.execute_script("window.scrollBy(0, 800)")
            time.sleep(2)
        
        # Tìm các bài viết
        posts = self.driver.find_elements(
            By.XPATH, "//div[@role='article']"
        )
        
        commented = 0
        for post in posts[:max_comments * 2]:
            if commented >= max_comments:
                break
            
            try:
                # Lấy link bài viết
                link_el = post.find_element(
                    By.XPATH, ".//a[contains(@href, '/posts/') or contains(@href, 'story_fbid')]"
                )
                post_url = link_el.get_attribute('href')
                
                if post_url in self.commented_posts:
                    continue
                
                # Kiểm tra keyword nếu có
                if keywords:
                    post_text = post.text.lower()
                    if not any(kw.lower() in post_text for kw in keywords):
                        continue
                
                # Click vào bài để mở
                self.driver.get(post_url)
                time.sleep(random.uniform(3, 6))
                
                # Comment
                if self.comment_on_post(post_url):
                    commented += 1
                    self._human_delay()
                    
            except Exception as e:
                continue
        
        return commented
7️⃣ Trình điều khiển chính main.py
python
import os
import time
import random
import schedule
import logging
from datetime import datetime
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

# ============ LOGGING ============
os.makedirs(Config.LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(Config.LOG_DIR, 'app.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def create_driver():
    """Khởi tạo Chrome với profile để giữ đăng nhập"""
    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={Config.USER_DATA_DIR}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--start-maximized")
    
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
    if "login" not in driver.current_url:
        logger.info("✓ Đã đăng nhập sẵn")
        return True
    
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
            logger.error("✗ Đăng nhập thất bại (có thể cần xác minh 2FA)")
            return False
    except Exception as e:
        logger.error(f"Lỗi đăng nhập: {e}")
        return False


def load_comments_pool():
    """Đọc danh sách comment từ file"""
    if not os.path.exists(Config.COMMENTS_FILE):
        return ["Sản phẩm bên mình đang có ưu đãi, ib mình nhé!"]
    
    with open(Config.COMMENTS_FILE, 'r', encoding='utf-8') as f:
        comments = [line.strip() for line in f if line.strip()]
    return comments if comments else ["Sản phẩm bên mình đang có ưu đãi!"]


# ============ TASKS ============

def task_scheduled_post():
    """Task 1: Đăng bài theo lịch từ Excel"""
    logger.info("=== BẮT ĐẦU TASK ĐĂNG BÀI THEO LỊCH ===")
    driver = create_driver()
    try:
        login_facebook(driver)
        
        groups = ExcelReader.read_groups(Config.GROUPS_FILE)
        schedule_data = ExcelReader.read_schedule(Config.SCHEDULE_FILE)
        img_mgr = ImageManager(Config.IMAGE_DIR)
        poster = FacebookPoster(driver, Config)
        
        now = datetime.now().strftime("%H:%M")
        
        # Lọc các bài đến giờ đăng
        for item in schedule_data:
            post_time = str(item.get('time', ''))[:5]
            if post_time != now:
                continue
            
            content = item.get('content', '')
            image_name = item.get('image')
            category = item.get('group_category')
            
            image_path = img_mgr.get_image(image_name)
            
            # Lọc nhóm theo category
            target_groups = ExcelReader.get_groups_by_category(groups, category) \
                            if category else groups
            
            logger.info(f"Đăng {len(target_groups)} nhóm | Ảnh: {image_path}")
            poster.post_batch(target_groups, content, image_path)
    
    except Exception as e:
        logger.error(f"Lỗi task đăng bài: {e}")
    finally:
        driver.quit()


def task_auto_comment():
    """Task 2: Auto comment vào bài viết của người khác"""
    logger.info("=== BẮT ĐẦU TASK AUTO COMMENT ===")
    driver = create_driver()
    try:
        login_facebook(driver)
        
        groups = ExcelReader.read_groups(Config.GROUPS_FILE)
        comments_pool = load_comments_pool()
        commenter = FacebookCommenter(driver, Config, comments_pool)
        
        for group in groups[:5]:  # giới hạn 5 nhóm/lần chạy
            commenter.scan_and_comment(
                group['group_url'],
                keywords=group.get('keywords', '').split(',') if group.get('keywords') else None,
                max_comments=5
            )
    
    except Exception as e:
        logger.error(f"Lỗi task comment: {e}")
    finally:
        driver.quit()


# ============ SCHEDULER ============

def run_scheduler():
    """Chạy scheduler - kiểm tra mỗi phút"""
    # Đăng bài theo lịch - check mỗi phút
    schedule.every(1).minutes.do(task_scheduled_post)
    
    # Auto comment - chạy mỗi 2 giờ (random)
    schedule.every(2).hours.do(task_auto_comment)
    
    logger.info("🚀 Scheduler đã khởi động")
    
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    # Kiểm tra file cấu hình
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    os.makedirs(Config.IMAGE_DIR, exist_ok=True)
    
    # Chạy scheduler
    run_scheduler()
8️⃣ Chuẩn bị dữ liệu
data/groups.xlsx — danh sách nhóm:

group_url	group_name	category	keywords
https://facebook.com/groups/123456	Nhóm A	Điện tử	iphone,samsung
https://facebook.com/groups/789012	Nhóm B	Gia dụng	nồi cơm
data/schedule.xlsx — lịch đăng:

time	content	image	group_category
08:00	🔥 Flash sale hôm nay...	sp1.jpg	Điện tử
20:00	Sản phẩm mới về...	sp2.jpg	Gia dụng
data/comments.txt — nội dung comment (mỗi dòng 1 câu):

text
Sản phẩm này bên mình đang có giá tốt, ib mình nhé!
Mình cũng đang bán sản phẩm tương tự, giá ưu đãi hơn, ib nhé!
Cần tư vấn sản phẩm tương tự ib mình nha, giá tốt!
data/images/ — để ảnh sản phẩm (sp1.jpg, sp2.jpg...)

🚀 Cách chạy
bash
python main.py