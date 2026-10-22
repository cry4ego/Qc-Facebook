# Dự án nội dung bán màn hình MSI – ASL Workshop

Tài liệu này mô tả toàn bộ dự án để người hoặc AI đọc là hiểu và sửa được.
Dự án gồm hai phần:
1. **Ảnh bán hàng** 1920×1080 (16:9), nền trắng, có giá, cho 5 mã màn MSI.
2. **Nội dung chữ**: 30 bình luận mỗi mã, 10 bài đăng nhóm mỗi mã, xuất ra 4 file Word.

Nguyên tắc chung: **chỉ sửa nguồn, không sửa tay file kết quả.**
Sửa nguồn (`noi-dung/`, `mau-ban-hang.html`), sau đó chạy script để tạo lại kết quả (`Tai-lieu/`, `Anh-ban-hang/`).

---

## 1. Cấu trúc thư mục

```
Ảnh Màn-20-10/
├── CAU-TRUC-DU-AN.md            ← file này
│
├── noi-dung/                    ← NGUỒN nội dung chữ (sửa ở đây)
│   ├── cau-hinh.json            ← người bán, SĐT/Zalo, địa chỉ, bảo hành, giá, ảnh, câu ký tên
│   ├── binh-luan/               ← 30 bình luận cho mỗi mã
│   │   ├── g274qpx.md           (mã QPX-01 … QPX-30)
│   │   ├── g274qpf-e2.md        (QPF-01 … QPF-30)
│   │   ├── g274qrfw.md          (RFW-01 … RFW-30)
│   │   ├── g272qpf-e2.md        (G272-01 … G272-30)
│   │   └── mp273qp.md           (MP-01 … MP-30)
│   └── bai-dang/                ← 10 bài đăng cho mỗi mã (QPX-BD01 … BD10, …)
│       └── (cùng 5 tên file như trên)
│
├── tao-tai-lieu.py              ← tạo 4 file Word từ noi-dung/
├── Tai-lieu/                    ← KẾT QUẢ chữ (tạo tự động, không sửa tay)
│   ├── 1-Binh-luan-co-SDT-Zalo-dia-chi.docx
│   ├── 2-Binh-luan-chi-ten-nguoi-ban.docx
│   ├── 3-Bai-dang-ban-hang.docx
│   └── 4-Anh-kem-binh-luan.docx
│
├── mau-ban-hang.html            ← NGUỒN ảnh: mẫu ảnh 1920×1080, nội dung + giá trong biến MODELS
├── xuat-anh.ps1                 ← xuất 5 ảnh PNG từ mẫu (dùng Google Chrome chạy ngầm)
├── Anh-ban-hang/                ← KẾT QUẢ ảnh (tạo tự động)
│   ├── MSI-G274QPX-ASL-Workshop.png
│   ├── MSI-G274QPF-E2-ASL-Workshop.png
│   ├── MSI-G274QRFW-ASL-Workshop.png
│   ├── MSI-G272QPF-E2-ASL-Workshop.png
│   └── MSI-PRO-MP273QP-ASL-Workshop.png
│
├── assets/
│   ├── logo-asl.png             ← logo ASL Workshop đã tách nền (dùng trong ảnh)
│   ├── logo-asl-original.png    ← logo gốc
│   ├── g274qpx/ g274qpf-e2/ g274qrfw/ g272qpf-e2/ mp273qp/
│   │   └── img1.png … img5.png  ← ảnh sản phẩm gốc tải từ msi.com
│   └── img1…img5 (.png/.webp)   ← bản cũ của ảnh G274QPF E2, không còn file nào dùng, có thể xoá
│
└── MSI-G274QPF-E2-ASL-Workshop-nen-trang.png   ← bản cũ (nền trắng, chưa có giá), không còn dùng
```

### Bảng mã sản phẩm

| Mã file (`ma`) | Tên | Tiền tố bình luận | Tiền tố bài đăng | Giá không chân / giá bán | Có chân |
|---|---|---|---|---|---|
| g274qpx | MSI G274QPX | QPX-xx | QPX-BDxx | 2.750.000đ | 2.900.000đ |
| g274qpf-e2 | MSI G274QPF E2 | QPF-xx | QPF-BDxx | 2.500.000đ | 2.650.000đ |
| g274qrfw | MSI G274QRFW (trắng) | RFW-xx | RFW-BDxx | 2.500.000đ | — |
| g272qpf-e2 | MSI G272QPF E2 | G272-xx | G272-BDxx | 2.400.000đ | 2.550.000đ |
| mp273qp | MSI PRO MP273QP | MP-xx | MP-BDxx | 1.950.000đ | — |

