"""
Cuộc họp sáng của công ty AI (chế độ quan sát: chỉ họp và đề xuất, chưa tự làm gì).

Thứ tự: (1) báo cáo sáng bằng code -> (2) đề xuất theo luật + 4 vai AI (Phân tích, Săn khách, Nội dung, Chăm sóc khách) nếu
còn lượt AI -> (3) Kiểm soát rủi ro soát từng đề xuất bằng luật cứng (quyền phủ quyết) -> (4) vòng 2: vai có đề xuất bị chặn
được sửa một lần -> (5) Giám đốc chọn các đề xuất trình chủ shop (tối đa CONG_TY_DE_XUAT_TOI_DA chờ duyệt cùng lúc) và viết tóm
tắt -> (6) lưu biên bản + đề xuất. Không có AI thì bước 2 chỉ còn luật và Giám đốc chọn theo thứ tự ưu tiên: cuộc họp luôn xong.
"""
import logging
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from typing import Callable

from cong_ty import bao_cao, hanh_dong, lich, luat, luu_tru, mau_ai, nhom_ai, rao_chan, su_that
from cong_ty import vai as vai_mod
from cong_ty.de_xuat import DeXuat, chuan_hoa
from modules.db import Database

NGAY_KHONG_DE_XUAT_LAI = 14      # đề xuất cùng loại + tiêu đề đã nêu / đã quyết trong ... ngày thì không nêu lại
GIO_HOP_MAC_DINH = time(7, 0)    # giờ coi là "lúc họp" khi người gọi không truyền bay_gio (test)
SO_DE_XUAT_TOI_DA_MAC_DINH = 3
NGAY_QUAN_SAT_MAC_DINH = 7
GHI_CHU_TU_LAM = "Công ty tự làm vì công tắc “tự làm” đang bật"
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class UngVien:
    dx: DeXuat
    nguon: str            # luat / ai
    vong: int = 1
    van_de: tuple = ()    # lý do Kiểm soát rủi ro chặn (rỗng = qua)


