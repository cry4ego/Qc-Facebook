"""
Chrome profile của bot. Chạy song song có 2 profile: chrome_profile (cửa sổ BÌNH LUẬN) và chrome_profile_quet
(cửa sổ QUÉT) — mỗi profile chỉ 1 Chrome được mở cùng lúc.
"""
import os
import shutil
import time

import psutil

# Không chép sang profile cửa sổ quét: bộ nhớ đệm (to, tự tạo lại) và khóa của Chrome đang chạy
COPY_IGNORE = shutil.ignore_patterns("Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache",
                                     "GrShaderCache", "GraphiteDawnCache", "ShaderCache", "Service Worker",
                                     "Crashpad", "Singleton*", "lockfile", "*.tmp", "BrowserMetrics*")


def _same_path(a, b):
    return os.path.normcase(os.path.abspath(a.strip('"'))) == os.path.normcase(os.path.abspath(b))


def is_profile_process(cmdline, profile):
    """Tiến trình Chrome (cmdline = danh sách tham số) dùng đúng thư mục profile này — so khớp cả đường dẫn,
    không nhầm chrome_profile với chrome_profile_quet"""
    for arg in cmdline or []:
        if arg.startswith("--user-data-dir=") and _same_path(arg.split("=", 1)[1], profile):
            return True
    return False


def _chrome_processes(profile):
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            if (proc.info["name"] or "").lower() == "chrome.exe" and is_profile_process(proc.info["cmdline"], profile):
                yield proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def profile_in_use(profile):
    return any(True for _ in _chrome_processes(profile))


def close_leftover_chrome(profile, logger=None):
    """Tắt Chrome còn sót (vd bị Ctrl+C) đang giữ profile này — không đụng Chrome cá nhân / Chrome của cửa sổ kia"""
    killed = 0
    for proc in _chrome_processes(profile):
        try:
            proc.kill()
            killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed:
        if logger:
            logger.info(f"Đã đóng {killed} tiến trình Chrome còn sót từ lần chạy trước ({os.path.basename(profile)})")
        time.sleep(2)
    return killed


def copy_profile(src, dst):
    """Chép phiên đăng nhập (profile Chrome) src -> dst (xóa dst cũ). Chrome dùng src phải đang tắt"""
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=COPY_IGNORE)