Giá chuẩn nằm trong `noi-dung/cau-hinh.json` và trong biến `MODELS` của `mau-ban-hang.html` (xem mục 4).

---

## 2. Cách tạo lại kết quả

| Muốn làm gì | Sửa ở đâu | Chạy lệnh |
|---|---|---|
| Đổi giá, SĐT, địa chỉ, bảo hành, câu ký tên | `noi-dung/cau-hinh.json` | `python tao-tai-lieu.py` |
| Sửa / thêm bình luận | `noi-dung/binh-luan/<mã>.md` | `python tao-tai-lieu.py` |
| Sửa / thêm bài đăng | `noi-dung/bai-dang/<mã>.md` | `python tao-tai-lieu.py` |
| Sửa chữ / giá trên ảnh | `MODELS` trong `mau-ban-hang.html` | `powershell -ExecutionPolicy Bypass -File xuat-anh.ps1` |
| Sửa bố cục, màu ảnh | phần `<style>` trong `mau-ban-hang.html` | `powershell -ExecutionPolicy Bypass -File xuat-anh.ps1` |

Cần cài: Python 3 với các gói `python-docx` và `Pillow` (cho file Word); Google Chrome (cho ảnh).
Xem nhanh một ảnh: mở `mau-ban-hang.html?m=g274qpx` trong Chrome (thay `g274qpx` bằng mã khác).

---

## 3. Nội dung chữ (`noi-dung/` → `Tai-lieu/`)

### 3.1 `cau-hinh.json`

| Trường | Ý nghĩa |
|---|---|
| `cong_ty`, `nguoi_ban`, `sdt`, `zalo`, `dia_chi` | Thông tin liên hệ. Chỉ xuất hiện trong file 1, 3 và phần A của file 4 |
| `bao_hanh` | Chính sách bảo hành, viết chữ thường để chèn giữa câu (hiện là "tháng đầu lỗi 1 đổi 1") |
| `tinh_trang` | "Hàng công ty đã qua sử dụng" |
| `ket_bl_day_du` | Các câu ký tên có SĐT + địa chỉ, gắn xoay vòng vào cuối bình luận ở file 1 / 4A |
| `ket_bl_chi_ten` | Các câu ký tên chỉ có tên người bán, gắn vào cuối bình luận ở file 2 / 4B |
| `san_pham[]` | Mỗi mã màn: `ma`, `ten`, `tom_tat`, `gia`, `gia_co_chan`, `phu_thu_chan`, `anh`, `anh_goc`, `nguon` |
| `san_pham[].anh` | Ảnh bán hàng (có giá + SĐT + địa chỉ), dùng cho file 1, 3, 4A |
| `san_pham[].anh_goc` | Danh sách ảnh gốc MSI (không có liên hệ), xoay vòng cho bình luận file 2 / 4B |
| `san_pham[].gia_co_chan` | `null` nếu mã đó không có giá kèm chân (G274QRFW, MP273QP) |

### 3.2 File bình luận `binh-luan/<mã>.md`

```markdown
## QPX-01
Nội dung bình luận, có thể nhiều dòng. Giá {gia}, có chân {gia_co_chan}, BH {bao_hanh}.
```

Quy tắc:
- Mỗi bình luận bắt đầu bằng `## MÃ`. Mã không được trùng. Script sẽ cảnh báo nếu một mã màn có khác 30 bình luận.
- **Không ghi SĐT, Zalo, địa chỉ hay tên công ty trong thân bình luận.** Script tự gắn câu ký tên: bản có liên hệ cho file 1, bản chỉ tên cho file 2. Nếu thân bình luận dùng `{sdt}`, `{dia_chi}` hoặc có số điện thoại / "Cầu Diễn" / "ASL Workshop", script dừng và báo lỗi.
- Biến dùng được trong bình luận: `{gia}` `{gia_co_chan}` `{phu_thu_chan}` `{bao_hanh}` `{ten}`.
- Không dùng `{gia_co_chan}` / `{phu_thu_chan}` cho mã có giá trị `null`, nếu dùng script sẽ báo lỗi.
- Muốn một bình luận dùng ảnh riêng: thêm dòng `Ảnh: đường/dẫn/anh.png` trong bình luận đó. Ảnh này sẽ dùng cho cả bản có liên hệ lẫn bản chỉ tên, nên đừng chọn ảnh có in SĐT.
- Ghi chú trong `<!-- ... -->` bị bỏ qua.

### 3.3 File bài đăng `bai-dang/<mã>.md`

