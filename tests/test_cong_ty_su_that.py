"""Sổ sự thật: đọc file chủ shop điền, nhận diện giá / SĐT trong chữ, kiểm tra nội dung theo sổ."""
import pytest

from cong_ty import su_that

DA_DIEN = """# Sổ sự thật
## Thông tin cửa hàng
Tên shop: ASL Workshop
Địa chỉ: 64 Cầu Diễn, Hà Nội
Số điện thoại: 0902 189 751
Zalo: ĐIỀN
(vd: dòng ghi chú trong ngoặc bị bỏ qua)
## Chính sách
Bảo hành: Tháng đầu lỗi 1 đổi 1
## Giá được phép nhắc thêm
- 2.900.000đ có chân
- 2tr6
## Không được nói
- miễn phí vận chuyển
- Bảo hành 12 tháng
"""

SO = su_that.SuThat(thong_tin=(("Số điện thoại", "0902 189 751"),), chua_dien=(), gia_them=(2_900_000,),
                    cam=("miễn phí vận chuyển",), co_file=True)
GIA = frozenset({2_500_000, 2_750_000})


def ghi(tmp_path, noi_dung):
    path = tmp_path / "su-that.md"
    path.write_text(noi_dung, encoding="utf-8")
    return str(path)


def test_template_marks_every_field_as_unfilled(tmp_path):
    path = str(tmp_path / "su-that.md")
    assert su_that.tao_mau_neu_chua_co(path) is True
    so = su_that.doc(path)
    assert so.co_file and set(so.chua_dien) == set(su_that.TRUONG)


def test_template_never_overwrites_an_existing_file(tmp_path):
    path = ghi(tmp_path, DA_DIEN)
    assert su_that.tao_mau_neu_chua_co(path) is False
    assert su_that.doc(path).lay("Địa chỉ") == "64 Cầu Diễn, Hà Nội"


def test_missing_file_reads_as_all_unfilled(tmp_path):
    so = su_that.doc(str(tmp_path / "khong-co.md"))
    assert not so.co_file and so.chua_dien == su_that.TRUONG and so.gia_them == () and so.cam == ()


def test_filled_fields_prices_and_banned_phrases_are_parsed(tmp_path):
    so = su_that.doc(ghi(tmp_path, DA_DIEN))
    assert so.lay("Địa chỉ") == "64 Cầu Diễn, Hà Nội" and so.lay("Bảo hành") == "Tháng đầu lỗi 1 đổi 1"
    assert "Zalo" in so.chua_dien and "Địa chỉ" not in so.chua_dien
    assert so.gia_them == (2_900_000, 2_600_000)
    assert so.cam == ("miễn phí vận chuyển", "bảo hành 12 tháng")
    assert so.lay("Giờ mở cửa", "chưa rõ") == "chưa rõ"


@pytest.mark.parametrize("text, expected", [
    ("Giá 2.500.000đ nhé", [2_500_000]),
    ("2.750.000đ không chân / 2.900.000đ có chân", [2_750_000, 2_900_000]),
    ("chỉ 2tr5", [2_500_000]),
    ("2,5 triệu", [2_500_000]),
    ("2tr65", [2_650_000]),
    ("2500k", [2_500_000]),
    ("màn 2K 240Hz 27 inch", []),
    ("độ phân giải 1.920 x 1.080", []),
    ("165Hz, 1ms, 24 inch", []),
    ("{giá} và {tiết_kiệm}", []),
])
def test_prices_are_recognised_but_resolution_is_not_a_price(text, expected):
    assert su_that.tim_gia(text) == expected


def test_phone_numbers_are_normalised_to_digits():
    assert su_that.so_dien_thoai("Gọi 0902 189 751 hoặc 0902.189.751") == ["0902189751", "0902189751"]
    assert su_that.so_dien_thoai("màn 165Hz giá 2.500.000đ") == []


def test_dotted_phone_number_is_not_mistaken_for_a_price():
    assert su_that.tim_gia("Gọi 090.218.9751 nhé") == []
    assert su_that.tim_gia("Gọi 0902 189 751, giá 2.500.000đ") == [2_500_000]


def test_price_typed_without_separators_is_still_a_price():
    assert su_that.tim_gia("2900000") == [2_900_000]
    assert su_that.tim_gia("2900000đ") == [2_900_000]
    assert su_that.gia_hop_le([{"price": "2900000", "new_price": None}]) == {2_900_000}


def test_international_phone_format_is_recognised_and_checked():
    assert su_that.so_dien_thoai("Gọi +84 902 189 751") == ["0902189751"]
    assert any("0912345678" in v for v in su_that.kiem_tra("Gọi +84 912 345 678", SO, GIA))
    assert su_that.kiem_tra("Gọi +84 902 189 751", SO, GIA) == ()


def test_valid_prices_come_from_the_product_table():
    san_pham = [{"price": "2.500.000đ", "new_price": "4.290.000đ"}, {"price": "1.950.000đ", "new_price": None}]
    assert su_that.gia_hop_le(san_pham) == {2_500_000, 4_290_000, 1_950_000}


def test_clean_text_passes():
    assert su_that.kiem_tra("Màn MSI 2K 240Hz giá 2.500.000đ. Gọi 0902 189 751", SO, GIA) == ()


def test_price_in_the_sheet_is_allowed_even_if_not_a_product_price():
    assert su_that.kiem_tra("Có chân 2.900.000đ", SO, GIA) == ()


def test_unknown_price_is_flagged():
    van_de = su_that.kiem_tra("Giá sốc 1.999.000đ", SO, GIA)
    assert len(van_de) == 1 and "1.999.000" in van_de[0]


def test_foreign_phone_number_is_flagged_but_only_when_shop_phone_is_known():
    assert any("0912345678" in v for v in su_that.kiem_tra("Gọi 0912 345 678", SO, GIA))
    chua_co_sdt = su_that.SuThat(thong_tin=(), chua_dien=("Số điện thoại",), gia_them=(), cam=(), co_file=True)
    assert su_that.kiem_tra("Gọi 0912 345 678", chua_co_sdt, GIA) == ()


def test_banned_phrase_is_flagged_ignoring_case():
    assert su_that.kiem_tra("MIỄN PHÍ vận chuyển toàn quốc", SO, GIA)


@pytest.mark.parametrize("text", [
    "miễn phí vận chuyển", "miễn phí vận chuyển",   # kiểu gõ tổ hợp (NFD)
    "miễn phí vận chuyển", "miễn  phí   vận chuyển", "miễn​ phí vận chuyển", "mien phi van chuyen"])
def test_banned_phrases_cannot_be_dodged_with_invisible_or_alternative_characters(text):
    assert su_that.kiem_tra(f"Màn MSI {text} nhé", SO, GIA)


def test_normalising_text_for_comparison():
    assert su_that.chuan_van_ban("  Giảm​ GIÁ ") == "giảm giá"
    assert su_that.bo_dau("Đổi mật khẩu") == "doi mat khau"


def test_emoji_is_flagged_because_the_bot_cannot_type_it():
    assert any("emoji" in v for v in su_that.kiem_tra("Màn đẹp 👍", SO, GIA))
