# Hướng dẫn chạy QC-Facebook (bản AdsPower) trên máy mới

Tài liệu này hướng dẫn **cài đặt và chạy bot từ đầu trên một máy Windows mới**, theo bản cập nhật
12/11/2026 (chạy qua trình duyệt chống phát hiện **AdsPower**, 1 cửa sổ, chạy chậm như người thật).
Dành cho người chưa từng cài, làm theo đúng thứ tự là chạy được.

> Tổng quan dự án: xem `README.md`. Chi tiết kỹ thuật cho AI/lập trình: xem `CLAUDE.md`.

---

## 1. Bản mới khác bản cũ chỗ nào

| | Bản cũ | Bản mới (12/11/2026) |
|---|---|---|
| Trình duyệt | Chrome thường (dễ lộ là bot) | **AdsPower** anti-detect: 1 vân tay + 1 IP riêng, giống người thật |
| Số cửa sổ | 2–3 cửa sổ chạy song song | **1 cửa sổ duy nhất** (an toàn nhất cho 1 tài khoản) |
| Mỗi bài | 5 bình luận + 5 ảnh | **1 bình luận + 1 ảnh ghép** (4 mẫu đang bán trong 1 ảnh) |
| Nội dung bình luận | Có SĐT/tên người bán | **Không SĐT/tên** trong chữ (liên hệ chỉ in trên ảnh) → đỡ bị tính spam |
| Tốc độ | Nhanh | **Chậm**: ~5 phút/bài, khởi động 8 bài/ngày rồi tăng dần |

**Vì sao:** chạy nhiều cửa sổ / nhiều bình luận / rải SĐT khắp nơi là các dấu hiệu spam mạnh nhất.
Bản mới đi hướng "1 tài khoản sạch, chạy chậm, giống người thật" để bảo vệ tài khoản lâu dài.

---

## 2. Chuẩn bị máy mới (cài 1 lần)

Cần cài sẵn:

1. **Windows 10/11.**
2. **Python 3.10 trở lên** — tải ở <https://www.python.org/downloads/>. Khi cài **nhớ tick "Add Python to PATH"**.
3. **Google Chrome** (AdsPower cần nhân Chrome).
4. **Git** — tải ở <https://git-scm.com/download/win> (để tải code về và cập nhật sau này).
5. **AdsPower** — tải ở <https://www.adspower.com/> → tạo tài khoản → đăng nhập. Gói **Free** là đủ (dùng được API mở trình duyệt).

---

## 3. Bước 1 — Tải code về

Mở **PowerShell** (hoặc Git Bash), chạy:

```powershell
cd D:\
git clone https://github.com/cry4ego/Qc-Facebook.git QC-Facebook
cd QC-Facebook
```

(Nếu đã có sẵn thư mục, cập nhật bản mới nhất bằng: `git pull`)

---

## 4. Bước 2 — Cài Python + thư viện

Trong thư mục `QC-Facebook`, **bấm đúp `cai-dat.bat`** (hoặc chạy trong PowerShell: `.\cai-dat.bat`).
File này tạo môi trường `.venv` và cài các thư viện cần thiết. Chờ cài xong.

> Lưu ý: `cai-dat.bat` có thể mở Chrome để đăng nhập Facebook theo cách cũ — **bước đó bỏ qua**,
> vì bản mới đăng nhập trong AdsPower (xem Bước 3). Cứ đóng cửa sổ Chrome đó / nhấn Enter cho qua.

---

## 5. Bước 3 — Cài và cấu hình AdsPower (quan trọng nhất)

### 5.1. Tạo hồ sơ (profile) cho tài khoản bot

1. Mở app **AdsPower** → bấm **"Hồ sơ mới"** (góc trên bên trái).
2. Tab **"Cài đặt chung"**:
   - **Tên:** đặt dễ nhớ, vd `FB-Bot`.
   - **Browser Kernel:** chọn **SunBrowser** (nền Chrome). ⚠️ KHÔNG chọn FlowerBrowser (nền Firefox) — bot sẽ không chạy.
   - **Thao tác hệ thống:** chỉ tick **Windows** (bỏ các hệ điều hành khác, để vân tay luôn là Windows cho khớp máy thật).
   - **Nhóm:** chọn "Chưa chia nhóm".
   - **Cookie:** để trống.
