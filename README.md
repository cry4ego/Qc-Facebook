# QC-Facebook — Tự động bình luận & đăng bài vào nhóm Facebook

Script Python dùng Selenium điều khiển Chrome (đã đăng nhập tài khoản của bạn) để:

1. **Theo dõi bài mới** trong các nhóm, chạy liên tục: lần lượt từng nhóm (nhóm Hà Nội đông thành viên, hoạt động mạnh
   trước) quét **hết bài đăng trong 24 giờ** về **màn hình** (ưu tiên) và **PC**, bỏ qua bài laptop, mỗi bài gửi **3 bình luận độc lập**, mỗi
   bình luận 1 sản phẩm kèm ảnh riêng. Cuối vòng **tự tham gia** nhóm chưa tham gia (điền "ok", tick hết), mỗi ngày **tự tìm nhóm mới theo
   từ khóa** (PC, màn hình, Hà Nội, setup pc, phụ kiện màn hình, đồ công nghệ, chợ đồ cũ 2nd), rồi quét lại
2. **Đăng bài theo lịch** vào các nhóm (`schedule.xlsx`)
3. **Lưu lại mọi hoạt động** (bài nào, bình luận gì, lúc mấy giờ, có bị chặn / chờ duyệt / bị xóa không, ảnh chụp màn hình)
   và hiển thị trên **web quản lý** http://127.0.0.1:5000

> ⚠️ **Cảnh báo:** Bình luận chào hàng tự động vào mọi bài vi phạm Điều khoản của Facebook và nội quy "không spam" của nhiều
> nhóm. Bạn có thể bị kick khỏi nhóm hoặc bị Facebook hạn chế bình luận / khóa tài khoản. Hãy giữ giới hạn thấp (mục 5).

---

## 🚀 Dùng hằng ngày

1. Bấm đúp **`chay-ngam.bat`**. Hai cửa sổ thu nhỏ sẽ chạy, và trình duyệt tự mở web quản lý
2. Xem kết quả trên web **http://127.0.0.1:5000**
3. Muốn dừng tạm thời thì bấm **Tạm dừng** trên web. Muốn tắt hẳn thì đóng cửa sổ terminal "QC-Facebook"

Chỉ muốn xem web mà không chạy script: bấm đúp **`mo-web.bat`**.

**Tự chạy khi bật máy:** nhấn `Win + R`, gõ `shell:startup`, Enter, rồi tạo shortcut của `chay-ngam.bat` vào thư mục vừa mở.

---

## 📁 Cấu trúc thư mục

```
QC-Facebook/
├── main.py                 # Script chính: chạy nền + các lệnh
├── web.py                  # Web quản lý (Flask) — http://127.0.0.1:5000 (bình luận, sản phẩm, danh sách nhóm)
├── web/index.html          # Giao diện web
├── config.py               # Cấu hình: khu vực, giới hạn, tần suất...
├── chay-ngam.bat           # Bấm đúp: chạy script + mở web
├── mo-web.bat              # Bấm đúp: chỉ mở web
├── CHAY-THU.md             # Các lệnh chạy thử
├── modules/
│   ├── watcher.py          # Quét bài mới trong nhóm, gửi 3 bình luận, kiểm tra lại
│   ├── commenter.py        # Gõ bình luận + gắn ảnh, nhận biết Đã đăng / Chờ duyệt / Bị chặn / Lỗi
│   ├── db.py               # Cơ sở dữ liệu SQLite (nhật ký)
│   ├── poster.py           # Đăng bài vào nhóm
│   ├── group_checker.py    # Kiểm tra / tham gia nhóm
│   ├── group_finder.py     # Tìm nhóm mới theo từ khóa
│   ├── group_lists.py      # Các file Excel danh sách nhóm (bật/tắt trên web)
│   ├── products.py         # Sản phẩm bình luận (thêm/sửa/bật/tắt trên web)
│   ├── image_manager.py, excel_reader.py
├── tools/import_groups.py  # nhom_facebook_man_hinh_PC.xlsx -> data/groups.xlsx
├── data/
│   ├── comments.txt        # 3 bình luận ban đầu (đã nhập vào tab Sản phẩm trên web)
│   ├── images/             # Ảnh sản phẩm
│   ├── group_lists/        # File Excel nhóm tải lên từ web
│   ├── groups.xlsx         # Danh sách nhóm (tạo từ nhom_facebook_man_hinh_PC.xlsx)
│   ├── schedule.xlsx       # Lịch đăng bài
│   ├── qc_facebook.db      # ★ Nhật ký đầy đủ (web đọc từ đây)
│   ├── nhat_ky_binh_luan.xlsx  # Bản Excel của nhật ký (tự cập nhật sau mỗi lượt quét)
│   └── screenshots/        # Ảnh chụp bài sau khi bình luận
├── logs/app.log
└── chrome_profile/         # Phiên đăng nhập Chrome (KHÔNG chia sẻ)
```

