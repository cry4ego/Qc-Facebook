"""Phân loại ý định MUA / BÁN (Yêu cầu 1).
Nghiệm thu: 20 bài mẫu (10 MUA, 10 BÁN) đúng ≥ 18/20 và KHÔNG bài BÁN nào bị nhận là MUA.
Bài mẫu viết theo đúng kiểu bài thật trong các nhóm (đã bỏ tên người, SĐT là số giả)."""
import pytest

from modules.intent import BUY, SELL, UNKNOWN, classify_intent, load_rules, parse_rules

BUY_POSTS = [
    "Tìm màn 27in 144hz-180hz cũ lướt tại hn",
    "em cần tìm màn ASrock giá hạt rẻ, có bác nào cần thanh lý không ạ",
    "Hà Đông cần màn 27 còn ngon ae cmt nhé",
    "Mình ở Định Công Hà Nội tìm màn 27. Giá 1tr5 bác nào có không ạ",
    "Em tài chính dưới 2 triệu, tìm màn 24-27 inch, màn IPS, còn bảo hành. Chỉ ship cod. Ưu tiên người dùng pass lại ạ",
    "Kv hoàn kiếm HN kiếm màn full hd trên 100hz ai có ib lấy luôn trong ngày",
    "dưới 1tr có màn nào lớn chút thanh lý ko các bác",
    "TC 500k tìm màn 22 - 24\" FHD, hoạt động tốt, không lỗi, có cod",
    "Có bác nào pass lại card màn hình giá rẻ khoảng hơn 1 triệu đổ lại không ạ?",
    "tài chính 18-20m mình cần pc đủ để làm đồ hoạ + chơi game ạ",
]
SELL_POSTS = [
    "Bán vài màn hình văn phòng - đồ họa nhẹ\nLG 27MP59G 27\" IPS 75Hz 1ms Freesync. Màn đẹp ko lỗi, ko box hết BH GIÁ 1,2tr",
    "Thanh lý con màn 32in 2k 165hz hết bh đẹp keng, k lỗi gì. Giá đẹp tiết kiệm 4 củ cho ae",
    "Hà Nội, màn Dell P2419h, P2422he typeC, u2422h giá từ 2tr. Ai cần ib. Màn đẹp không lỗi",
    "E còn 3 con ai nhanh thì còn ạ\nMSI G2712F (FHD/ Rapid IPS/180Hz/1ms). K chân",
    "#HN nâng màn nên thừa ra 1 em Viewsonic XG2431 240HZ fullbox ạ\ntàu nhanh 1m8 cho ai ít nói",
    "Pass màn Yunsi 24in 100hz Giá 1.150.000 đủ sạc + dây HDMI.\nMàn đẹp Còn BH T1/2027.",
    "Cty mình còn 10 màn Dell P2219h cũ cần thanh lý.\nThông tin kỹ thuật:",
    "Mình ở định công, bác nào qua lấy luôn thì cmt nhé\nMain : B760 Pro B\nChip : Core i5 12400F",
    "Lẻ 10 màn Edra 27” 240hz còn bh hãng t10/2027\ngiá 2tr1 /1c\nLh 0900.000.000\nCầu Giấy HN",
    "Dọn văn phòng bán cho bác nào cần. 4 màn samsung, 1 màn HP compaq 19in. Tất cả hoạt động bình thường không lỗi",
]


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def test_acceptance_20_posts_at_least_18_correct(rules):
    results = [(t, classify_intent(t, rules).label, BUY) for t in BUY_POSTS] \
        + [(t, classify_intent(t, rules).label, SELL) for t in SELL_POSTS]
    wrong = [(t[:50], got, want) for t, got, want in results if got != want]
    assert len(results) == 20
    assert len(results) - len(wrong) >= 18, wrong


@pytest.mark.parametrize("text", SELL_POSTS)
def test_no_sell_post_is_classified_as_buy(text, rules):
    assert classify_intent(text, rules).label != BUY


@pytest.mark.parametrize("text", [
    "Màn hình 2k 27 inch hãng E-Dra dùng bền không vậy mọi người",
    "Con màn Asus của e nó bị lỏng cái cổng HDMI, e muốn thay mới ai nhận làm ko ạ",
    "",
])
def test_unclear_posts_are_unknown(text, rules):
    assert classify_intent(text, rules).label == UNKNOWN


@pytest.mark.parametrize("text", [
    # 2 bài thật từng bị nhận nhầm là MUA khi chạy thử 06/10/2026
    "Các bác cho em hỏi. Màn như này là bị gì ạ. Tầm 15-20p sau thì mới sáng lại bình thường",  # "tầm 15" ≠ ngân sách
    "Anh em đang tìm màn 165Hz chơi game, tham khảo chiếc này nhé!",                          # quảng cáo của shop
])
def test_real_false_positives_are_not_buy(text, rules):
    assert classify_intent(text, rules).label != BUY


def test_result_explains_matched_keywords(rules):
    r = classify_intent("Cần mua màn 27 inch tầm 2tr", rules)
    assert r.label == BUY
    assert r.buy_score > r.sell_score
    assert "cần mua" in r.reason


def test_rules_file_format_weights_regex_and_comments():
    rules = parse_rules("# chú thích\n[MUA]\ncần mua | 4\nre: ^tìm\\b | 3\n\n[BÁN]\nthanh lý\n")
    assert [(r.label, r.weight) for r in rules.buy] == [("cần mua", 4.0), ("^tìm\\b", 3.0)]
    assert [(r.label, r.weight) for r in rules.sell] == [("thanh lý", 2.0)]


def test_broken_line_is_skipped_and_reported_not_fatal():
    errors = []
    rules = parse_rules("[MUA]\nre: cần (mua | 3\nre:  | 2\ncần tìm | 3\n[BÁN]\nbán\n", errors)
    assert [r.label for r in rules.buy] == ["cần tìm"]          # 2 dòng hỏng bị bỏ, dòng tốt vẫn dùng
    assert len(errors) == 2 and "regex sai" in errors[0]
    assert classify_intent("Cần tìm màn 27 inch", rules).label == BUY


def test_custom_keywords_change_the_result():
    rules = parse_rules("[MUA]\nhóng màn | 5\n[BÁN]\n")
    assert classify_intent("Ai có con 27 inch không, hóng màn quá", rules).label == BUY


def test_keyword_matches_whole_words_only():
    rules = parse_rules("[MUA]\n[BÁN]\nbán | 5\n")
    assert classify_intent("bánh mì ngon", rules).label == UNKNOWN