3. Tab **"Proxy"** → **Loại proxy: "Không Proxy (Kết nối mạng local)"** — dùng **IP nhà** của máy này.
   - Với **1 tài khoản**, IP nhà (dân cư Việt Nam) là tốt nhất và miễn phí.
   - Chỉ mua proxy riêng (ISP tĩnh Việt Nam) nếu chạy **nhiều tài khoản** hoặc muốn tách hẳn khỏi tài khoản cá nhân khác.
4. Tab **"Dấu vân tay":** để **mặc định hết** (AdsPower tự sinh; múi giờ/ngôn ngữ "Dựa trên IP" sẽ tự thành Việt Nam).
5. Bấm **OK**.

### 5.2. Bật API cục bộ (để bot điều khiển)

1. Vào menu **"API & MCP"** (bên trái).
2. **Tắt** công tắc **"Xác minh API"** (để bot gọi được mà không cần API Key — API chỉ chạy nội bộ trên máy nên an toàn).
3. Cổng mặc định là **50325** (không cần đổi).

### 5.3. Lấy số hồ sơ (để điền vào cấu hình)

1. Vào tab **"Hồ sơ"**.
2. Nhìn cột **"Số"** (số thứ tự) ở hàng hồ sơ vừa tạo — thường là **1**. Ghi nhớ số này.

### 5.4. Đăng nhập Facebook vào hồ sơ

1. Trong tab **"Hồ sơ"**, bấm **"Mở"** ở hàng hồ sơ bot → trình duyệt AdsPower mở ra.
2. Vào facebook.com → **đăng nhập tài khoản bot** (tài khoản sẽ dùng để bình luận).
3. Lần đầu đăng nhập trên trình duyệt mới, Facebook có thể hỏi **"xác minh đây là bạn"** (qua SĐT/email) — cứ làm theo để xác nhận. Đây là việc bình thường.
4. Đăng nhập xong để yên, không cần đóng.

> ⚠️ **Tuyệt đối không đăng nhập tài khoản CÁ NHÂN/chính vào hồ sơ bot này, và ngược lại.** Giữ 2 tài khoản
> ở 2 trình duyệt khác nhau để Facebook không liên kết chúng.

---

## 6. Bước 4 — Cấu hình `config.py`

Mở file `config.py` bằng Notepad (hoặc VS Code), tìm phần **AdsPower** (gần cuối file), đặt **số hồ sơ** của máy này
vào `"default"`:

```python
ADSPOWER = True
ADSPOWER_USER_IDS = {
    "default": "1",      # <-- SỐ hồ sơ AdsPower ở Bước 5.3 (thường là 1)
}
```

Các giá trị khác đã đặt sẵn an toàn, **không cần đổi**:
- `PARALLEL = False` (1 cửa sổ)
- `COMMENT_PRODUCTS_PER_POST = 1` (1 bình luận + 1 ảnh ghép/bài)
- `MAX_COMMENTED_POSTS_PER_DAY = 8` (khởi động nhẹ; tăng dần sau vài ngày nếu êm)
- `MIN_DELAY = 240`, `MAX_DELAY = 360` (~5 phút/bài)

Lưu file.

---

## 7. Bước 5 — Nạp nội dung bán hàng (ảnh ghép + bình luận)

Nội dung (4 mẫu màn đang bán, bình luận, ảnh) đã kèm sẵn trong repo. Chạy loader để ghép ảnh + nạp vào cơ sở dữ liệu:

```powershell
.\.venv\Scripts\python.exe tools\nap_asl_ghep.py
```

