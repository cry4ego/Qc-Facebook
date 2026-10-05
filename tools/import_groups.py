"""
Chuyển file danh sách nhóm (nhom_facebook_man_hinh_PC.xlsx) sang data/groups.xlsx
theo định dạng script cần: group_url, group_name, category, keywords

Chạy:  python tools/import_groups.py
"""
import os
import re
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

SOURCE_FILE = os.path.join(Config.DATA_DIR, "nhom_facebook_man_hinh_PC.xlsx")
SOURCE_SHEET = "Tất cả"

# Đổi tên "Phân loại" trong file gốc -> category ngắn gọn (dùng cho cột group_category của schedule.xlsx)
CATEGORY_MAP = {
    "Chuyên màn hình": "Màn hình",
    "PC / linh kiện / gaming gear": "PC",
}

# Chỉ comment vào bài có chứa 1 trong các từ này (cách nhau bằng dấu phẩy)
DEFAULT_KEYWORDS = "màn hình,man hinh,monitor,144hz,165hz,180hz,27 inch,27inch"


# Nhận diện khu vực theo tên nhóm
REGION_PATTERNS = {
    "Hà Nội": r"hà nội|ha noi|hanoi|\bhn\b",
}


def detect_region(name):
    for region, pattern in REGION_PATTERNS.items():
        if re.search(pattern, str(name), flags=re.IGNORECASE):
            return region
    return ""


def main():
    df = pd.read_excel(SOURCE_FILE, sheet_name=SOURCE_SHEET)
    out = pd.DataFrame({
        "group_url": df["Link nhóm"].str.strip(),
        "group_name": df["Tên nhóm"],
        "category": df["Phân loại"].map(CATEGORY_MAP).fillna(df["Phân loại"]),
        "region": df["Tên nhóm"].map(detect_region),
        "keywords": DEFAULT_KEYWORDS,
        "privacy": df["Quyền riêng tư"],
        "members": df["Số thành viên (ước tính)"],
        "activity": df["Mức hoạt động"],
    }).drop_duplicates("group_url")

    out.to_excel(Config.GROUPS_FILE, index=False)
    print(f"✓ Đã ghi {len(out)} nhóm vào {Config.GROUPS_FILE}")
    print(out.groupby(["region", "category"]).size().to_string())


if __name__ == "__main__":
    main()