---

## 1️⃣ Cài đặt & đăng nhập (1 lần)

```powershell
cd D:\QC-Facebook
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py login      # đăng nhập Facebook trong Chrome rồi nhấn Enter
```

---

## 2️⃣ Tự động bình luận bài mới

Script chạy **liên tục theo vòng**. Mỗi vòng:

1. **Danh sách nhóm** = 24 nhóm Hà Nội trong `groups.xlsx` + nhóm **tự tìm theo từ khóa** (`groups_found.xlsx`, xem dưới).
   **Xếp thứ tự**: nhóm thuộc `PRIORITY_REGION` trước, rồi theo điểm = (hoạt động + số thành viên) × từ khóa trong tên
   (`GROUP_KEYWORDS`, mỗi từ khóa +25%) × **2 nếu tên có "màn hình"**, × 0,7 nếu tên chỉ nói laptop
2. **Lần lượt từng nhóm** (nhóm đông bài nhất trước):
   - mở nhóm, sắp xếp theo **Bài viết mới**, cuộn tới hết các bài đăng trong **24 giờ** (`MAX_POST_AGE_MINUTES`) —
     **không giới hạn số bài** (`MAX_POSTS_PER_GROUP = 0`), kể cả nhiều người đăng cùng lúc
   - **chỉ lấy bài màn hình và PC** (`COMMENT_TOPICS = ["Màn hình", "PC"]`), **bài màn hình bình luận trước**:
     - *Màn hình*: mua/bán/tìm màn hình, bài cần build PC **kèm màn hình**
     - *PC*: máy bàn, case, cấu hình, linh kiện, VGA, setup, bàn phím/chuột…
     - **bỏ qua** bài laptop (kể cả bài laptop ghi "màn 15.6", "165hz"), điện thoại, máy in…
     Bộ nhận diện nằm trong `modules/watcher.py` (`MONITOR_TOPIC`, `PC_TOPIC`, `LAPTOP_TOPIC`)
   - **bỏ qua** bài đã có trong nhật ký, bài do chính bạn đăng
   - bình luận **hết** các bài đó rồi mới sang nhóm sau
3. Mở bài, bỏ qua nếu đã có bình luận của bạn, rồi gửi lần lượt **3 bình luận** trong `data/comments.txt`, mỗi bình luận
   kèm ảnh riêng, cách nhau 15–40 giây
4. Sau mỗi bình luận, ghi nhận trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| **Đã đăng** | Bình luận hiện lên bài |
| **Bị từ chối · đã xóa** | Nhóm/Facebook gắn nhãn "Bị từ chối", script đã tự xóa (xem mục dưới) |
| **Chờ duyệt** | Facebook báo chờ quản trị viên duyệt, hoặc đã gửi nhưng không hiển thị |
| **Bị chặn** | Facebook báo bị chặn / hạn chế. Script **ngừng tự bình luận `BLOCK_COOLDOWN_HOURS` (6) giờ** |
| **Lỗi** | Không gửi được (ô bình luận lỗi, giao diện đổi...) |