```markdown
## QPX-BD01 | Nhóm mua bán linh kiện PC Hà Nội
Nội dung bài... Liên hệ {nguoi_ban} – {sdt} – {dia_chi}
```

- Phần sau dấu `|` là kiểu nhóm nên đăng. Mỗi mã có 10 bài cho 10 kiểu nhóm khác nhau, để không đăng trùng nội dung.
- Bài đăng **có** liên hệ, viết bằng biến: `{nguoi_ban}` `{sdt}` `{zalo}` `{dia_chi}` `{cong_ty}`, cùng các biến giá ở trên.
- Ảnh đính kèm mặc định là `anh` của mã đó. Có thể đổi bằng dòng `Ảnh: ...`.

### 3.4 Bốn file Word kết quả (`Tai-lieu/`)

| File | Nội dung | Ảnh |
|---|---|---|
| `1-Binh-luan-co-SDT-Zalo-dia-chi.docx` | 150 bình luận (30 × 5 mã), cuối mỗi bình luận có SĐT/Zalo + địa chỉ | Ghi tên ảnh bán hàng ở đầu mỗi mã |
| `2-Binh-luan-chi-ten-nguoi-ban.docx` | Cùng 150 bình luận, chỉ ký tên người bán, không SĐT, không địa chỉ, không tên công ty | Ghi ảnh gốc MSI cho từng bình luận |
| `3-Bai-dang-ban-hang.docx` | 50 bài đăng (10 × 5 mã), mỗi bài ghi kiểu nhóm nên đăng, có giá + liên hệ | Ảnh bán hàng in sẵn ở đầu mỗi mã |
| `4-Anh-kem-binh-luan.docx` | Bảng: mỗi dòng = ảnh + 1 bình luận. Phần A dùng bản của file 1, phần B dùng bản của file 2 | A: ảnh bán hàng · B: ảnh gốc MSI |

File 1, 2 và 4 dùng chung mã bình luận (QPX-01…), tiện đánh dấu bình luận đã đăng.

### 3.5 `tao-tai-lieu.py` làm gì

1. Đọc `cau-hinh.json` và các file `.md`.
2. Thay biến `{...}` bằng giá trị thật. Gặp biến sai, biến không có giá trị, hoặc nội dung có icon/emoji thì báo lỗi.
3. Kiểm tra bản "chỉ tên người bán" không lộ SĐT, địa chỉ, tên công ty.
4. Nén ảnh sang JPEG rồi chèn vào Word (mỗi ảnh chỉ nhúng 1 lần nên file nhẹ).
5. Ghi 4 file vào `Tai-lieu/` (ghi đè bản cũ).

---

## 4. Ảnh bán hàng (`mau-ban-hang.html` → `Anh-ban-hang/`)

- `mau-ban-hang.html` là một trang HTML 1920×1080. Tham số `?m=<mã>` chọn mã màn cần hiển thị.
- Nội dung từng mã nằm trong biến JavaScript `MODELS` ở cuối file, gồm: `name`, `eyebrow`, `img`, `zoom` (phóng ảnh), `lead`, `bubbles` (4 vòng tròn thông số), `fit` (Phù hợp cho), `perks` (7 ưu điểm), `spec` (8 dòng thông số), `price` (`label`, `value`, `sub`).
- `xuat-anh.ps1` mở mẫu bằng Chrome chạy ngầm cho từng mã rồi chụp ra `Anh-ban-hang/<TÊN>-ASL-Workshop.png`.
- Bố cục: logo + nhãn "Hàng công ty đã qua sử dụng" + nhãn bảo hành ở trên; ảnh sản phẩm và 4 vòng thông số bên trái; tên, ưu điểm, bảng thông số bên phải; dải dưới cùng gồm ô giá đỏ, SĐT, địa chỉ.
- Màu thương hiệu lấy từ logo: xanh navy `#0a2a6b`, đỏ `#d0102e`, vàng `#ffc21a`. Font: Be Vietnam Pro (Google Fonts, cần mạng khi xuất ảnh).
- **Ảnh bán hàng có in SĐT và địa chỉ**, nên chỉ dùng với bình luận / bài đăng có liên hệ.

> ⚠️ **Giá đang nằm ở 2 nơi**: `noi-dung/cau-hinh.json` (cho chữ) và `MODELS` trong `mau-ban-hang.html` (cho ảnh).
> Khi đổi giá phải sửa cả hai, rồi chạy cả `python tao-tai-lieu.py` lẫn `xuat-anh.ps1`.

---

## 5. Thêm một mã màn mới (checklist)

