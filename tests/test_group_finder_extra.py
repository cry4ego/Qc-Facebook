"""Tìm nhóm mới: ngoài các từ khóa trong config, bot tìm thêm theo từ khóa do công ty AI thêm (extra_queries). Nhóm tìm được từ
từ khóa thêm vẫn qua đúng bộ lọc cũ (chủ đề màn hình, không PC / laptop, đủ thành viên)."""
import logging
from types import SimpleNamespace

import pytest

from modules import group_finder

CAU_GIAY = "thanh lý màn hình Cầu Giấy Hà Nội"


@pytest.fixture
def config(tmp_path):
    return SimpleNamespace(GROUPS_FOUND_FILE=str(tmp_path / "found.xlsx"), GROUP_SEARCH_QUERIES=["màn hình cũ Hà Nội"],
                           GROUP_KEYWORDS=["màn hình", "Hà Nội"], MAX_FOUND_GROUPS=30, MIN_GROUP_MEMBERS=5000,
                           GROUP_MIN_MEMBERS_HANOI=500)


def nhom(ma, ten, thanh_vien):
    return {"url": f"https://www.facebook.com/groups/{ma}/", "name": ten, "privacy": "Nhóm công khai", "members": thanh_vien,
            "activity": "10 bài viết hôm nay"}


def chay(config, monkeypatch, ket_qua, **kw):
    """Chạy find_groups với search_groups giả; trả về (các từ khóa đã tìm, số nhóm mới)"""
    da_tim = []

    def tim(driver, query, scrolls=4):
        da_tim.append(query)
        return ket_qua.get(query, [])

    monkeypatch.setattr(group_finder, "search_groups", tim)
    monkeypatch.setattr(group_finder.time, "sleep", lambda giay: None)
    return da_tim, group_finder.find_groups(None, config, logging.getLogger("test"), [], **kw)


def test_extra_queries_are_searched_after_the_config_ones_without_duplicates(config, monkeypatch):
    da_tim, _ = chay(config, monkeypatch, {}, extra_queries=[CAU_GIAY, "MÀN HÌNH   cũ hà nội", CAU_GIAY, "mua bán màn hình Đống Đa Hà Nội"])
    assert da_tim == ["màn hình cũ Hà Nội", CAU_GIAY, "mua bán màn hình Đống Đa Hà Nội"]


def test_without_extra_queries_nothing_changes(config, monkeypatch):
    da_tim, them = chay(config, monkeypatch, {})
    assert da_tim == ["màn hình cũ Hà Nội"] and them == 0


def test_groups_from_an_extra_query_go_through_the_same_filters(config, monkeypatch):
    ket_qua = {CAU_GIAY: [nhom(111, "Chợ màn hình Cầu Giấy Hà Nội", 900),            # đạt: nhóm Hà Nội ≥ 500 thành viên
                          nhom(222, "Mua bán laptop cũ Hà Nội", 90000),                # laptop -> bỏ
                          nhom(333, "Màn hình Hà Nội", 100),                           # quá ít thành viên -> bỏ
                          nhom(444, "Mua bán màn hình HCM", 90000)]}                   # tỉnh khác -> bỏ
    _, them = chay(config, monkeypatch, ket_qua, extra_queries=[CAU_GIAY])
    da_luu = group_finder.load_found(config.GROUPS_FOUND_FILE)
    assert them == 1 and [(g["group_name"], g["query"]) for g in da_luu] == [("Chợ màn hình Cầu Giấy Hà Nội", CAU_GIAY)]


def test_stats_tell_how_many_queries_ran_failed_and_returned_anything(config, monkeypatch):
    def tim(driver, query, scrolls=4):
        if query == "hỏng":
            raise RuntimeError("Facebook không tải được trang")
        return [nhom(1, "Chợ màn hình Cầu Giấy Hà Nội", 900)] if query == CAU_GIAY else []

    monkeypatch.setattr(group_finder, "search_groups", tim)
    monkeypatch.setattr(group_finder.time, "sleep", lambda giay: None)
    stats = {}
    group_finder.find_groups(None, config, logging.getLogger("test"), [], extra_queries=[CAU_GIAY, "hỏng"], stats=stats)
    assert stats == {"truy_van": 3, "loi": 1, "co_ket_qua": 1}


def test_on_query_is_called_before_every_query(config, monkeypatch):
    thu_tu = []
    monkeypatch.setattr(group_finder, "search_groups", lambda driver, query, scrolls=4: thu_tu.append(("tim", query)) or [])
    monkeypatch.setattr(group_finder.time, "sleep", lambda giay: None)
    group_finder.find_groups(None, config, logging.getLogger("test"), [], extra_queries=[CAU_GIAY],
                             on_query=lambda: thu_tu.append(("nhip", None)))
    assert thu_tu == [("nhip", None), ("tim", "màn hình cũ Hà Nội"), ("nhip", None), ("tim", CAU_GIAY)]


def test_the_found_file_is_written_atomically(config, monkeypatch, tmp_path):
    chay(config, monkeypatch, {CAU_GIAY: [nhom(111, "Chợ màn hình Cầu Giấy Hà Nội", 900)]}, extra_queries=[CAU_GIAY])
    truoc = group_finder.load_found(config.GROUPS_FOUND_FILE)
    assert len(truoc) == 1 and [p.name for p in tmp_path.iterdir()] == ["found.xlsx"]       # không để lại file tạm

    def hong(self, *a, **kw):
        raise OSError("hết chỗ trống trên ổ đĩa")

    monkeypatch.setattr(group_finder.pd.DataFrame, "to_excel", hong)
    with pytest.raises(OSError):
        chay(config, monkeypatch, {CAU_GIAY: [nhom(222, "Mua bán màn hình Đống Đa Hà Nội", 800)]}, extra_queries=[CAU_GIAY])
    monkeypatch.undo()
    assert group_finder.load_found(config.GROUPS_FOUND_FILE) == truoc                          # file cũ còn nguyên
    assert [p.name for p in tmp_path.iterdir()] == ["found.xlsx"]


def test_a_failing_extra_query_does_not_stop_the_others(config, monkeypatch):
    da_tim = []

    def tim(driver, query, scrolls=4):
        da_tim.append(query)
        if query == CAU_GIAY:
            raise RuntimeError("Facebook không tải được trang")
        return [nhom(555, "Mua bán màn hình Đống Đa Hà Nội", 800)] if "Đống Đa" in query else []

    monkeypatch.setattr(group_finder, "search_groups", tim)
    monkeypatch.setattr(group_finder.time, "sleep", lambda giay: None)
    them = group_finder.find_groups(None, config, logging.getLogger("test"), [],
                                    extra_queries=[CAU_GIAY, "mua bán màn hình Đống Đa Hà Nội"])
    assert them == 1 and da_tim[-1] == "mua bán màn hình Đống Đa Hà Nội"