5. Chụp màn hình bài sau khi bình luận (`data/screenshots/`)
6. **Cuối vòng: tự tham gia các nhóm chưa tham gia** (tối đa `JOIN_PER_DAY` = 20 nhóm/ngày). Nhóm có câu hỏi duyệt thành
   viên: điền **"ok"** (`JOIN_ANSWER`) vào mọi ô cần điền, **tick hết** các ô (đồng ý nội quy…), câu hỏi chọn 1 đáp án thì
   chọn đáp án đầu, rồi bấm Gửi. Nhóm cần quản trị viên duyệt thì bỏ qua tới khi được duyệt. Vòng sau sẽ bình luận các
   nhóm vừa vào. (Chưa là thành viên mà bình luận ở nhóm công khai thì bình luận nằm ở hàng "chờ quản trị viên phê duyệt",
   người khác không thấy — nên phải tham gia.)
7. Xong vòng → **quét lại ngay** từ nhóm đầu tiên. Vòng không có bài mới nào thì chờ `ROUND_IDLE_MINUTES` (5) phút.
   Bài trong lịch đăng (`schedule.xlsx`) đến giờ thì được đăng xen giữa, không phải chờ hết vòng. Script bị tắt giữa chừng
   thì bài đang bình luận dở được làm lại ở lần chạy sau
8. **Kiểm tra lại** sau ~1 giờ: mở lại bài, đếm bình luận của bạn còn hiển thị → `Còn đủ 3/3` / `Chỉ còn 1/3` /
   `Không thấy 0/3 — có thể đã bị xóa/từ chối`

Không lọc nội dung bài (`FILTER_BUY_POSTS = False`). Muốn chỉ bình luận bài **tìm mua màn hình** thì đặt `True`
(bộ lọc nằm trong `modules/watcher.py`).

### Tìm nhóm mới theo từ khóa — `data/groups_found.xlsx`

Mỗi `GROUP_SEARCH_EVERY_HOURS` (24) giờ, cuối vòng quét, script tìm trên Facebook theo `GROUP_SEARCH_QUERIES`
("màn hình Hà Nội", "PC Hà Nội", "setup pc", "phụ kiện màn hình", "đồ công nghệ Hà Nội", "chợ đồ cũ Hà Nội", "đồ cũ 2nd Hà Nội"…)
và giữ nhóm:
- tên có từ khóa quan trọng (`GROUP_KEYWORDS`: PC, màn hình, setup pc, phụ kiện màn hình, đồ công nghệ, chợ đồ cũ, 2nd;
  hoặc Hà Nội + máy tính/gaming/linh kiện)
- từ `MIN_GROUP_MEMBERS` (1000) thành viên, không thuộc tỉnh khác
- không phải nhóm màn hình LED/quảng cáo, điện thoại, pin/màn laptop, máy chơi game cầm tay, bàn ghế…

Tối đa `MAX_FOUND_GROUPS` (30) nhóm (Hà Nội & đông thành viên trước). Vòng sau script tự tham gia (điền "ok", tick hết)
rồi bình luận. Muốn bỏ nhóm nào thì xóa dòng đó trong `groups_found.xlsx`. Tìm ngay: `python main.py findgroups`.

### Khung Tiến trình — web, tab **Bình luận**

Đầu tab Bình luận hiện script **đang chạy / tạm dừng / đã tắt**, đang ở bước nào (quét nhóm, bình luận, nghỉ giữa 2 bài,
tham gia nhóm, kiểm tra lại, chờ vòng sau…), **% vòng quét**, nhóm thứ mấy / tổng, bài thứ mấy trong nhóm, đang gửi bình
luận sản phẩm nào, nội dung + link bài đang bình luận, bài vừa xong, và **nhật ký chạy** (như cửa sổ terminal), tự cập nhật
mỗi 4 giây. Không cần mở 2 cửa sổ đen nữa — để chúng thu nhỏ dưới thanh tác vụ.