1. Lấy thông số và công nghệ từ trang **chính thức của MSI** (`https://www.msi.com/Monitor/<MÃ>/Specification` và trang Overview). Nếu trang toàn cầu đã gỡ, dùng trang khu vực như `us.msi.com`.
2. Tải ảnh sản phẩm từ trang Gallery của MSI vào `assets/<mã>/img1.png …`.
3. Thêm mã vào `MODELS` trong `mau-ban-hang.html` và vào danh sách `$models` trong `xuat-anh.ps1`, rồi chạy `xuat-anh.ps1`. Mở ảnh kiểm tra xem ảnh sản phẩm có đè chữ không; nếu có thì chỉnh `zoom`.
4. Thêm mục vào `san_pham` trong `noi-dung/cau-hinh.json` (`anh` trỏ tới ảnh vừa xuất, `anh_goc` trỏ tới ảnh MSI).
5. Tạo `noi-dung/binh-luan/<mã>.md` (30 bình luận) và `noi-dung/bai-dang/<mã>.md` (10 bài), với tiền tố mã mới.
6. Chạy `python tao-tai-lieu.py`.

---

## 6. Quy tắc nội dung (cho người hoặc AI viết thêm)

- **Thông số và công nghệ chỉ lấy từ trang MSI**, ghi đúng số liệu (Hz, nits, % sRGB/DCI-P3, cổng, góc chỉnh chân đế). Không tự thêm tính năng mà trang MSI không ghi.
- Không hứa những điều người bán chưa xác nhận, ví dụ "như mới", "zin 100%", "ship toàn quốc", "số lượng có hạn". Tình trạng luôn ghi là "hàng công ty đã qua sử dụng".
- Giá luôn công khai, ghi rõ giá không chân / có chân. Bảo hành luôn ghi đúng chuỗi trong `bao_hanh`.
- Nói rõ cả điểm hạn chế để tạo tin tưởng, ví dụ: HDMI chỉ 144Hz, G274QRFW chỉ HDR Ready 300 nits, G272QPF E2 không có USB-C, MP273QP chỉ hợp game nhẹ.
- Không dùng "anh/chị" để gọi người bán (không đoán giới tính). Gọi bằng tên "Hoàng Văn Dũng".
- **Không dùng icon/emoji** (✅ 💰 📞 📍 🛡 ❓ ✔ …) trong bình luận, bài đăng hay câu ký tên. Gạch đầu dòng viết bằng `- `; thay icon bằng chữ, ví dụ "Giá:", "Bảo hành:", "SĐT:", "Địa chỉ:". Gặp icon, `tao-tai-lieu.py` sẽ dừng và báo vị trí.
- Các bình luận cùng mã phải khác nhau về góc độ (giá, bảo hành, thông số, chơi game, văn phòng, hỏi đáp, so sánh, danh sách emoji…) để không bị xem là spam.

---

## 7. Việc còn chờ người bán xác nhận

1. **Chân đế +150k có phải chân gốc MSI không?** Ảnh và nội dung đang ghi tính năng của chân gốc (nâng hạ 130mm, xoay, xoay dọc 90°). Nếu là chân khác, cần bỏ các tính năng này ở: `perks` "Chân đế (+150k)" trong `mau-ban-hang.html`; bình luận QPX-09, QPF-09, QPF-23, G272-08, G272-22; bài đăng QPX-BD05, QPX-BD10, QPF-BD05, QPF-BD10, G272-BD05, G272-BD09 (và các bài có nhắc "bản có chân").
2. **G274QRFW có bán kèm chân không?** Hiện chỉ có giá không chân 2.500.000đ, nên nội dung không nhắc chân đế.
3. **MP273QP giá 1.950.000đ đã gồm chân chưa?** Nội dung đang coi là có chân (có nhắc chân nâng hạ, xoay dọc).

---

## 8. Nguồn thông số

| Mã | Trang thông số | Trang công nghệ |
|---|---|---|
| G274QPX | https://www.msi.com/Monitor/G274QPX/Specification | https://www.msi.com/Monitor/G274QPX |
| G274QPF E2 | https://www.msi.com/Monitor/G274QPF-E2/Specification | https://www.msi.com/Monitor/G274QPF-E2 |
| G274QRFW | https://www.msi.com/Monitor/G274QRFW/Specification | https://us.msi.com/Monitor/G274QRFW |
| G272QPF E2 | https://www.msi.com/Monitor/G272QPF-E2/Specification | https://www.msi.com/Monitor/G272QPF-E2 |
| PRO MP273QP | https://www.msi.com/Business-Productivity-Monitor/PRO-MP273QP/Specification | https://www.msi.com/Business-Productivity-Monitor/PRO-MP273QP |
