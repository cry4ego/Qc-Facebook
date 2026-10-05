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
            root, ext = os.path.splitext(image_path)
            optimized_path = f"{root}_opt{ext}"
            img.save(optimized_path, optimize=True, quality=85)
            return optimized_path
        except Exception as e:
            print(f"Lỗi xử lý ảnh: {e}")
            return image_path
