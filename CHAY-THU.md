# Chạy thử script — copy từng lệnh vào terminal VS Code

Mở terminal tại `D:\QC-Facebook`, kích hoạt môi trường ảo trước (đầu dòng phải hiện `(.venv)`):

```powershell
.venv\Scripts\Activate.ps1
```

---

## Bước 1 — Mở web quản lý

Bấm đúp **`mo-web.bat`**, hoặc chạy:

```powershell
python web.py
```

Rồi mở **http://127.0.0.1:5000**. Ở đây đã có 3 bài bình luận trước đây (trạng thái *Bản cũ*).

---

## Bước 2 — Thử gửi 3 bình luận vào 1 bài

Chọn 1 bài bất kỳ, ví dụ bài của chính bạn hoặc một bài tìm mua màn hình. Mở bài → bấm vào **thời gian đăng** → copy link:

```powershell
python main.py testcomment https://www.facebook.com/groups/manhinhhanoi/posts/DÁN_SỐ_BÀI_VIẾT_VÀO_ĐÂY/
```

Theo dõi Chrome:

- [ ] Gửi lần lượt **3 bình luận**, mỗi bình luận đủ 5 dòng và kèm **đúng ảnh** sản phẩm
- [ ] Terminal báo `[1/3] Đã đăng`, `[2/3] Đã đăng`, `[3/3] Đã đăng`
- [ ] Trên web: bài hiện ra, bấm vào thấy 3 bình luận + ảnh chụp màn hình

Chỉ gửi 1 bình luận: thêm số ở cuối lệnh (`... 2` = chỉ bình luận MSI G274QPF E2).

---

## Bước 3 — Quét các nhóm & tự bình luận (1 lượt)

```powershell
python main.py watch
```

Script chạy **1 vòng**: lần lượt từng nhóm Hà Nội theo thứ tự ưu tiên, quét **hết bài trong 24 giờ** về
**màn hình** (trước) và **PC** (bỏ qua bài laptop), bình luận hết rồi sang nhóm sau; cuối vòng tự tham gia nhóm chưa tham gia. Terminal sẽ hiện:

```
→ [1/24] Quét: CHỢ LAPTOP-MÁY TÍNH CŨ -HÀ NỘI
  3 bài mới chưa bình luận (chủ đề: Màn hình, PC)
  ★ [1/3] Màn hình — bài 1320 phút trước: 'Giá: 3tr990đ Màn hình Xiaomi G34WQi …'
  [1] Đã đăng (Đầy đủ)
  [2] Đã đăng (Đầy đủ)
  [3] Đã đăng (Đầy đủ)
  ✓ Hoàn tất: https://www.facebook.com/groups/336669676188888/posts/…/
…
→ [17/24] Quét: Chợ PC & Gaming Gear Hà Nội - Build PC
  ↷ Chưa tham gia nhóm — sẽ tự tham gia cuối vòng
…
=== Tự tham gia 8 nhóm chưa tham gia ===
→ Tham gia: Chợ PC & Gaming Gear Hà Nội - Build PC
  ➕ Tự tham gia nhóm: Chờ duyệt — điền 'ok' vào 3 ô, tick 1 ô; đã gửi yêu cầu, chờ quản trị viên duyệt
Kết quả vòng: 16 nhóm, 12 bài mới, 12 bài đã bình luận | Hôm nay: 29 bài
```

Đồng thời web cập nhật theo.

---

## Bước 4 — Chạy nền

Bấm đúp **`chay-ngam.bat`**: script chạy vòng nối vòng (từng nhóm bình luận hết bài mới → tham gia nhóm → quét lại),
đăng bài theo giờ trong `schedule.xlsx` xen giữa, và web tự mở.
Đóng cửa sổ thu nhỏ "QC-Facebook" để dừng, hoặc bấm **Tạm dừng** trên web.

---

## Thử đăng bài theo lịch (không bắt buộc)

```powershell
python main.py test https://www.facebook.com/groups/manhinhhanoi/
```

Đăng bài đầu tiên trong `data/schedule.xlsx` vào nhóm đó. Nhóm này bắt buộc bài đăng ghi rõ **tình trạng màn hình**.

---

## Gặp lỗi?

