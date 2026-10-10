"""
Khu vực của người cần mua (đọc trong nội dung bài). Shop ở Hà Nội: bài ghi rõ khu vực xa (TP.HCM, miền Nam,
miền Trung, tỉnh xa…) mà không nhắc Hà Nội / tỉnh lân cận thì bỏ qua — dành lượt bình luận cho khách ở gần.
Bài không ghi khu vực nào vẫn được bình luận.

Danh sách nằm trong file riêng (mặc định data/khu_vuc.txt — sửa file, không sửa code; sửa xong có hiệu lực ngay):
mục [GẦN] và [XA], mỗi dòng 1 tên (khớp nguyên từ, không phân biệt hoa thường) hoặc 're: <regex> | 1 | tên'.
"""
from dataclasses import dataclass

from modules.intent import load_cached, normalize, parse_sections

NEAR, FAR = "near", "far"
SECTIONS = {"GẦN": NEAR, "GAN": NEAR, "XA": FAR}


@dataclass(frozen=True)
class Regions:
    near: tuple   # Rule — Hà Nội & tỉnh lân cận
    far: tuple    # Rule — khu vực xa


@dataclass(frozen=True)
class RegionResult:
    near: tuple   # tên khu vực gần nhắc trong bài
    far: tuple    # tên khu vực xa nhắc trong bài

    @property
    def is_far(self):
        """Chỉ nhắc khu vực xa (nhắc cả Hà Nội thì vẫn tính là khách gần)"""
        return bool(self.far) and not self.near


def parse_regions(content, errors=None):
    found = parse_sections(content, SECTIONS, errors)
    return Regions(tuple(found[NEAR]), tuple(found[FAR]))


def load_regions(path):
    return load_cached(path, parse_regions, "khu vực")


def find_regions(text, regions):
    t = normalize(text)
    hits = lambda rules: tuple(r.label for r in rules if r.pattern.search(t))
    return RegionResult(hits(regions.near), hits(regions.far))