class _CuocHop:
    """Một cuộc họp đang diễn ra: giữ bối cảnh (báo cáo, sổ sự thật, giá hợp lệ) và đếm lượt AI đã dùng"""

    def __init__(self, db: Database, config, duong_dan_su_that: str, hom_nay: date, bo_ai, thu_muc_bao_cao: str | None,
                 bay_gio: datetime, cuoc_id: int, dong_ho: Callable[[], datetime]):
        self.db, self.bo_ai, self.hom_nay, self.bay_gio, self.cuoc_id = db, bo_ai, hom_nay, bay_gio, cuoc_id
        self.dong_ho, self.duong_dan_su_that = dong_ho, duong_dan_su_that
        self.so = su_that.doc(duong_dan_su_that)
        self.bc = bao_cao.tao_bao_cao(db, config, duong_dan_su_that, hom_nay, bay_gio=bay_gio)
        if thu_muc_bao_cao:
            try:
                bao_cao.luu(self.bc, thu_muc_bao_cao)    # bản chữ lưu ra file chỉ là bản sao tiện đọc: lỗi ghi không được làm hỏng họp
            except OSError as e:
                log.warning("Không lưu được file báo cáo sáng (%s) — cuộc họp vẫn tiếp tục", e)
        self.boi = vai_mod.boi_canh(self.bc, self.so, db.products(active_only=True))
        self.gia = su_that.gia_hop_le(db.products())
        self.toi_da = getattr(config, "CONG_TY_DE_XUAT_TOI_DA", SO_DE_XUAT_TOI_DA_MAC_DINH)
        self.ngay_quan_sat = getattr(config, "CONG_TY_NGAY_QUAN_SAT", NGAY_QUAN_SAT_MAC_DINH)
        self.truy_van_goc = tuple(getattr(config, "GROUP_SEARCH_QUERIES", ()))     # từ khóa tìm nhóm có sẵn trong config
        self.nguon_ai: set[str] = set()
        self.so_luot = 0

    def ghi(self, vai: str, vong: int, noi_dung: str) -> None:
        luu_tru.them_ban_tin(self.db, self.cuoc_id, vai, vong, noi_dung, self.bay_gio)

    def _dem_luot(self, nguon: str) -> None:
        if nguon:
            self.so_luot += 1
            self.nguon_ai.add(nguon)

    def _chuan_hoa(self, vai: str, tho: tuple, vong: int) -> list[UngVien]:
        ket_qua = []
        for d in tho:
            try:
                ket_qua.append(UngVien(chuan_hoa(vai, d, self.hom_nay), "ai", vong))
            except ValueError as e:
                self.ghi(vai, vong, f"Bỏ một đề xuất không hợp lệ: {e}")
        return ket_qua

    def _soat(self, ung_vien: list[UngVien]) -> list[UngVien]:
        return [replace(u, van_de=rao_chan.kiem_tra(u.dx, self.bc, self.so, self.gia, nguon=u.nguon)) for u in ung_vien]

    def thu_de_xuat(self) -> list[UngVien]:
        """Đề xuất theo luật + của 4 vai AI (nếu còn lượt), đã bỏ trùng"""
        ung_vien = [UngVien(dx, "luat") for dx in luat.de_xuat_theo_luat(self.bc, self.hom_nay)]
        if self.bo_ai.con_luot():
            da_co = [u.dx.tieu_de for u in ung_vien] + [d["tieu_de"] for d in luu_tru.liet_ke_de_xuat(
                self.db, trang_thai=luu_tru.CHO_DUYET)]
            boi = {**self.boi, "de_xuat_da_co": list(dict.fromkeys(da_co))}
            for vai in vai_mod.VAI_AI:
                kq = vai_mod.chay_vai(self.bo_ai, vai, boi)
                self._dem_luot(kq.nguon)
                self.ghi(vai, 1, kq.nhan_xet or kq.loi or "(không có nhận xét)")
                ung_vien += self._chuan_hoa(vai, kq.de_xuat, 1)
        return self._bo_trung(ung_vien)

    def _bo_trung(self, ung_vien: list[UngVien], da_co: list[UngVien] = ()) -> list[UngVien]:
        """Bỏ đề xuất trùng nhau trong danh sách, trùng `da_co` (chỉ tính cái đã qua rào chắn) hoặc đã nêu gần đây"""
        tu_ngay = (self.bay_gio - timedelta(days=NGAY_KHONG_DE_XUAT_LAI)).strftime("%Y-%m-%d")
        giu, da_thay = [], {(u.dx.loai, u.dx.tieu_de) for u in da_co if not u.van_de}
        for u in ung_vien:
            khoa = (u.dx.loai, u.dx.tieu_de)
            if khoa in da_thay or luu_tru.da_de_xuat_gan_day(self.db, u.dx, tu_ngay, self.cuoc_id):
                continue
            da_thay.add(khoa)
            giu.append(u)
        if len(giu) < len(ung_vien):
            self.ghi("giam_doc", 1, f"Bỏ {len(ung_vien) - len(giu)} đề xuất đã nêu gần đây (đang chờ duyệt, đã duyệt "
                                    "hoặc bị từ chối).")
        return giu

    def vong_sua(self, ung_vien: list[UngVien]) -> list[UngVien]:
        """Vòng 2: mỗi vai có đề xuất bị chặn được sửa MỘT lần; trả các đề xuất đã sửa (đã soát lại)"""
        moi: list[UngVien] = []
        for vai in vai_mod.VAI_AI:
            bi_chan = [(u.dx, u.van_de) for u in ung_vien if u.nguon == "ai" and u.van_de and u.dx.vai == vai]
            if not bi_chan or not self.bo_ai.con_luot():
                continue
            kq = vai_mod.sua_vai(self.bo_ai, vai, self.boi, bi_chan)
            self._dem_luot(kq.nguon)
            self.ghi(vai, 2, kq.nhan_xet or kq.loi or "(không sửa được)")
            moi += self._soat(self._chuan_hoa(vai, kq.de_xuat, 2))
        return self._bo_trung(moi, ung_vien)

    def nhan_xet_rui_ro(self, ung_vien: list[UngVien], vong: int) -> None:
        """Lời của Kiểm soát rủi ro — viết bằng code từ kết quả soát và số liệu rủi ro, không dùng AI"""
        rr, chan = self.bc["rui_ro"], [u for u in ung_vien if u.van_de]
        dong = [f"Đã soát {len(ung_vien)} đề xuất bằng luật cứng: {len(chan)} bị chặn."]
        dong += [f"- Chặn “{u.dx.tieu_de}”: {'; '.join(u.van_de)}" for u in chan]
        if rr["safe_all"]:
            dong.append("Lưu ý: đang dùng bản bình luận không SĐT cho mọi nhóm.")
        if rr["chan_den"]:
            dong.append(f"Lưu ý: Facebook đang chặn bình luận đến {rr['chan_den']}.")
        dong.append(f"Hôm nay đã bình luận {rr['bai_hom_nay']}/{rr['tran']} bài (trần mỗi ngày).")
        self.ghi("rui_ro", vong, "\n".join(dong))

    def chot(self, qua: list[UngVien]) -> tuple[list[tuple[str, str]], vai_mod.GiamDoc | None]:
        """Giám đốc (AI nếu được, không thì theo thứ tự ưu tiên) chọn đề xuất trình chủ shop. Trả về (trạng thái, lý do)
        cho từng đề xuất trong `qua`, và lời của Giám đốc"""
        cho_phep = max(0, self.toi_da - luu_tru.dem_cho_duyet(self.db))
        gd = None
        if qua and cho_phep and self.bo_ai.con_luot():
            gd = vai_mod.giam_doc_chot(self.bo_ai, [u.dx for u in qua], cho_phep, self.boi)
            self._dem_luot(gd.nguon if gd else "")
        ket_qua, da_nhan = [], 0
        quyet_dinh = gd.quyet_dinh if gd and gd.quyet_dinh else None     # AI chỉ viết tóm tắt, không chọn gì -> theo ưu tiên
        for i in range(1, len(qua) + 1):
            quyet, ly_do = quyet_dinh.get(i, ("hoan", "Giám đốc chưa chọn đề xuất này")) if quyet_dinh else ("chap_nhan", "")
            if quyet == "chap_nhan" and da_nhan < cho_phep:
                da_nhan += 1
                ket_qua.append((luu_tru.CHO_DUYET, ly_do))
            elif quyet == "chap_nhan":
                ket_qua.append((luu_tru.HOAN, f"Đã đủ {self.toi_da} đề xuất chờ duyệt cùng lúc — hoãn sang lần sau"))
            else:
                ket_qua.append((luu_tru.HOAN, ly_do or "Giám đốc hoãn"))
        return ket_qua, gd

    def luu_de_xuat(self, ung_vien: list[UngVien], qua: list[UngVien], quyet: list[tuple[str, str]]) -> None:
        for u in ung_vien:
            if u.van_de:
                luu_tru.them_de_xuat(self.db, self.cuoc_id, u.dx, u.nguon, luu_tru.BI_CHAN, "; ".join(u.van_de), self.bay_gio)
        for u, (trang_thai, ly_do) in reversed(list(zip(qua, quyet))):   # đề xuất ưu tiên cao nhất có id lớn nhất: hiện đầu
            luu_tru.them_de_xuat(self.db, self.cuoc_id, u.dx, u.nguon, trang_thai, ly_do, self.bay_gio)

    def _viec_do_code_dung(self, vai: str, nguon: str, ten_viec: str, soan: Callable, co_viec: Callable,
                           dung_de_xuat: Callable) -> int:
        """Một bước "AI viết chữ, code dựng việc": soan() nhờ AI (tự kiểm tra hạn mức, không đủ điều kiện thì không gọi AI) ->
        nếu có chữ đạt kiểm tra thì code dựng đề xuất và Kiểm soát rủi ro soát lại -> lưu chờ duyệt (hoặc tự làm nếu công tắc
        bật, ở tu_lam). Không đề xuất chồng khi đề xuất cùng nguồn trước đó chưa được duyệt. Lỗi bất ngờ chỉ ghi vào biên bản,
        cuộc họp vẫn phải xong. Trả về số đề xuất chờ duyệt mới tạo (0 / 1)"""
        if any(d["nguon"] == nguon for d in luu_tru.liet_ke_de_xuat(self.db, trang_thai=luu_tru.CHO_DUYET)):
            self.ghi(vai, 1, f"Đang có {ten_viec} chờ bạn duyệt — chưa đề xuất thêm.")
            return 0
        try:
            kq = soan()
            self._dem_luot(kq.nguon)
            self.ghi(vai, 1, kq.ghi_chu)
            if not co_viec(kq):
                return 0
            dx = dung_de_xuat(kq)
            van_de = rao_chan.kiem_tra(dx, self.bc, self.so, self.gia, nguon=nguon)
            trang_thai = luu_tru.BI_CHAN if van_de else luu_tru.CHO_DUYET
            luu_tru.them_de_xuat(self.db, self.cuoc_id, dx, nguon, trang_thai, "; ".join(van_de), self.bay_gio)
            return 0 if van_de else 1
        except Exception as e:     # lỗi bất ngờ (CSDL khóa, AI sập…): chưa làm được bước này, nhưng cuộc họp vẫn phải xong
            log.exception("Bước “%s” bị lỗi", ten_viec)
            self.ghi(vai, 1, f"Chưa làm được bước {ten_viec} vì lỗi: {type(e).__name__}")
            return 0

    def viet_mau_ai(self) -> int:
        """Vai Nội dung nhờ AI viết thêm THẺ THÔNG SỐ NGẮN cho mẫu bình luận (người bán / SĐT / địa chỉ do code ghép, xem mau_ai.py)"""
        return self._viec_do_code_dung(
            "noi_dung", "mau_ai", "mẫu bình luận do AI viết",
            lambda: mau_ai.soan_mau(self.db, self.so, self.gia, self.bo_ai, self.bay_gio), lambda kq: bool(kq.mo_dau),
            lambda kq: mau_ai.de_xuat_tu_ket_qua(kq, self.hom_nay))

    def tim_nhom_ai(self) -> int:
        """Vai Săn khách nhờ AI đề xuất từ khóa tìm nhóm MỚI (bot đọc thêm, vẫn lọc nhóm theo luật của nó; xem nhom_ai.py)"""
        return self._viec_do_code_dung(
            "san_khach", "tu_khoa_ai", "từ khóa tìm nhóm do AI đề xuất",
            lambda: nhom_ai.soan_tu_khoa(self.db, self.truy_van_goc, self.bo_ai, self.bay_gio), lambda kq: bool(kq.tu_khoa),
            lambda kq: nhom_ai.de_xuat_tu_ket_qua(kq, self.hom_nay))

    def tu_lam(self) -> list[str]:
        """Công tắc "tự làm" bật VÀ đã hết quan sát: làm luôn các việc do LUẬT đề xuất vừa trình chủ shop (chữ của AI không bao
        giờ tự làm). Việc không làm được (vi phạm giới hạn…) vẫn nằm chờ duyệt, lý do ghi vào biên bản. Trả về tiêu đề việc đã làm"""
        if not luu_tru.duoc_tu_lam(self.db, self.hom_nay, self.ngay_quan_sat):
            return []
        da_lam = []
        for d in luu_tru.liet_ke_de_xuat(self.db, trang_thai=luu_tru.CHO_DUYET, cuoc_hop_id=self.cuoc_id):   # id lớn = ưu tiên cao
            if d["nguon"] not in hanh_dong.NGUON_TU_LAM or not d["tham_so"]:
                continue
            try:
                hanh_dong.lam_luon(self.db, d["id"], GHI_CHU_TU_LAM, self.dong_ho(), tu_dong=True,
                                   su_that_file=self.duong_dan_su_that, truy_van_goc=self.truy_van_goc)
            except (hanh_dong.KhongLamDuoc, ValueError, LookupError) as e:
                self.ghi("giam_doc", 1, f"Chưa tự làm được “{d['tieu_de']}”: {e}")
            except Exception as e:     # lỗi bất ngờ (CSDL khóa…): đề xuất vẫn chờ duyệt, cuộc họp vẫn phải xong
                log.exception("Tự làm “%s” bị lỗi", d["tieu_de"])
                self.ghi("giam_doc", 1, f"Chưa tự làm được “{d['tieu_de']}” vì lỗi: {type(e).__name__}")
            else:
                da_lam.append(d["tieu_de"])
        if da_lam:
            self.ghi("giam_doc", 1, "Đã tự làm (công tắc tự làm đang bật, đã hết quan sát): " + "; ".join(da_lam)
                     + ". Bạn hoàn tác được ở mục “Việc công ty đã làm”.")
        return da_lam

    def tom_tat(self, gd: vai_mod.GiamDoc | None, dem: dict) -> str:
        if gd and gd.tom_tat:
            return gd.tom_tat
        dau = ("Hôm nay không có AI khả dụng (hết lượt miễn phí hoặc chưa cài) — đề xuất chỉ lấy từ luật theo số liệu."
               if self.so_luot == 0 else "Tóm tắt tự động (Giám đốc AI không trả lời).")
        chu_y = [n["noi_dung"] for n in self.bc["nhan_xet"] if n["muc"] == "chu_y"][:3]
        return (f"{dau} {dem[luu_tru.CHO_DUYET]} đề xuất chờ bạn duyệt, {dem[luu_tru.HOAN]} hoãn, "
                f"{dem[luu_tru.BI_CHAN]} bị Kiểm soát rủi ro chặn." + (" Cần chú ý: " + " | ".join(chu_y) if chu_y else ""))

    def chay(self) -> None:
        ung_vien = self._soat(self.thu_de_xuat())
        self.nhan_xet_rui_ro(ung_vien, 1)
        sua = self.vong_sua(ung_vien)
        if sua:
            self.nhan_xet_rui_ro(sua, 2)
        ung_vien += sua
        qua = [u for u in ung_vien if not u.van_de]
        quyet, gd = self.chot(qua)
        self.luu_de_xuat(ung_vien, qua, quyet)
        so_mau_moi = self.viet_mau_ai() + self.tim_nhom_ai()
        da_lam = self.tu_lam()
        dem = {t: sum(1 for u in ung_vien if u.van_de) if t == luu_tru.BI_CHAN else sum(1 for q, _ in quyet if q == t)
               for t in (luu_tru.CHO_DUYET, luu_tru.HOAN, luu_tru.BI_CHAN)}
        dem[luu_tru.CHO_DUYET] += so_mau_moi - len(da_lam)
        tom_tat = self.tom_tat(gd, dem)
        if da_lam:
            tom_tat += f" Công ty đã tự làm {len(da_lam)} việc (xem mục Việc công ty đã làm)."
        self.ghi("giam_doc", 1, tom_tat)
        luu_tru.ket_thuc_cuoc_hop(self.db, self.cuoc_id, luu_tru.XONG, ", ".join(sorted(self.nguon_ai)), self.so_luot,
                                  tom_tat, self.bc["van_ban"], self.dong_ho())