### Sản phẩm & nội dung bình luận — web, tab **Sản phẩm**

Mỗi sản phẩm **đang bật** = 1 bình luận kèm ảnh riêng vào mỗi bài viết (3 sản phẩm bật → mỗi bài 3 bình luận).
Trên web bấm **＋ Thêm sản phẩm** hoặc **Sửa**:

| Ô | Ý nghĩa |
|---|---|
| Ảnh | `.jpg` `.png` `.webp`, lưu vào `data/images/` và đăng kèm bình luận |
| Tên, Giá đang bán, Giá mua mới | Chỗ trống tự điền trong bình luận: `{giá}` giá đang bán, `{giá_mới}` giá mua mới, `{tiết_kiệm}` = giá mới − giá bán. Sản phẩm chưa có giá mua mới thì các mẫu có `{giá_mới}`/`{tiết_kiệm}` bị bỏ qua (không đăng câu bị trống) |
| Bình luận đầy đủ | Có SĐT, địa chỉ — dùng mặc định |
| Bình luận không SĐT/địa chỉ | Dùng khi nhóm từ chối bản có SĐT. **Để trống** = tự bỏ các dòng có SĐT, địa chỉ, Zalo, hotline |

**Mẫu bình luận** (nút "Mẫu bình luận" trên từng sản phẩm): mỗi sản phẩm có nhiều mẫu, mỗi mẫu có bản đầy đủ và bản không
SĐT/địa chỉ. Mỗi bài viết, script **chọn ngẫu nhiên 1 mẫu đang bật** cho mỗi sản phẩm — ưu tiên mẫu ít dùng, tránh mẫu đã
dùng trong cùng nhóm 3 ngày gần đây, **không trùng nội dung trong 1 bài** — để bình luận không bị đại trà. Tick / bỏ tick
từng mẫu, **Bật hết / Tắt hết**, thêm / sửa / xóa, chuyển mẫu sang sản phẩm khác ngay trên web. Tắt hết mẫu của 1 sản phẩm =
không bình luận sản phẩm đó.

**Nhập mẫu từ file** (mục "Nhập mẫu bình luận từ file" đầu tab): file `.txt`, các mẫu cách nhau bằng dòng `---`; file bản
đầy đủ (bắt buộc) + file bản không liên hệ (ghép theo đúng thứ tự). Script tự nhận mẫu thuộc sản phẩm nào theo mã máy
(vd `G2712F`) và giá, mẫu đã có thì bỏ qua. Đang dùng: `data/Coment-Ver3/30_binh_luan_day_du.txt` + `30_binh_luan_khong_lien_he.txt` (30 mẫu bán hàng, 10 / sản phẩm).

Tick / bỏ tick **"Bình luận sản phẩm này"** để chọn sản phẩm được bình luận. Thay đổi có hiệu lực **từ bài viết tiếp
theo**, không cần khởi động lại script. Nên bật tối đa 3 sản phẩm (nhiều bình luận liên tiếp dễ bị coi là spam).
(Sản phẩm lưu trong `data/qc_facebook.db`; `data/comments.txt` chỉ dùng 1 lần để nhập 3 sản phẩm ban đầu.)

### Danh sách nhóm (file Excel) — web, tab **Danh sách nhóm**

- Tick **Dùng** để chọn file nào được chạy; script gộp các file đang tick (bỏ trùng link). Có sẵn 2 danh sách:
  `groups.xlsx` (danh sách gốc) và `groups_found.xlsx` (script tự tìm theo từ khóa)
