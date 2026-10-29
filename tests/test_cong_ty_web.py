"""API web của tab Công ty AI: ghi khách, báo cáo, sổ sự thật."""
import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask

from cong_ty import de_xuat, hanh_dong, luu_tru, web_api
from modules.db import Database

HOM_NAY = date(2026, 10, 24)


@pytest.fixture
def client(tmp_path):
    cfg = SimpleNamespace(MAX_COMMENTED_POSTS_PER_DAY=40, SU_THAT_FILE=str(tmp_path / "su-that.md"),
                          BAO_CAO_DIR=str(tmp_path / "bao_cao"))
    app = Flask(__name__)
    database = Database(str(tmp_path / "t.db"))
    app.register_blueprint(web_api.tao_blueprint(database, cfg, hom_nay=lambda: HOM_NAY,
                                                 bay_gio=lambda: datetime(2026, 10, 24, 9, 0)))
    khach_web = app.test_client()
    khach_web.db = database
    khach_web.su_that_file = cfg.SU_THAT_FILE
    return khach_web


def them_de_xuat(client, trang_thai="cho_duyet"):
    dx = de_xuat.chuan_hoa("san_khach", {"loai": "uu_tien_nhom", "tieu_de": "Giảm ưu tiên nhóm A", "noi_dung": "Nhóm A",
                                         "vi_sao": "quét 624 lần", "ky_vong": "x", "rui_ro": "y", "ngay_do": 7}, HOM_NAY)
    cuoc = luu_tru.tao_cuoc_hop(client.db, "2026-10-24", datetime(2026, 10, 24, 7, 0))
    return luu_tru.them_de_xuat(client.db, cuoc, dx, "luat", trang_thai, "", datetime(2026, 10, 24, 7, 1))


def test_add_then_list_customers(client):
    r = client.post("/api/congty/khach", json={"ngay": "2026-10-24", "loai": "Gọi", "so_luong": 2, "nguon": "Nhóm A"})
    assert r.status_code == 200 and r.get_json()["id"] > 0
    j = client.get("/api/congty/khach?days=30").get_json()
    assert j["rows"][0]["loai"] == "Gọi" and j["tong"]["2026-10-24"]["Gọi"] == 2


def test_bad_entry_gets_a_vietnamese_error(client):
    r = client.post("/api/congty/khach", json={"ngay": "2026-10-24", "loai": "Hỏi giá"})
    assert r.status_code == 400 and "loại" in r.get_json()["error"].lower()


def test_non_json_body_is_a_400_not_a_crash(client):
    assert client.post("/api/congty/khach", data="x", content_type="text/plain").status_code == 400


def test_customer_days_filter_is_validated(client):
    assert client.get("/api/congty/khach?days=abc").status_code == 400


def test_delete_customer(client):
    new_id = client.post("/api/congty/khach", json={"ngay": "2026-10-24", "loai": "Mua"}).get_json()["id"]
    assert client.delete(f"/api/congty/khach/{new_id}").status_code == 200
    assert client.delete(f"/api/congty/khach/{new_id}").status_code == 404


def test_report_endpoint_returns_the_report(client):
    j = client.get("/api/congty/baocao").get_json()
    assert j["van_ban"] and j["hom_nay"] == "2026-10-24"


def test_report_endpoint_accepts_a_date_and_rejects_garbage(client):
    assert client.get("/api/congty/baocao?date=2026-10-20").get_json()["hom_nay"] == "2026-10-20"
    assert client.get("/api/congty/baocao?date=abc").status_code == 400


def test_fact_sheet_template_is_created_and_reported(client, tmp_path):
    j = client.get("/api/congty/suthat").get_json()
    assert (tmp_path / "su-that.md").exists() and "Địa chỉ" in j["chua_dien"]
    assert j["duong_dan"].endswith("su-that.md")


def test_unicode_digits_in_days_are_a_400_not_a_crash(client):
    assert client.get("/api/congty/khach?days=%C2%B2").status_code == 400


def test_dates_far_in_the_past_are_a_400_not_a_crash(client):
    assert client.get("/api/congty/baocao?date=0001-01-05").status_code == 400


def test_report_of_a_past_date_treats_that_day_as_complete(client):
    j = client.get("/api/congty/baocao?date=2026-10-20").get_json()
    assert j["chuoi"][-1]["ngay"] == "2026-10-20" and j["chuoi"][-1]["chua_het"] is False


