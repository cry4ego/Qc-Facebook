"""Công cụ kiểm tra vận hành: nhận ra cửa sổ tắt / chạy mã cũ / chạy trùng — sự cố thật 28/10/2026 (họp và web giữ mã cũ sau khi sửa code)."""
import importlib.util
import os
import time

import pytest

DUONG_DAN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "kiem_tra_van_hanh.py")
_spec = importlib.util.spec_from_file_location("kiem_tra_van_hanh", DUONG_DAN)
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

BAY_GIO = 1_800_000_000.0
KHONG_SUA = {ten: (BAY_GIO - 86400, "x.py") for ten in tool.CUA_SO}          # mọi file code sửa từ hôm qua


def tt(lenh, bat_dau=BAY_GIO - 3600):
    return {"cmd": tuple(lenh), "bat_dau": bat_dau}


def day_du(bat_dau=BAY_GIO - 3600):
    """Mỗi cửa sổ có 2 tiến trình (cha venv + con) khởi động sát nhau"""
    return [tt(lenh, bat_dau + k) for lenh, _ in tool.CUA_SO.values() for k in (0, 2)]


def trang_thai(ket_qua):
    return {r["cua_so"]: r["trang_thai"] for r in ket_qua}


@pytest.mark.parametrize("dong_lenh, mong_doi", [
    (["python.exe", "main.py"], ("main.py",)), (["D:\\x\\.venv\\Scripts\\python.exe", "main.py", "quet", "2"], ("main.py", "quet", "2")),
    (["python.exe", "web.py"], ("web.py",)), (["python.exe", "-m", "pytest", "-q"], ()), ([], ()), (["python.exe", "tools\\thu_nghiem_khu_vuc.py"], ()),
])
def test_command_signature_is_what_comes_after_the_script_name(dong_lenh, mong_doi):
    assert tool.chu_ky_lenh(dong_lenh) == mong_doi


def test_all_six_windows_running_new_code_are_all_fine():
    ket_qua = tool.danh_gia_cua_so(day_du(), KHONG_SUA)
    assert len(ket_qua) == 6 and set(trang_thai(ket_qua).values()) == {"moi"}
    assert not any(r["chay_trung"] for r in ket_qua)


def test_a_window_started_before_its_code_was_edited_is_stale_and_names_the_file():
    sua = {**KHONG_SUA, "Họp sáng (công ty AI)": (BAY_GIO - 60, "cong_ty/mau_ai.py")}
    ket_qua = tool.danh_gia_cua_so(day_du(), sua)
    ts = trang_thai(ket_qua)
    assert ts["Họp sáng (công ty AI)"] == "cu" and ts["Bình luận"] == "moi"           # chỉ cửa sổ dùng file đó bị báo cũ
    assert next(r for r in ket_qua if r["trang_thai"] == "cu")["file_sua_sau"] == "cong_ty/mau_ai.py"


def test_a_missing_window_is_reported_as_off():
    ts = [t for t in day_du() if t["cmd"] != ("main.py", "hopngam")]
    assert trang_thai(tool.danh_gia_cua_so(ts, KHONG_SUA))["Họp sáng (công ty AI)"] == "tat"


def test_the_same_window_started_twice_far_apart_is_flagged_as_a_duplicate():
    ts = day_du() + [tt(("web.py",), BAY_GIO - 7200)]
    ket_qua = {r["cua_so"]: r for r in tool.danh_gia_cua_so(ts, KHONG_SUA)}
    assert ket_qua["Web quản lý"]["chay_trung"] and not ket_qua["Bình luận"]["chay_trung"]


def test_quet_1_and_quet_2_are_told_apart():
    ts = [tt(("main.py", "quet", "2"))]
    ts_theo = trang_thai(tool.danh_gia_cua_so(ts, KHONG_SUA))
    assert ts_theo["Quét 2"] == "moi" and ts_theo["Quét 1"] == "tat"


def test_newest_edit_is_found_in_folders_and_single_files(tmp_path):
    (tmp_path / "modules").mkdir()
    (tmp_path / "modules" / "a.py").write_text("x")
    (tmp_path / "modules" / "__pycache__").mkdir()
    (tmp_path / "modules" / "__pycache__" / "b.py").write_text("x")           # không tính
    (tmp_path / "config.py").write_text("x")
    os.utime(tmp_path / "modules" / "a.py", (time.time() - 100, time.time() - 100))
    os.utime(tmp_path / "modules" / "__pycache__" / "b.py", (time.time(), time.time()))
    t, ten = tool.sua_code_moi_nhat(("modules", "config.py"), str(tmp_path))
    assert ten == "config.py" and t > time.time() - 50
    t2, ten2 = tool.sua_code_moi_nhat(("modules",), str(tmp_path))
    assert ten2.replace("\\", "/") == "modules/a.py"


def test_every_expected_window_depends_on_code_that_exists_in_the_project():
    goc = tool.GOC
    for ten, (_, cay) in tool.CUA_SO.items():
        for muc in cay:
            assert os.path.exists(os.path.join(goc, muc)), (ten, muc)