- **Chỉ nhóm Hà Nội**: chỉ lấy nhóm có "Hà Nội / HN" trong tên
- **Thêm file mới**: tải lên `.xlsx` / `.csv` có 1 cột chứa link nhóm (`https://www.facebook.com/groups/...`). Cột tên nhóm,
  số thành viên, mức hoạt động (nếu có) được tự nhận để xếp ưu tiên. File lưu ở `data/group_lists/`
- **Dán link nhóm**: dán nhiều link (mỗi dòng 1 link, có thể `link | tên nhóm`) vào 1 danh sách có sẵn hoặc danh sách mới.
  Link chưa có tên tự hiện tên sau khi script mở nhóm đó
- **Xem nhóm**: danh sách nhóm trong file kèm trạng thái đã tham gia; mỗi nhóm có **Sửa** (tên, link, số thành viên,
  hoạt động, khu vực) và **Xóa** — ghi thẳng vào file Excel (file đang mở trong Excel thì đóng lại rồi thử lại).
  Nhóm xóa khỏi danh sách tự tìm sẽ không bị tự thêm lại. **Tải về**; **Xóa** cả file (chỉ file đã tải lên)
- Thay đổi có hiệu lực từ vòng quét sau. Nhóm chưa tham gia được tự tham gia cuối vòng

### Bình luận bị từ chối: tự xóa & gửi lại bản không SĐT/địa chỉ

Facebook/nhóm từ chối bình luận bằng cách gắn nhãn **"Bị từ chối · Xem ý kiến đóng góp"** dưới bình luận (chỉ người viết thấy).
Sau mỗi bình luận, script đợi tối đa 15 giây để đọc nhãn này:

1. Bản **đầy đủ** bị từ chối → **xóa ngay** → gửi lại bản **không SĐT/địa chỉ** vào đúng bài đó. Nhóm đó từ nay dùng bản không SĐT/địa chỉ
2. Bản **không SĐT/địa chỉ** cũng bị từ chối → xóa → **ngừng bình luận nhóm đó** (nhóm chặn mọi bình luận quảng cáo)
3. Bị từ chối **muộn** (sau khi script đã đi): lượt kiểm tra lại sau ~1 giờ sẽ tìm và xóa
4. **Chờ duyệt / không hiển thị**: không xóa được (không tìm thấy bình luận), nhóm đó chuyển sang bản không SĐT/địa chỉ
5. Facebook báo **bị chặn**: mọi nhóm chuyển sang bản không SĐT/địa chỉ, script nghỉ 6 giờ

Dọn bình luận bị từ chối còn sót trên các bài đã bình luận trong 3 ngày gần đây (hoặc N ngày):

```powershell
python main.py cleanup
python main.py cleanup 7
```

Trên web: ô **"Bị từ chối (đã tự xóa)"**. Nếu có bình luận không xóa được, ô này ghi *"… chưa xóa được, cần xóa tay"*.
Mục *Bản không SĐT/địa chỉ* liệt kê các nhóm đã chuyển và các nhóm **ngừng bình luận**, có nút để bật lại.

Trước khi gửi, script **đối chiếu chữ trong ô bình luận với nội dung gốc**. Nếu sai (rơi/lẫn chữ) thì xóa đi gõ lại; vẫn sai thì
không gửi (ghi trạng thái *Lỗi*).

---

## 3️⃣ Web quản lý — http://127.0.0.1:5000

- **Trạng thái script:** đang quét / lượt kế tiếp lúc mấy giờ / tạm dừng / bị chặn tới mấy giờ / *script có thể đã dừng*
- **Số liệu trong ngày:** số bài đã bình luận / giới hạn, số bình luận đã đăng, chờ duyệt, bị chặn/lỗi, bị xóa, bỏ qua
- **Danh sách bài:** giờ, nhóm, nội dung bài, trạng thái. Bấm vào một bài để xem **3 bình luận** (chữ, ảnh, giờ gửi,
  trạng thái, ghi chú), **ảnh chụp màn hình** và link **Mở bài viết**. Bài có vấn đề được viền đỏ