def test_deleting_a_huge_id_is_a_404(client):
    assert client.delete("/api/congty/khach/99999999999999999999").status_code == 404


def test_blueprint_survives_an_unwritable_fact_sheet_path(tmp_path):
    la_file = tmp_path / "la-file"
    la_file.write_text("x", encoding="utf-8")
    cfg = SimpleNamespace(MAX_COMMENTED_POSTS_PER_DAY=40, SU_THAT_FILE=str(la_file / "su-that.md"))
    assert web_api.tao_blueprint(Database(str(tmp_path / "t.db")), cfg) is not None


def test_meeting_endpoint_describes_the_company_state(client):
    j = client.get("/api/congty/hop").get_json()
    assert set(j) >= {"gan_nhat", "cho_duyet", "lich_su", "ai", "che_do", "dang_cho_hop"}
    assert j["gan_nhat"] is None and j["cho_duyet"] == [] and j["che_do"]["ten"] == "quan_sat"


def test_meeting_request_is_remembered_for_the_meeting_window(client):
    assert client.post("/api/congty/hop").status_code == 200
    assert client.get("/api/congty/hop").get_json()["dang_cho_hop"] is True


def test_owner_can_approve_a_proposal_then_mark_it_done(client):
    dx_id = them_de_xuat(client)
    j = client.get("/api/congty/hop").get_json()
    assert [d["id"] for d in j["cho_duyet"]] == [dx_id] and j["gan_nhat"]["de_xuat"][0]["id"] == dx_id
    assert client.post(f"/api/congty/dexuat/{dx_id}", json={"quyet_dinh": "da_duyet", "ghi_chu": "ok"}).status_code == 200
    j = client.get("/api/congty/hop").get_json()
    assert j["cho_duyet"] == [] and j["lich_su"][0]["trang_thai"] == "da_duyet"
    assert client.post(f"/api/congty/dexuat/{dx_id}", json={"quyet_dinh": "da_lam"}).status_code == 200


def test_deciding_wrongly_gets_a_clear_error(client):
    dx_id = them_de_xuat(client)
    assert client.post(f"/api/congty/dexuat/{dx_id}", json={"quyet_dinh": "xoa_het"}).status_code == 400
    assert client.post(f"/api/congty/dexuat/{dx_id}", data="x", content_type="text/plain").status_code == 400
    assert client.post("/api/congty/dexuat/99999", json={"quyet_dinh": "da_duyet"}).status_code == 404
    bi_chan = them_de_xuat(client, "bi_chan")
    assert client.post(f"/api/congty/dexuat/{bi_chan}", json={"quyet_dinh": "da_duyet"}).status_code == 409


def test_meeting_requests_cannot_pile_up_or_be_spammed(client):
    assert client.post("/api/congty/hop").status_code == 200
    assert client.post("/api/congty/hop").status_code == 409          # đã có yêu cầu đang chờ


def test_meeting_request_is_refused_while_a_meeting_is_running_but_not_when_it_is_stuck(client):
    luu_tru.tao_cuoc_hop(client.db, "2026-10-24", datetime(2026, 10, 24, 8, 50))     # đang họp (giờ trong fixture: 9:00)
    assert client.post("/api/congty/hop").status_code == 409


def test_a_meeting_stuck_for_hours_does_not_block_new_requests(client):
    luu_tru.tao_cuoc_hop(client.db, "2026-10-24", datetime(2026, 10, 24, 6, 0))
    assert client.post("/api/congty/hop").status_code == 200


def test_meetings_are_capped_per_day(client):
    for _ in range(web_api.HOP_TOI_DA_MOI_NGAY):
        luu_tru.tao_cuoc_hop(client.db, "2026-10-24", datetime(2026, 10, 24, 7, 0))
    assert client.post("/api/congty/hop").status_code == 409


def test_front_end_script_is_served(client):
    r = client.get("/congty/app.js")
    assert r.status_code == 200 and "javascript" in r.content_type


# ---------- Giai đoạn 3: làm luôn, nhật ký việc đã làm, hoàn tác, công tắc tự làm ----------
def them_mau(client, so_mau=12):
    san_pham = client.db.add_product(name="MSI G274QPF", price="2.500.000đ")
    return [client.db.add_variant(san_pham, f"Mẫu {i}", "") for i in range(so_mau)]