Chụp ảnh terminal gửi lại. Nhật ký đầy đủ nằm ở `logs/app.log`.

---

## 24 nhóm Hà Nội script đang dùng

Có thể thay link bất kỳ dưới đây vào lệnh `python main.py test <link>`.

| # | Tên nhóm | Loại | Link |
|---|---|---|---|
| 1 | MUA BÁN MÀN HÌNH MÁY TÍNH HÀ NỘI ✔ đã tham gia | Màn hình | https://www.facebook.com/groups/manhinhhanoi/ |
| 2 | Chợ Màn Hình Máy Tính Giá Rẻ Hà Nội ✅ | Màn hình | https://www.facebook.com/groups/690633162414839/ |
| 3 | MUA BÁN MÀN HÌNH MÁY TÍNH HÀ NỘI | Màn hình | https://www.facebook.com/groups/700172005910616/ |
| 4 | CHỢ MÀN HÌNH MÁY TÍNH HÀ NỘI | Màn hình | https://www.facebook.com/groups/httpswww.facebook.comhotline0971.706.662loca/ |
| 5 | NHÓM THANH LÝ MÁY TÍNH PC CŨ – MUA BÁN MÀN HÌNH MÁY TÍNH PC CŨ HÀ NỘI | Màn hình | https://www.facebook.com/groups/676007766618897/ |
| 6 | CHỢ LAPTOP-MÁY TÍNH CŨ -HÀ NỘI | PC | https://www.facebook.com/groups/336669676188888/ |
| 7 | Chợ Máy Tính Gaming Hà Nội | PC | https://www.facebook.com/groups/laptoptruongtho.c0m/ |
| 8 | CHỢ LAPTOP-MÁY TÍNH CŨ -HÀ NỘI✅ | PC | https://www.facebook.com/groups/483746292018077/ |
| 9 | Trao Đổi Máy Tính, Linh Kiện LapTop Hà Nội | PC | https://www.facebook.com/groups/381481045932285/ |
| 10 | Chợ PC & Gaming Gear Hà Nội | PC | https://www.facebook.com/groups/3829672663929073/ |
| 11 | CHỢ MÁY TÍNH CŨ - LÊ THANH NGHỊ HÀ NỘI | PC | https://www.facebook.com/groups/1172196739532204/ |
| 12 | Chợ Mua Bán Máy Tính Cũ HÀ NỘI | PC | https://www.facebook.com/groups/757160182464675/ |
| 13 | Chợ Máy tính Hà Nội ở đây | PC | https://www.facebook.com/groups/laptoppcre/ |
| 14 | Chợ PC & Gaming Gear Hà Nội - Build PC | PC | https://www.facebook.com/groups/1137172986692496/ |
| 15 | Máy Tính Laptop Cũ Giá Rẻ tại Hà Nội | PC | https://www.facebook.com/groups/laptopcugiare.vn/ |
| 16 | CHỢ MÁY TÍNH- LAPTOP -GIÁ RẺ- HÀ NỘI | PC | https://www.facebook.com/groups/974300370619016/ |
| 17 | Chợ máy tính - linh kiện PC Hà Nội ✅ | PC | https://www.facebook.com/groups/chomaytinhlinhkienpchanoi/ |
| 18 | Máy Tính Cũ Hà Nội | PC | https://www.facebook.com/groups/3449022191815450/ |
| 19 | Máy Tính- Lap Top Hà Nội | PC | https://www.facebook.com/groups/1546768218936637/ |
| 20 | Chợ máy tính Hà Nội | PC | https://www.facebook.com/groups/thanhlydocusinhvienhanoi/ |
| 21 | Chợ Mua Bán PC, Laptop, Linh Kiện Hà Nội | PC | https://www.facebook.com/groups/466202197262756/ |
| 22 | Chợ Mua Bán Laptop - PC Gaming Hà Nội | PC | https://www.facebook.com/groups/1398923880689298/ |
| 23 | Linh Kiện PC Laptop Giá Tốt Nhất Hà Nội | PC | https://www.facebook.com/groups/1750134845261652/ |
| 24 | Mua Bán Máy Tính Cũ Hà Nội | PC | https://www.facebook.com/groups/maytinhducanhpc/ |