- **Lọc** theo ngày, theo trạng thái (*Có vấn đề*, *Hoàn tất*, *Bỏ qua*), tìm theo chữ
- **Lượt quét gần đây:** mỗi lượt quét bao nhiêu nhóm, bao nhiêu bài mới, đã bình luận bao nhiêu
- Nút **Tạm dừng / Tiếp tục chạy** (dừng cả bình luận lẫn đăng bài theo lịch), **Bỏ chặn ngay**, **Tải Excel**
- Tự làm mới mỗi 30 giây

Web chỉ mở được trên máy này (127.0.0.1), máy khác trong mạng không truy cập được.

---

## 4️⃣ Đăng bài theo lịch — `data/schedule.xlsx`

| time | content | image | group_category |
|---|---|---|---|
| 08:00 | MSI G2712F 27" FHD 180Hz — 1.600.000đ... | MSI_G2712F_FHD_180Hz_Gia_1600000d.jpg | |

- `time`: giờ đăng `HH:MM`. Nếu đúng giờ đó máy đang bận quét nhóm, bài được đăng bù trong vòng 60 phút
- `group_category`: `Màn hình` / `PC`. Để trống thì đăng vào mọi nhóm thuộc `TARGET_REGION`
- Mỗi nhóm nhận tối đa 1 bài/ngày

> Nhóm "MUA BÁN MÀN HÌNH MÁY TÍNH HÀ NỘI" yêu cầu bài đăng **ghi rõ tình trạng màn hình**.

---

## 5️⃣ Tùy chỉnh (`config.py`)

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `TARGET_REGION` | `"Hà Nội"` | Chỉ dùng nhóm có `region` này. `""` = tất cả 215 nhóm |
| `PRIORITY_REGION` | `"Hà Nội"` | Nhóm khu vực này được quét/bình luận trước |
| `MAX_POST_AGE_MINUTES` | 1440 | Chỉ bình luận bài đăng trong vòng ... phút (24 giờ) |
| `MAX_POSTS_PER_GROUP` | 0 | Mỗi vòng 1 nhóm tối đa ... bài. `0` = bình luận hết |
| `COMMENT_TOPICS` | `["Màn hình", "PC"]` | Chủ đề được bình luận, theo thứ tự ưu tiên. Thêm `"Laptop"` = cả bài laptop; `[]` = mọi bài |
| `GROUP_KEYWORDS` | PC, màn hình, Hà Nội, setup pc, phụ kiện màn hình, đồ công nghệ, chợ đồ cũ, 2nd | Từ khóa quan trọng trong tên nhóm (lọc nhóm tìm được + cộng điểm ưu tiên) |
| `GROUP_SEARCH_QUERIES` | 9 cụm từ | Cụm từ tìm nhóm trên Facebook |
| `GROUP_SEARCH_EVERY_HOURS` | 24 | Bao lâu tìm nhóm mới 1 lần |
| `MIN_GROUP_MEMBERS` / `MAX_FOUND_GROUPS` | 1000 / 30 | Bỏ nhóm ít thành viên / giữ tối đa ... nhóm tự tìm |
| `MAX_COMMENTED_POSTS_PER_DAY` | 0 | Giới hạn số bài/ngày. `0` = không giới hạn (chạy liên tục) |
| `ROUND_IDLE_MINUTES` | 5 | Vòng không có bài mới thì chờ ... phút rồi quét lại |
| `AUTO_JOIN` | `True` | Cuối vòng tự tham gia nhóm chưa tham gia |
| `JOIN_ANSWER` | `"ok"` | Câu trả lời điền vào mọi ô câu hỏi khi tham gia |
| `JOIN_PER_DAY` | 20 | Số nhóm tối đa tự tham gia mỗi ngày |
| `COMMENT_GAP_MIN` / `MAX` | 15 / 40 | Chờ giữa 3 bình luận trong cùng 1 bài (giây) |
| `MIN_DELAY` / `MAX_DELAY` | 30 / 120 | Chờ giữa 2 bài (giây) |
| `FILTER_BUY_POSTS` | `False` | `True` = chỉ bình luận bài tìm mua màn hình |
| `BLOCK_COOLDOWN_HOURS` | 6 | Bị Facebook chặn thì nghỉ ... giờ |
| `VERIFY_AFTER_MINUTES` | 60 | Sau ... phút mở lại bài kiểm tra bình luận còn hay bị xóa |
| `WATCH_SCROLLS` | 60 | Số lần cuộn tối đa mỗi nhóm (dừng sớm khi gặp bài cũ hơn 24 giờ) |
| `HEADLESS` | `False` | `True` = ẩn cửa sổ Chrome |
| `WEB_PORT` | 5000 | Cổng web quản lý |

