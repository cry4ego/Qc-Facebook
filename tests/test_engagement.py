"""Đọc số reaction / bình luận / chia sẻ của 1 bài trong bảng tin và tính điểm tương tác (Yêu cầu 2).
Dữ liệu mẫu chép theo đúng cấu trúc chữ Facebook hiển thị (tháng 10/2026), đã đổi tên người."""
from modules.engagement import Engagement, engagement_score, parse_engagement

COMPOSER = "Bình luận dưới tên Shop"
WEIGHTS = {"reaction": 1, "comment": 2, "share": 3}


def test_reactions_then_comments_bare_numbers():
    msg = "Em tìm màn hình xem cam, giá dưới 500k"
    text = (f"Người A\n  ·\nTheo dõi\n43 phút trước\n  ·\n{msg}\n2\n10\nXem thêm bình luận\nNgười B\n"
            f"Người đóng góp nổi bật\nCó tivi 24\n41 phút\nThích\nTrả lời\nChia sẻ\n\n{COMPOSER}")
    labels = ["Thích", "Bày tỏ cảm xúc", "Viết bình luận", "Xem ai đã bày tỏ cảm xúc về tin này", "Thích: 2 người",
              "Bình luận dưới tên Người B vào 41 phút trước", COMPOSER]
    e = parse_engagement(text, msg, labels)
    assert (e.reactions, e.comments, e.shares) == (2, 10, 0)
    assert engagement_score(e, WEIGHTS) == 22


def test_comments_only_without_reaction_summary():
    msg = "Pass màn 24in 100hz Giá 1.150.000 đủ sạc + dây HDMi.\nMàn đẹp Còn BH T1/2027.… Xem thêm"
    text = f"Người A\n44 phút trước\n  ·\n{msg}\n2\nNgười C\n  ·\nTheo dõi\nK ship hả bạn\n20 phút\nThích\n{COMPOSER}"
    labels = ["Thích", "Viết bình luận", "Bình luận dưới tên Người C vào 20 phút trước", COMPOSER]
    e = parse_engagement(text, msg, labels)
    assert (e.reactions, e.comments, e.shares) == (0, 2, 0)


def test_no_engagement_at_all():
    msg = "TC 500k tìm màn 22 - 24\" FHD, hoạt động tốt"
    e = parse_engagement(f"Người A\n44 phút trước\n  ·\n{msg}\n\n{COMPOSER}", msg, ["Thích", COMPOSER])
    assert (e.reactions, e.comments, e.shares) == (0, 0, 0)
    assert engagement_score(e, WEIGHTS) == 0


def test_reactions_comments_and_shares():
    msg = "Cần màn 27 inch 2K tầm 3tr"
    text = f"Người A\n2 giờ\n  ·\n{msg}\n15\n8\n3\nNgười B\nCòn nè\n1 giờ\n{COMPOSER}"
    labels = ["Xem ai đã bày tỏ cảm xúc về tin này", "Thích: 12 người"]
    e = parse_engagement(text, msg, labels)
    assert (e.reactions, e.comments, e.shares) == (15, 8, 3)
    assert engagement_score(e, WEIGHTS) == 15 + 16 + 9


def test_text_counts_old_layout_and_thousands():
    msg = "Tìm màn 24 inch"
    text = f"Người A\n3 giờ\n{msg}\nTất cả cảm xúc:\n1,2K\n45 bình luận\n6 lượt chia sẻ\nThích\n{COMPOSER}"
    e = parse_engagement(text, msg, [])
    assert (e.reactions, e.comments, e.shares) == (1200, 45, 6)


def test_comment_reaction_numbers_further_down_are_ignored():
    msg = "Kiếm màn 24in 144hz"
    text = f"Người A\n5 phút\n{msg}\nNgười B\nCó con AOC\n3\n2 phút\n{COMPOSER}"
    e = parse_engagement(text, msg, ["Bình luận dưới tên Người B vào 2 phút trước"])
    assert (e.reactions, e.comments, e.shares) == (0, 1, 0)  # 1 bình luận đang hiện, số 3 là cảm xúc của bình luận


def test_message_not_found_falls_back_to_labels():
    labels = ["Thích: 4 người", "Bình luận dưới tên X vào 5 phút trước", "Bình luận dưới tên Y vào 3 phút trước", COMPOSER]
    e = parse_engagement("không khớp gì", "đoạn khác hẳn", labels)
    assert (e.reactions, e.comments, e.shares) == (4, 2, 0)
    assert e.known is False   # chỉ là ước lượng — không được coi như "0 tương tác"


def test_score_uses_configured_weights():
    assert engagement_score(Engagement(1, 1, 1), {"reaction": 2, "comment": 5, "share": 10}) == 17
