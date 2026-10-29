"""
Lịch tìm nhóm mới và nhịp tim của cửa sổ KHÁM PHÁ (chạy ngầm, Chrome riêng — python main.py khampha). Không import Selenium: việc tìm
thật (group_finder.find_groups) được truyền vào, nên toàn bộ logic lịch / thử lại / nhịp tim kiểm thử được mà không cần Chrome.

- chay_tim(): tìm nhóm khi tới giờ (every_hours giờ 1 lần). Tìm HỎNG — lỗi, hoặc mọi từ khóa đều trả rỗng (dấu hiệu phiên Facebook
  hết hạn / bị chặn tìm kiếm) — thì KHÔNG coi là đã tìm xong: nghỉ THU_LAI_SAU_GIO giờ rồi thử lại, không đập liên tục vào Facebook
  và cũng không im lặng bỏ qua cả ngày. Trả về True (tìm được), False (tìm hỏng), None (chưa tới giờ).
- nhip() / con_song(): cửa sổ khám phá ghi nhịp tim; còn sống (≤ SONG_PHUT phút) thì cửa sổ bình luận không tự tìm nhóm nữa. Cửa sổ
  khám phá chỉ báo "còn sống" khi việc tìm thật sự chạy (không phải chỉ vòng lặp còn quay), nên khi nó hỏng cửa sổ bình luận tự tìm lại.
"""
from datetime import datetime, timedelta
from typing import Callable

LAN_TIM_SETTING = "groups_searched_at"
NHIP_SETTING = "discovery_heartbeat"
DINH_DANG = "%Y-%m-%d %H:%M:%S"
THU_LAI_SAU_GIO = 1        # tìm hỏng thì ... giờ sau thử lại
SONG_PHUT = 30             # nhịp tim cũ hơn ngần này phút = cửa sổ khám phá đã tắt / hỏng


def _doc_gio(chu: str | None) -> datetime | None:
    try:
        return datetime.strptime(chu or "", DINH_DANG)
    except ValueError:
        return None


def nhip(db, bay_gio: datetime | None = None) -> None:
    db.set_setting(NHIP_SETTING, (bay_gio or datetime.now()).strftime(DINH_DANG))


def con_song(db, bay_gio: datetime | None = None, phut: int = SONG_PHUT) -> bool:
    """Cửa sổ khám phá có nhịp tim trong `phut` phút qua? Nhịp tim hỏng / chưa có = không"""
    nhip_cuoi = _doc_gio(db.get_setting(NHIP_SETTING))
    return nhip_cuoi is not None and (bay_gio or datetime.now()) - nhip_cuoi < timedelta(minutes=phut)


def _den_gio(db, every_hours: float, bay_gio: datetime) -> bool:
    lan_cuoi = _doc_gio(db.get_setting(LAN_TIM_SETTING))
    return lan_cuoi is None or bay_gio - lan_cuoi >= timedelta(hours=every_hours)


def _hen_thu_lai(db, every_hours: float, bay_gio: datetime) -> None:
    """Đặt mốc "lần tìm cuối" sao cho lần tới hạn sau THU_LAI_SAU_GIO giờ (không phải sau every_hours giờ)"""
    moc = bay_gio - timedelta(hours=max(every_hours - THU_LAI_SAU_GIO, 0))
    db.set_setting(LAN_TIM_SETTING, moc.strftime(DINH_DANG))


def chay_tim(db, logger, driver, find: Callable, known_fn: Callable[[], list], extra_fn: Callable[[], list],
             every_hours: float, force: bool = False, progress: Callable | None = None,
             on_query: Callable | None = None, bay_gio: datetime | None = None) -> bool | None:
    """Tìm nhóm mới nếu tới giờ. find(driver, known, extra, stats, on_query) -> số nhóm mới (và điền stats như
    group_finder.find_groups); known_fn() = các link nhóm đã biết; extra_fn() = từ khóa do công ty AI thêm (đọc hỏng thì bỏ qua,
    vẫn tìm theo từ khóa trong config). Xem docstring đầu file về giá trị trả về"""
    bay_gio = bay_gio or datetime.now()
    if not force and not _den_gio(db, every_hours, bay_gio):
        return None
    logger.info("=== TÌM NHÓM MỚI THEO TỪ KHÓA ===")
    (progress or (lambda **fields: None))(phase="Tìm nhóm mới theo từ khóa", step="Tìm trên Facebook theo GROUP_SEARCH_QUERIES",
                                          post_text="", post_url="")
    try:
        extra = list(extra_fn())
    except Exception:     # công ty AI hỏng không được làm bot ngừng tìm nhóm: cứ tìm theo từ khóa trong config
        logger.exception("Không đọc được từ khóa tìm nhóm do công ty AI thêm — tìm theo từ khóa trong config")
        extra = []
    stats: dict = {}
    try:
        them = find(driver, list(known_fn()), extra, stats, on_query)
    except Exception as e:
        logger.error(f"Lỗi tìm nhóm mới: {e} — {THU_LAI_SAU_GIO} giờ sau thử lại")
        _hen_thu_lai(db, every_hours, bay_gio)
        return False
    if stats.get("truy_van", 0) > 0 and stats.get("co_ket_qua", 0) == 0:
        logger.warning(f"Tìm nhóm: {stats['truy_van']} từ khóa mà không có kết quả nào ({stats.get('loi', 0)} lỗi) — nghi phiên "
                       f"Facebook hết hạn hoặc bị chặn tìm kiếm; {THU_LAI_SAU_GIO} giờ sau thử lại")
        _hen_thu_lai(db, every_hours, bay_gio)
        return False
    db.set_setting(LAN_TIM_SETTING, bay_gio.strftime(DINH_DANG))
    logger.info(f"Đã thêm {them} nhóm mới vào groups_found.xlsx — vòng sau tự tham gia & bình luận")
    return True