def _tom_lai(db: Database, cuoc: dict, da_co: bool) -> dict:
    dem = {r["trang_thai"]: r["n"] for r in db.query(
        "SELECT trang_thai, COUNT(*) AS n FROM de_xuat WHERE cuoc_hop_id = ? GROUP BY trang_thai", (cuoc["id"],))}
    return {"id": cuoc["id"], "da_co": da_co, "trang_thai": cuoc["trang_thai"], "tom_tat": cuoc["tom_tat"],
            "so_cho_duyet": dem.get(luu_tru.CHO_DUYET, 0), "so_bi_chan": dem.get(luu_tru.BI_CHAN, 0),
            "so_hoan": dem.get(luu_tru.HOAN, 0)}


def _cuoc_dang_co(db: Database, ngay: str, bay_gio: datetime) -> dict | None:
    """Cuộc họp của ngày đã xong, hoặc đang họp chưa quá lâu (kẹt do máy tắt giữa chừng thì không tính)"""
    for c in luu_tru.cuoc_hop_cua_ngay(db, ngay):
        con_dang_hop = c["trang_thai"] == luu_tru.DANG_HOP and bay_gio - datetime.strptime(
            c["bat_dau"], luu_tru.DINH_DANG_GIO) < timedelta(minutes=lich.PHUT_CHO_THU_LAI)
        if c["trang_thai"] == luu_tru.XONG or con_dang_hop:
            return c
    return None


