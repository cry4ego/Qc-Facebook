"""
Lịch họp sáng: tới giờ mà hôm nay chưa họp thì họp (lỡ giờ vì máy tắt thì họp ngay khi máy bật); chủ shop bấm "Họp ngay"
trên web thì họp trong vòng một phút. Lỗi một lần không làm dừng vòng lặp, nhưng sau lỗi nghỉ một lúc rồi mới thử lại để không
gọi AI liên tục.
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Callable

from cong_ty import luu_tru
from modules.db import Database

GIAY_NGHI = 60              # vòng lặp kiểm tra mỗi ... giây
PHUT_CHO_THU_LAI = 30       # họp hỏng / kẹt thì ... phút sau mới họp lại
LOI_TOI_DA_MOI_NGAY = 3     # họp hỏng quá ... lần trong ngày thì thôi (hôm nay không tự họp nữa)
log = logging.getLogger(__name__)


def _so_loi(cuoc: list[dict]) -> int:
    return sum(1 for c in cuoc if c["trang_thai"] == luu_tru.LOI)


def can_hop(db: Database, bay_gio: datetime, gio_hop: int) -> bool:
    """Hôm nay tới giờ họp mà chưa có cuộc họp nào xong hay đang diễn ra? (họp hỏng / kẹt quá lâu thì họp lại, nhưng hỏng
    LOI_TOI_DA_MOI_NGAY lần rồi thì hôm nay thôi để khỏi gọi AI mãi; lỗi nằm ở biên bản / tab Công ty AI)"""
    cuoc = luu_tru.cuoc_hop_cua_ngay(db, bay_gio.strftime("%Y-%m-%d"))
    if any(c["trang_thai"] == luu_tru.XONG for c in cuoc) or _so_loi(cuoc) >= LOI_TOI_DA_MOI_NGAY:
        return False
    if not cuoc:
        return bay_gio.hour >= gio_hop
    moc = cuoc[0]["bat_dau"] if cuoc[0]["trang_thai"] == luu_tru.DANG_HOP else cuoc[0]["ket_thuc"] or cuoc[0]["bat_dau"]
    return bay_gio - datetime.strptime(moc, luu_tru.DINH_DANG_GIO) >= timedelta(minutes=PHUT_CHO_THU_LAI)


def buoc(db: Database, bay_gio: datetime, gio_hop: int, chay_hop: Callable[[bool], object]) -> str:
    """Một lượt kiểm tra: họp theo yêu cầu của chủ shop, hoặc theo lịch, hoặc chờ. chay_hop(ep): ep=True = họp dù hôm nay
    đã họp. Trả về 'hop_theo_yeu_cau' / 'hop_theo_lich' / 'cho'"""
    if luu_tru.dang_cho_hop(db):
        if _so_loi(luu_tru.cuoc_hop_cua_ngay(db, bay_gio.strftime("%Y-%m-%d"))) >= LOI_TOI_DA_MOI_NGAY:
            luu_tru.xoa_yeu_cau_hop(db)      # hôm nay họp hỏng quá nhiều lần: bỏ yêu cầu để khỏi lặp mãi
            return "cho"
        chay_hop(True)
        luu_tru.xoa_yeu_cau_hop(db)          # chỉ xóa cờ khi họp xong: họp hỏng thì yêu cầu của chủ shop không bị mất
        return "hop_theo_yeu_cau"
    if can_hop(db, bay_gio, gio_hop):
        chay_hop(False)
        return "hop_theo_lich"
    return "cho"


def vong_lap(db: Database, gio_hop: int, chay_hop: Callable[[bool], object], ngu: Callable[[float], None] = time.sleep,
             bay_gio: Callable[[], datetime] = datetime.now, dung: Callable[[], bool] = lambda: False) -> None:
    """Chạy mãi (cho tới khi dung() trả True): mỗi GIAY_NGHI giây xem có cần họp không"""
    nghi_den = None
    while not dung():
        bay_gio_nay = bay_gio()
        if nghi_den is None or bay_gio_nay >= nghi_den:
            try:
                buoc(db, bay_gio_nay, gio_hop, chay_hop)
            except Exception:    # lỗi bất ngờ (CSDL khóa, AI sập…) không được làm dừng lịch họp
                log.exception("Cuộc họp bị lỗi — nghỉ %d phút rồi thử lại", PHUT_CHO_THU_LAI)
                nghi_den = bay_gio_nay + timedelta(minutes=PHUT_CHO_THU_LAI)
        ngu(GIAY_NGHI)
