"""
Đóng gói dự án thành 1 file zip để chuyển sang máy khác.

Chạy:  bấm đúp dong-goi.bat   (hoặc: .venv\\Scripts\\python.exe tools\\dong_goi.py)
Kết quả: ..\\QC-Facebook_dong-goi\\QC-Facebook_<ngày giờ>.zip (thư mục cạnh thư mục dự án)

Bỏ ra: .venv (môi trường Python chỉ chạy trên máy này), chrome_profile (cookie đăng nhập bị mã hóa theo
tài khoản Windows — không dùng được ở máy khác, phải đăng nhập lại), __pycache__, logs, file tạm.
CSDL được sao chép bằng sqlite backup (đủ dữ liệu kể cả khi web/script đang chạy).
"""
import os
import sys
import sqlite3
import zipfile
import tempfile
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".venv", "venv", "chrome_profile", "chrome_profile_quet", "chrome_profile_quet2", "__pycache__", ".git", "logs", ".claude", ".pytest_cache"}
SKIP_FILES = {"qc_facebook.db", "qc_facebook.db-wal", "qc_facebook.db-shm",  # CSDL thêm riêng bằng backup
              ".env"}  # khóa bí mật (Gemini…): tự chép tay sang máy mới, không để trong file zip


def skip_file(name):
    return (name in SKIP_FILES or name.startswith(("~$", "qc_facebook_backup_"))  # bản sao lưu CSDL: không đóng gói
            or name.endswith((".tmp.xlsx", ".pyc", ".bak")))


def main():
    out_dir = os.path.join(os.path.dirname(BASE), "QC-Facebook_dong-goi")
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, f"QC-Facebook_{datetime.now():%Y%m%d_%H%M}.zip")
    root = "QC-Facebook"

    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, dirs, files in os.walk(BASE):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                if skip_file(name):
                    continue
                full = os.path.join(folder, name)
                z.write(full, os.path.join(root, os.path.relpath(full, BASE)))
                count += 1

        db = os.path.join(BASE, "data", "qc_facebook.db")
        if os.path.exists(db):
            tmp = os.path.join(tempfile.mkdtemp(), "qc_facebook.db")
            src, dst = sqlite3.connect(db), sqlite3.connect(tmp)
            src.backup(dst)
            dst.close()
            src.close()
            z.write(tmp, os.path.join(root, "data", "qc_facebook.db"))
            count += 1

    size = os.path.getsize(zip_path) / 1024 / 1024
    print(f"✓ Đã đóng gói {count} file ({size:.1f} MB):")
    print(f"  {zip_path}")
    print("Máy mới: giải nén -> bấm đúp cai-dat.bat -> đăng nhập Facebook -> bấm đúp chay-ngam.bat")
    return zip_path


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
