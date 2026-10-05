import pandas as pd
import os


class ExcelReader:
    @staticmethod
    def read_groups(file_path):
        """Đọc danh sách nhóm từ Excel"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Không tìm thấy: {file_path}")
        df = pd.read_excel(file_path).fillna("")  # ô trống -> "" thay vì NaN
        return df.to_dict('records')

    @staticmethod
    def read_schedule(file_path):
        """Đọc lịch đăng bài"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Không tìm thấy: {file_path}")
        df = pd.read_excel(file_path).fillna("")
        return df.to_dict('records')

    @staticmethod
    def get_groups_by_category(groups, category):
        return [g for g in groups if g.get('category') == category]