def hop(db: Database, config, duong_dan_su_that: str, hom_nay: date, bo_ai, thu_muc_bao_cao: str | None = None,
        bay_gio: datetime | None = None, ep: bool = False, logger: logging.Logger | None = None,
        dong_ho: Callable[[], datetime] | None = None) -> dict:
    """Họp sáng cho ngày `hom_nay`. Hôm nay đã họp thì trả lại cuộc họp đó (da_co=True) trừ khi ep=True. `dong_ho` = đồng hồ
    thật để ghi giờ kết thúc (mặc định dùng `bay_gio`). Cuộc họp hỏng — kể cả bị ngắt bằng Ctrl+C — được ghi trạng thái
    'loi' rồi ném lại lỗi để nơi gọi biết. Trả về {id, da_co, trang_thai, tom_tat, so_cho_duyet, so_bi_chan, so_hoan}"""
    luu_tru.ensure_schema(db)
    hanh_dong.ensure_schema(db)
    bay_gio = bay_gio or datetime.combine(hom_nay, GIO_HOP_MAC_DINH)
    dong_ho = dong_ho or (lambda: bay_gio)
    ngay = hom_nay.strftime("%Y-%m-%d")
    dang_co = None if ep else _cuoc_dang_co(db, ngay, bay_gio)
    if dang_co:
        return _tom_lai(db, dang_co, da_co=True)
    cuoc_id = luu_tru.tao_cuoc_hop(db, ngay, bay_gio)
    try:
        luu_tru.ghi_bat_dau_quan_sat(db, ngay)
        _CuocHop(db, config, duong_dan_su_that, hom_nay, bo_ai, thu_muc_bao_cao, bay_gio, cuoc_id, dong_ho).chay()
    except BaseException as e:    # kể cả KeyboardInterrupt: cuộc họp dở không được để mãi ở trạng thái "đang họp"
        luu_tru.ket_thuc_cuoc_hop(db, cuoc_id, luu_tru.LOI, "", 0, "", "", dong_ho(), loi=f"{type(e).__name__}: {e}"[:500])
        if isinstance(e, Exception):
            (logger or log).exception("Cuộc họp sáng bị lỗi")
        raise
    return _tom_lai(db, luu_tru.cuoc_hop(db, cuoc_id), da_co=False)
