"""Chrome profile: cửa sổ bình luận và cửa sổ quét không tắt nhầm Chrome của nhau; chép phiên đăng nhập bỏ bộ nhớ đệm."""
import os

from modules.browser import copy_profile, is_profile_process


def test_profile_match_is_exact(tmp_path):
    main, scan = str(tmp_path / "chrome_profile"), str(tmp_path / "chrome_profile_quet")
    cmd = lambda p: ["chrome.exe", "--type=renderer", f"--user-data-dir={p}"]
    assert is_profile_process(cmd(main), main)
    assert not is_profile_process(cmd(scan), main)      # trước đây so khớp chuỗi con -> tắt nhầm Chrome cửa sổ quét
    assert not is_profile_process(cmd(main), scan)
    assert is_profile_process(["chrome.exe", f'--user-data-dir="{main}"'], main)
    assert not is_profile_process(["chrome.exe"], main)


def test_copy_profile_keeps_login_but_skips_cache_and_locks(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "Default" / "Cache").mkdir(parents=True)
    (src / "Default" / "Cookies").write_text("cookie")
    (src / "Default" / "Cache" / "data_0").write_text("x")
    (src / "SingletonLock").write_text("lock")
    (dst / "old").mkdir(parents=True)
    copy_profile(str(src), str(dst))
    assert (dst / "Default" / "Cookies").read_text() == "cookie"
    assert not (dst / "Default" / "Cache").exists() and not (dst / "SingletonLock").exists()
    assert not (dst / "old").exists()
    assert os.path.isdir(dst / "Default")