Loader sẽ: sao lưu CSDL cũ → ghép 4 ảnh bán hàng thành 1 ảnh `data/images/ghep-4-man-dang-ban.png` →
tạo 4 sản phẩm đang bật, mỗi mẫu 30 thẻ bình luận **không SĐT/tên** → tắt các sản phẩm cũ.

> Muốn đổi mẫu đang bán: sửa `dang_ban: true/false` trong `data/noi_dung_asl/noi-dung/cau-hinh.json` rồi chạy lại loader.

---

## 8. Bước 6 — Chạy và theo dõi

**Trước khi chạy, kiểm 2 thứ:**
1. App **AdsPower đang mở** (bot cần API của nó).
2. Hồ sơ bot **đã đăng nhập Facebook** (Bước 5.4).

**Chạy:**

```powershell
.\chay-ngam.bat
```

Rồi mở trình duyệt vào **<http://127.0.0.1:5000>** để theo dõi (tab **"Bình luận"**: tiến trình, nhật ký, bài đã bình luận).

Hoặc chạy để xem log trực tiếp (2 cửa sổ PowerShell):
```powershell
.\.venv\Scripts\python.exe web.py        # cửa sổ 1: web quản lý
.\.venv\Scripts\python.exe main.py       # cửa sổ 2: bot
```

**Dừng bot:** đóng cửa sổ **"QC-Facebook"**, hoặc bấm **"Tạm dừng"** trên web.

---

## 9. An toàn — đọc kỹ (nhất là tài khoản mới/quý)

- **Không chạy 2 máy cùng 1 tài khoản Facebook** — Facebook thấy 1 tài khoản ở 2 nơi là nghi ngay.
- **Khởi động nhẹ:** để `MAX_COMMENTED_POSTS_PER_DAY = 8` vài ngày đầu. Nếu êm, mỗi vài ngày tăng thêm ~5.
- **Theo dõi bài đầu:** xem 1–2 bình luận đầu đúng là **1 bình luận + ảnh ghép**, chữ không có SĐT/tên.
- **Thấy "Bị chặn" hoặc "Chờ duyệt" liên tục → tắt bot ngay**, nghỉ vài ngày rồi chạy lại nhẹ hơn.
- **Dùng tài khoản như người thật:** thỉnh thoảng tự lướt, like, nhắn tin bằng tay — đừng để tài khoản chỉ đi bình luận.
- **Không chia sẻ:** hồ sơ AdsPower (có phiên đăng nhập), file `.env` (nếu có). Các file này không nằm trong GitHub.

---

## 10. Vài tham số hay chỉnh (trong `config.py`, sửa xong khởi động lại bot)

| Tham số | Ý nghĩa | Mặc định |
|---|---|---|
| `MAX_COMMENTED_POSTS_PER_DAY` | Số bài tối đa mỗi ngày (0 = không giới hạn) | 8 |
| `COMMENT_PRODUCTS_PER_POST` | Số bình luận mỗi bài | 1 |
| `MIN_DELAY` / `MAX_DELAY` | Giãn cách giữa 2 bài (giây) | 240 / 360 |
| `MAX_POST_AGE_MINUTES` | Chỉ bình luận bài mới trong vòng (phút) | 360 |
| `ADSPOWER_USER_IDS["default"]` | Số/ID hồ sơ AdsPower của máy này | "1" |

> **Danh sách nhóm và nhóm ưu tiên** quản lý trên web (tab "Danh sách nhóm"), không nằm trong `config.py`.

---

## 11. Khắc phục nhanh

- **Bot báo lỗi gọi AdsPower / không mở được hồ sơ:** kiểm tra app AdsPower đang mở, đã tắt "Xác minh API", và số hồ sơ trong `config.py` đúng.
- **Mở trình duyệt gõ** `http://local.adspower.net:50325/status` **→ phải thấy** `{"code":0,"msg":"success"}` (API đang chạy).
- **Bot nói chưa đăng nhập Facebook:** mở hồ sơ trong AdsPower, đăng nhập lại tài khoản bot.
- **Cài lại thư viện:** chạy lại `cai-dat.bat`.