Sửa xong thì đóng cửa sổ "QC-Facebook" và bấm đúp lại `chay-ngam.bat`.

---

## 6️⃣ Các lệnh

| Lệnh | Tác dụng |
|---|---|
| `python main.py` | Chạy nền liên tục (từng nhóm bình luận hết bài mới, cuối vòng tự tham gia nhóm, quét lại; đăng bài theo lịch) |
| `python main.py watch` | Chạy **1 vòng** |
| `python web.py` | Mở web quản lý |
| `python main.py testcomment <link bài>` | Gửi cả 3 bình luận vào đúng 1 bài (kết quả cũng hiện trên web) |
| `python main.py testcomment <link bài> 2` | Chỉ gửi bình luận số 2 |
| `python main.py cleanup [N]` | Xóa mọi bình luận bị từ chối trên các bài đã bình luận trong N ngày (mặc định 3) |
| `python main.py test [<link nhóm>]` | Đăng thử bài đầu tiên trong lịch vào 1 nhóm |
| `python main.py post` | Đăng ngay tất cả bài trong lịch |
| `python main.py login` | Đăng nhập Facebook |
| `python main.py join` | Kiểm tra / tham gia nhóm, lưu nội quy |
| `python main.py findgroups` | Tìm nhóm mới theo từ khóa → `data/groups_found.xlsx` |
| `python tools/import_groups.py` | Cập nhật `groups.xlsx` sau khi sửa `nhom_facebook_man_hinh_PC.xlsx` |

---

## 7️⃣ Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân / Cách xử lý |
|---|---|
| Web báo *script có thể đã dừng* | Cửa sổ "QC-Facebook" đã bị đóng hoặc lỗi → bấm đúp lại `chay-ngam.bat` |
| Nhiều bình luận **Bị chặn** | Facebook hạn chế tài khoản. Script tự nghỉ 6 giờ; nên đặt `MAX_COMMENTED_POSTS_PER_DAY` (vd 40) hoặc `MAX_POSTS_PER_GROUP` (vd 10) |
| Nhiều bình luận **Chờ duyệt** / kiểm tra lại **Không thấy** | Nhóm duyệt hoặc xóa bình luận quảng cáo → cân nhắc bỏ nhóm đó khỏi danh sách |
| `Lỗi — Không tìm thấy ô soạn bình luận` | Facebook đổi giao diện → cập nhật `XP_EDITOR` trong `modules/commenter.py` |
| Vòng quét luôn `0 bài mới` | Không có bài mới trong 24 giờ (hoặc đã bình luận hết), hoặc Facebook đổi giao diện bảng tin (`modules/watcher.py`) |
| Không mở được Chrome | Chrome lần trước còn chạy ngầm; script tự đóng nó, nếu vẫn lỗi thì tắt `chrome.exe` trong Task Manager |
| `✗ Đăng nhập thất bại` | Chạy `python main.py login` |

---

## 🔒 Bảo mật

**Không chia sẻ** `.env`, `chrome_profile/` và `data/qc_facebook.db`.