def them_viec_tat_mau(client, *ids, nguon="luat"):
    dx = replace(de_xuat.chuan_hoa("noi_dung", {"loai": "bat_tat_mau", "tieu_de": f"Tắt mẫu {ids}", "noi_dung": "Tắt vài mẫu",
                                               "vi_sao": "25 bình luận bị chặn", "ngay_do": 7}, HOM_NAY),
                 tham_so=json.dumps({"hanh_dong": "tat_mau", "variant_ids": list(ids)}))
    cuoc = luu_tru.tao_cuoc_hop(client.db, "2026-10-24", datetime(2026, 10, 24, 7, 0))
    return luu_tru.them_de_xuat(client.db, cuoc, dx, nguon, "cho_duyet", "", datetime(2026, 10, 24, 7, 1))


def dang_bat(client):
    return {v["id"] for v in client.db.variants(active_only=True)}


def test_do_it_now_carries_out_the_action_and_lists_it_in_the_log(client):
    ids = them_mau(client)
    dx_id = them_viec_tat_mau(client, ids[0], ids[1])
    r = client.post(f"/api/congty/dexuat/{dx_id}", json={"quyet_dinh": "lam_luon", "ghi_chu": "ok"})
    nhat_ky_id = r.get_json()["nhat_ky_id"]
    assert r.status_code == 200 and r.get_json()["ok"] is True
    j = client.get("/api/congty/hop").get_json()
    assert j["cho_duyet"] == [] and j["lich_su"][0]["trang_thai"] == "da_lam"
    viec = j["viec_da_lam"]
    assert [v["id"] for v in viec] == [nhat_ky_id] == [n["id"] for n in hanh_dong.liet_ke(client.db)]
    assert viec[0]["de_xuat_id"] == dx_id and viec[0]["tieu_de"] and viec[0]["variant_ids"] == [ids[0], ids[1]]
    assert dang_bat(client) == set(ids) - {ids[0], ids[1]}


def test_do_it_now_gives_clear_errors_and_changes_nothing(client):
    ids = them_mau(client, 11)
    assert client.post("/api/congty/dexuat/99999", json={"quyet_dinh": "lam_luon"}).status_code == 404
    r = client.post(f"/api/congty/dexuat/{them_de_xuat(client)}", json={"quyet_dinh": "lam_luon"})      # không có việc tự làm
    assert r.status_code == 409 and "tay" in r.get_json()["error"]
    r = client.post(f"/api/congty/dexuat/{them_viec_tat_mau(client, ids[0], ids[1])}", json={"quyet_dinh": "lam_luon"})
    assert r.status_code == 409 and "10" in r.get_json()["error"]                                       # còn 9 < 10 mẫu
    r = client.post(f"/api/congty/dexuat/{them_viec_tat_mau(client, ids[2], nguon='ai')}", json={"quyet_dinh": "lam_luon"})
    assert r.status_code == 409 and "luật" in r.get_json()["error"]                                     # chữ của AI
    assert len(dang_bat(client)) == 11 and client.get("/api/congty/hop").get_json()["viec_da_lam"] == []


def test_undo_turns_the_variants_back_on_and_cannot_be_repeated(client):
    ids = them_mau(client)
    r = client.post(f"/api/congty/dexuat/{them_viec_tat_mau(client, ids[0])}", json={"quyet_dinh": "lam_luon"})
    nhat_ky_id = r.get_json()["nhat_ky_id"]
    assert client.post(f"/api/congty/nhatky/{nhat_ky_id}/hoantac").status_code == 200
    assert dang_bat(client) == set(ids)
    assert client.get("/api/congty/hop").get_json()["viec_da_lam"][0]["hoan_tac_luc"]
    assert client.post(f"/api/congty/nhatky/{nhat_ky_id}/hoantac").status_code == 409
    assert client.post("/api/congty/nhatky/99999/hoantac").status_code == 404
    assert client.post(f"/api/congty/nhatky/{10 ** 30}/hoantac").status_code == 404


def test_the_self_acting_switch_stays_locked_until_observation_is_over(client):
    tu_lam = client.get("/api/congty/hop").get_json()["tu_lam"]
    assert tu_lam["bat"] is False and tu_lam["mo_khoa"] is False
    r = client.post("/api/congty/tulam", json={"bat": True})
    assert r.status_code == 409 and "quan sát" in r.get_json()["error"]
    assert client.get("/api/congty/hop").get_json()["tu_lam"]["bat"] is False
    client.db.set_setting("cong_ty_bat_dau", (HOM_NAY - timedelta(days=8)).strftime("%Y-%m-%d"))
    assert client.get("/api/congty/hop").get_json()["tu_lam"]["mo_khoa"] is True
    assert client.post("/api/congty/tulam", json={"bat": True}).status_code == 200
    assert client.get("/api/congty/hop").get_json()["tu_lam"]["bat"] is True
    assert client.post("/api/congty/tulam", json={"bat": False}).status_code == 200                    # tắt thì luôn được
    assert client.get("/api/congty/hop").get_json()["tu_lam"]["bat"] is False


