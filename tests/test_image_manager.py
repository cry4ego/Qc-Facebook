"""Chọn ảnh cho bài đăng theo lịch (11/10: lịch ghi tên ảnh giá cũ đã bị xóa -> bài đăng KHÔNG có ảnh)."""
from modules.image_manager import ImageManager


def make(tmp_path, *names):
    for n in names:
        (tmp_path / n).write_bytes(b"png")
    return ImageManager(str(tmp_path))


def test_exact_file_name_is_used(tmp_path):
    m = make(tmp_path, "MSI_G274QPF_E2_2K_180Hz_.png")
    assert m.get_image("MSI_G274QPF_E2_2K_180Hz_.png").endswith("MSI_G274QPF_E2_2K_180Hz_.png")


def test_renamed_image_of_same_model_is_found(tmp_path):
    m = make(tmp_path, "MSI_G274QPF_E2_2K_180Hz_.png", "MSI_G274QRFW_2K_170Hz_.png")
    # tên cũ trong lịch (ảnh giá cũ đã xóa) -> vẫn lấy ảnh mới của đúng mẫu màn, không lấy nhầm mẫu khác
    assert m.get_image("MSI_G274QPF_E2_2K_180Hz_Gia_2400000d.png").endswith("MSI_G274QPF_E2_2K_180Hz_.png")
    assert m.get_image("MSI_G274QRFW_2K_170Hz_Gia_2450000d.png").endswith("MSI_G274QRFW_2K_170Hz_.png")


def test_no_image_of_that_model_returns_none(tmp_path):
    m = make(tmp_path, "MSI_G274QRFW_2K_170Hz_.png")
    assert m.get_image("MSI_G2712F_FHD_180Hz_Gia_1600000d.jpg") is None