SO_TEXT = ("## Thông tin cửa hàng\nĐịa chỉ: 64 Cầu Diễn, Hà Nội\nSố điện thoại: 0902 189 751\nNgười bán: Hoàng Văn Dũng\n\n## Chính sách\n"
           "Bảo hành: Tháng đầu lỗi 1 đổi 1\n")
MAU_VIET_TAY = "MSI G2712F – 27 inch 2K · 180Hz · 1ms – Rapid IPS · Adaptive-Sync · HDR 400\nDũng-0902189751-64 Cầu Diễn"
MO_DAU = "Mã màn: MSI G2712F\nThông số: 27 inch 2K · 180Hz · 1ms\nCông nghệ: Rapid IPS · Adaptive-Sync"


def them_viec_them_mau(client, san_pham_id, *mo_dau):
    dx = replace(de_xuat.chuan_hoa("noi_dung", {"loai": "mau_moi", "tieu_de": "Thêm mẫu do AI viết", "noi_dung": "\n".join(mo_dau),
                                               "vi_sao": "mẫu AI đang bật 0/9", "ngay_do": 7}, HOM_NAY),
                 tham_so=json.dumps({"hanh_dong": "them_mau", "san_pham_id": san_pham_id, "mo_dau": list(mo_dau)},
                                    ensure_ascii=False))
    cuoc = luu_tru.tao_cuoc_hop(client.db, "2026-10-24", datetime(2026, 10, 24, 7, 0))
    return luu_tru.them_de_xuat(client.db, cuoc, dx, "mau_ai", "cho_duyet", "", datetime(2026, 10, 24, 7, 1))


def test_do_it_now_adds_ai_written_comments_and_the_log_can_undo_them(client):
    pid = client.db.add_product(name="MSI G2712F 27 inch", price="2.500.000đ")
    client.db.add_variant(pid, MAU_VIET_TAY, "")
    with open(client.su_that_file, "w", encoding="utf-8") as f:
        f.write(SO_TEXT)
    r = client.post(f"/api/congty/dexuat/{them_viec_them_mau(client, pid, MO_DAU)}", json={"quyet_dinh": "lam_luon"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    moi = [v for v in client.db.variants(pid) if v["text"] != MAU_VIET_TAY]
    assert len(moi) == 1 and moi[0]["active"] == 1 and moi[0]["text"] == MO_DAU + "\nDũng-0902189751-64 Cầu Diễn"
    assert "Hoàng" not in moi[0]["text"]                                        # không ghi họ tên đầy đủ
    viec = client.get("/api/congty/hop").get_json()["viec_da_lam"][0]
    assert viec["hanh_dong"] == "them_mau" and viec["variant_ids"] == [moi[0]["id"]]
    assert viec["mo_ta"] == [MO_DAU]                                          # nhật ký cho đọc lại đúng chữ AI đã viết
    assert client.post(f"/api/congty/nhatky/{r.get_json()['nhat_ky_id']}/hoantac").status_code == 200
    assert [v["active"] for v in client.db.variants(pid) if v["id"] == moi[0]["id"]] == [0]


def test_do_it_now_for_ai_written_comments_needs_a_filled_fact_sheet(client):
    pid = client.db.add_product(name="MSI G2712F 27 inch", price="2.500.000đ")
    client.db.add_variant(pid, MAU_VIET_TAY, "")                          # sổ sự thật mẫu: mọi mục còn "ĐIỀN"
    r = client.post(f"/api/congty/dexuat/{them_viec_them_mau(client, pid, MO_DAU)}", json={"quyet_dinh": "lam_luon"})
    assert r.status_code == 409 and "Sổ sự thật" in r.get_json()["error"]
    assert len(client.db.variants(pid)) == 1


def test_the_switch_rejects_garbage(client):
    assert client.post("/api/congty/tulam", json={"bat": "yes"}).status_code == 400
    assert client.post("/api/congty/tulam", json={}).status_code == 400
    assert client.post("/api/congty/tulam", data="x", content_type="text/plain").status_code == 400
