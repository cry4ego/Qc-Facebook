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

1. Bấm đúp **`chay-ngam.bat`**. Bốn cửa sổ thu nhỏ sẽ chạy, và trình duyệt tự mở web quản lý:
   - **QC-Facebook Quet** và **QC-Facebook Quet 2** — 2 cửa sổ **QUÉT** (mỗi cửa sổ 1 Chrome riêng): chia nhau các nhóm
     (không quét trùng), liên tục tìm bài mới, bài đạt điều kiện vào **hàng chờ**
   - **QC-Facebook** — cửa sổ **BÌNH LUẬN**: lấy bài **mới nhất** trong hàng chờ bình luận **ngay**
   - **QC-Facebook Web** — web quản lý
2. Xem kết quả trên web **http://127.0.0.1:5000** (dòng 🔎 cho biết cửa sổ quét đang quét nhóm nào, hàng chờ còn bao nhiêu bài)
3. Muốn dừng tạm thời thì bấm **Tạm dừng** trên web (mọi cửa sổ cùng dừng). Muốn tắt hẳn thì đóng các cửa sổ terminal —
   **đừng đóng nhầm**: đóng cửa sổ terminal là bot dừng hẳn (10/10 11:24 cả 4 cửa sổ tắt cùng lúc, không có lỗi nào)

**Lần đầu chạy song song** (hoặc khi cửa sổ quét báo chưa đăng nhập): đóng các cửa sổ trên rồi chạy
`.venv\Scripts\python.exe main.py taophienquet` — chép phiên đăng nhập sang Chrome của 2 cửa sổ quét (`chrome_profile_quet/`, `chrome_profile_quet2/`).
Vẫn chưa đăng nhập được thì chạy `python main.py login quet` (cửa sổ 2: `python main.py login quet 2`) và đăng nhập tay.

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

### Chạy song song: quét & bình luận cùng lúc (`PARALLEL = True`, từ 10/10)

Trước đây 1 cửa sổ vừa quét vừa bình luận: lúc đang bình luận 1 bài (2–4 phút) thì không quét, bài mới thường đã đăng
~60 phút mới được bình luận. Nay 2 cửa sổ chạy song song, mỗi cửa sổ 1 Chrome riêng (cùng tài khoản Facebook):

- **2 cửa sổ QUÉT** (`python main.py quet`, `python main.py quet 2` — `SCAN_WINDOWS = 2`, chia nhau nhóm qua bảng
  `scan_claims`, không quét trùng): liên tục chọn nhóm nên quét nhất —
  nhóm tương tác cao (`HOT_GROUPS`) mỗi **2 phút**, nhóm có khách tìm màn hình / nhóm ≥ 100 bài/ngày mỗi **5 phút**,
  nhóm thường mỗi **60 phút**, nhóm ít khách 24 giờ. Nhóm tới lượt cùng lúc thì nhóm **điểm cao** trước: điểm = khách
  tìm màn hình (nặng nhất) + **tương tác trung bình mỗi bài** (cảm xúc + bình luận + chia sẻ) + số bài/ngày + **số thành
  viên**. Mỗi lần chỉ xét bài đăng **sau lần quét trước** (+10 phút dự phòng) nên quét lại chỉ mất vài chục giây (tối đa
  45 giây). Bài đạt mọi bộ lọc → **hàng chờ**. Cửa sổ quét chỉ đọc: không bình luận, không tham gia nhóm
- **Cửa sổ BÌNH LUẬN** (`python main.py`): luôn lấy bài **đăng gần đây nhất** trong hàng chờ bình luận ngay; giữa 2 bài
  vẫn nghỉ 30–120 giây. Hàng chờ trống thì: tự tham gia nhóm cửa sổ quét báo chưa tham gia, kiểm tra lại vài bài đã
  bình luận, đăng bài theo lịch. Bài quá 6 giờ chưa kịp bình luận → "Quá hạn"
- Cả 2 cửa sổ cùng dừng khi bấm **Tạm dừng** trên web, khi đủ 40 bài/ngày, khi bị Facebook chặn
- `PARALLEL = False` (hoặc chưa có `chrome_profile_quet/`) → chạy cách cũ bên dưới (1 cửa sổ tự quét rồi bình luận)

### Cách cũ (1 cửa sổ)

Script chạy **liên tục theo vòng**. Mỗi vòng:

1. **Danh sách nhóm** = 24 nhóm Hà Nội trong `groups.xlsx` + nhóm **tự tìm theo từ khóa** (`groups_found.xlsx`, xem dưới).
   **Xếp thứ tự**: nhóm thuộc `PRIORITY_REGION` trước, rồi theo điểm = (hoạt động + số thành viên) × từ khóa trong tên
   (`GROUP_KEYWORDS`, mỗi từ khóa +25%) × **2 nếu tên có "màn hình"**, × 0,7 nếu tên chỉ nói laptop
2. **Lần lượt từng nhóm** (nhóm đông bài nhất trước):
   - mở nhóm, sắp xếp theo **Bài viết mới**, cuộn tới hết các bài đăng trong **6 giờ** (`MAX_POST_AGE_MINUTES`) —
     **không giới hạn số bài** (`MAX_POSTS_PER_GROUP = 0`), kể cả nhiều người đăng cùng lúc
   - **chỉ lấy bài tìm màn hình** (`COMMENT_TOPICS = ["Màn hình"]` — từ 08/10 bỏ bài tìm PC / linh kiện lẻ; thêm
     `"PC"` vào danh sách nếu muốn bình luận lại cả bài PC):
     - *Màn hình*: mua/bán/tìm màn hình, bài cần build PC **kèm màn hình**
     - *PC*: máy bàn, case, cấu hình, linh kiện, VGA, setup, bàn phím/chuột…
     - **bỏ qua** bài laptop (kể cả bài laptop ghi "màn 15.6", "165hz"), điện thoại, máy in…
     Bộ nhận diện nằm trong `modules/topic.py` (`MONITOR_TOPIC`, `PC_TOPIC`, `LAPTOP_TOPIC`)
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

### Chỉ bình luận bài của người cần MUA, ở nhóm đông & tương tác tốt

Bot **không bình luận tràn lan** nữa. Trước khi quét, mỗi **nhóm** được kiểm tra; trong nhóm, mỗi **bài** qua lần lượt
các bộ lọc — không đạt 1 bộ lọc là bỏ qua, và **mọi quyết định đều được ghi lại kèm lý do** (web → tab **Phân loại bài**,
và `logs/app.log`):

| Bước | Điều kiện | Cấu hình (`config.py`) |
|---|---|---|
| Nhóm | Số thành viên ≥ 5.000; **nhóm Hà Nội** (tên có Hà Nội/HN hoặc cột khu vực = Hà Nội) chỉ cần ≥ 500 (đọc ở trang **Giới thiệu** của nhóm, lưu CSDL, đọc lại sau 24 giờ). Không đọc được số thành viên → bỏ qua nhóm | `GROUP_MIN_MEMBERS`, `GROUP_MIN_MEMBERS_HANOI`, `GROUP_STATS_CACHE_HOURS` |
| Nhóm | (tùy chọn) số bài mới mỗi ngày ≥ … | `GROUP_MIN_POSTS_PER_DAY` (0 = không xét) |
| Bài | Chủ đề **màn hình** (bỏ bài tìm PC / linh kiện lẻ, laptop, điện thoại…; bài build PC có kèm màn hình vẫn tính là màn hình) | `COMMENT_TOPICS` |
| Bài | Ý định **MUA** — bỏ bài **BÁN** (shop, thanh lý, đối thủ) và bài **KHÔNG XÁC ĐỊNH** | `INTENT_FILTER`, `INTENT_MIN_SCORE`, `INTENT_MARGIN` |
| Bài | Từ khóa chưa đủ chắc (KHÔNG XÁC ĐỊNH) → hỏi **AI Gemini** MUA hay BÁN (mỗi nội dung hỏi 1 lần, lưu lại). Gemini lỗi / hết lượt → bỏ qua bài | `INTENT_AI`, `GEMINI_MODEL`, `GEMINI_MAX_CALLS_PER_DAY`, khóa `GEMINI_API_KEY` trong file `.env` |
| Bài | **Khu vực**: khách ghi rõ ở xa (TP.HCM, miền Nam, miền Trung, tỉnh xa…) mà không nhắc Hà Nội / tỉnh lân cận → bỏ qua, dành lượt cho khách gần. Bài **không ghi khu vực**: ở **nhóm Hà Nội** (tên nhóm có "Hà Nội"/"HN") vẫn bình luận; ở **nhóm toàn quốc** (vd MÀN HÌNH MÁY TÍNH) bỏ qua — khoảng một nửa là khách tỉnh xa. Danh sách tỉnh **GẦN / XA** sửa trong file **`data/khu_vuc.txt`** (có hiệu lực ngay) | `REGION_FILTER`, `REGION_FILE`, `REGION_REQUIRED_IN_NATIONAL_GROUPS` |
| Bài | Đăng trong **6 giờ** gần đây (bài cũ hơn thường đã có nhiều shop trả lời) | `MAX_POST_AGE_MINUTES` |
| Bài | **Không chờ tương tác**: bài cần mua được bình luận **ngay khi phát hiện** (bài mới 0 like / 0 bình luận là cơ hội tốt nhất — chưa shop nào trả lời). Muốn chỉ bình luận bài đã có tương tác thì đặt ngưỡng > 0 (điểm = cảm xúc ×1 + bình luận ×2 + chia sẻ ×3) | `POST_MIN_ENGAGEMENT` (đang `0`), `ENGAGEMENT_WEIGHTS` |

**Từ khóa MUA / BÁN** nằm trong file riêng **`data/tu_khoa_mua_ban.txt`** (mỗi dòng 1 cụm từ, có thể kèm điểm
`cụm từ | 3`) — sửa file là bot dùng ngay từ bài tiếp theo, không cần sửa code hay khởi động lại. Thử 1 câu:

```powershell
python main.py phanloai "Cần tìm màn 27 inch 2K tầm 3tr ở Cầu Giấy"
```

Xem lại bài **KHÔNG XÁC ĐỊNH** trên tab **Phân loại bài**: bài nào thật ra là người cần mua thì thêm từ khóa vào file.

Mỗi nhóm chỉ quét tối đa **2 phút** (`GROUP_SCAN_MAX_SECONDS`) — bài mới nhất được xét trước. Số thành viên đọc lại
ngay khi bấm **Cập nhật số thành viên** (tab Phân loại bài) hoặc chạy `python main.py capnhatnhom`.

**Xoay vòng nhóm theo số bài cần mua** (để quét tới cả các nhóm cuối danh sách, không chỉ vài nhóm đầu):
- thứ tự: nhóm tương tác cao → nhóm "Ưu tiên" trên web → nhóm có **nhiều bài cần mua** trong 7 ngày (`YIELD_DAYS`)
  → nhóm chưa quét lần nào → nhóm **ít khách** (quét ≥ 3 lần mà 0 bài cần mua)
- nhóm vừa quét xong thì **2 giờ** sau mới quét lại (`GROUP_RESCAN_MINUTES`), nhóm ít khách **24 giờ** 1 lần
  (`LOW_YIELD_RESCAN_HOURS`); nhóm tương tác cao vẫn quét lại mỗi 5 phút
- nhóm báo **"Bạn hiện không xem được nội dung này"** (thường do bị quản trị viên chặn khỏi nhóm): log ghi cảnh báo ⚠,
  bot bỏ qua nhóm đó 24 giờ rồi thử lại (`GROUP_UNAVAILABLE_RETRY_HOURS`)
- đủ `MAX_COMMENTED_POSTS_PER_DAY` bài trong ngày: vẫn tự tham gia nhóm & kiểm tra lại bài đã bình luận rồi mới nghỉ

**Đăng bài theo lịch** vào nhóm có nhiều bài cần mua trước. Nhóm không đăng được vì lý do của nhóm thì không tính là lỗi
và lần sau tự bỏ qua: chưa tham gia, không xem được nhóm, nhóm **chỉ cho đăng tin bán** ("Bán gì đó" — bỏ qua 30 ngày),
nhóm đang giữ **quá nhiều bài/bình luận chờ duyệt** của bạn (bỏ qua 24 giờ). Bấm Đăng mà cửa sổ không đóng thì log ghi lại
Facebook báo gì + ảnh chụp trong `data/screenshots/dang_bai_loi_*.png`.

**Chạy thử trước khi chạy thật** — quét & phân loại, KHÔNG bình luận, KHÔNG tham gia nhóm:

```powershell
python main.py thuquet 5        # 5 nhóm đầu danh sách
python main.py thuquet https://www.facebook.com/groups/manhinhmaytinh/
```

### Tìm nhóm mới theo từ khóa — `data/groups_found.xlsx`

Mỗi `GROUP_SEARCH_EVERY_HOURS` (24) giờ, cuối vòng quét, script tìm trên Facebook theo `GROUP_SEARCH_QUERIES`
(từ 08/10 chỉ về **màn hình**: "màn hình máy tính Hà Nội", "mua bán màn hình Hà Nội", "màn hình cũ Hà Nội",
"thanh lý màn hình Hà Nội", "chợ màn hình máy tính Hà Nội"…) và giữ nhóm:
- tên có từ khóa quan trọng (`GROUP_KEYWORDS`: màn hình, màn hình cũ, thanh lý màn hình, mua bán màn hình;
  hoặc Hà Nội + máy tính/gaming/linh kiện)
- từ `MIN_GROUP_MEMBERS` (5000) thành viên (nhóm Hà Nội: từ `GROUP_MIN_MEMBERS_HANOI` = 500), không thuộc tỉnh khác
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
| `MAX_POST_AGE_MINUTES` | 360 | Chỉ bình luận bài đăng trong vòng ... phút (6 giờ) |
| `MAX_POSTS_PER_GROUP` | 0 | Mỗi vòng 1 nhóm tối đa ... bài. `0` = bình luận hết |
| `COMMENT_TOPICS` | `["Màn hình"]` | Chủ đề được bình luận, theo thứ tự ưu tiên. Thêm `"PC"` / `"Laptop"` nếu muốn; `[]` = mọi bài |
| `GROUP_KEYWORDS` | màn hình, Hà Nội, màn hình cũ, thanh lý màn hình, mua bán màn hình | Từ khóa quan trọng trong tên nhóm (lọc nhóm tìm được + cộng điểm ưu tiên) |
| `GROUP_SEARCH_QUERIES` | 7 cụm từ về màn hình (Hà Nội) | Cụm từ tìm nhóm trên Facebook |
| `GROUP_SEARCH_EVERY_HOURS` | 24 | Bao lâu tìm nhóm mới 1 lần |
| `MIN_GROUP_MEMBERS` / `MAX_FOUND_GROUPS` | 5000 / 30 | Tìm nhóm mới: bỏ nhóm ít thành viên / giữ tối đa ... nhóm tự tìm |
| `MAX_COMMENTED_POSTS_PER_DAY` | 40 | Giới hạn số bài/ngày (05/10 bị chặn sau 121 bài). Đủ số thì nghỉ tới 0 giờ, không mở Chrome (vẫn đăng bài theo lịch). `0` = không giới hạn |
| `ROUND_IDLE_MINUTES` | 5 | Vòng không có bài mới thì chờ ... phút rồi quét lại |
| `AUTO_JOIN` | `True` | Cuối vòng tự tham gia nhóm chưa tham gia |
| `JOIN_ANSWER` | `"ok"` | Câu trả lời điền vào mọi ô câu hỏi khi tham gia |
| `JOIN_PER_DAY` | 20 | Số nhóm tối đa tự tham gia mỗi ngày |
| `COMMENT_GAP_MIN` / `MAX` | 15 / 40 | Chờ giữa 3 bình luận trong cùng 1 bài (giây) |
| `MIN_DELAY` / `MAX_DELAY` | 30 / 120 | Chờ giữa 2 bài (giây) |
| `GROUP_MIN_MEMBERS` | 5000 | Chỉ quét nhóm có từ ... thành viên (đọc ở trang Giới thiệu nhóm) |
| `GROUP_MIN_MEMBERS_HANOI` | 500 | Nhóm Hà Nội chỉ cần từ ... thành viên (nhỏ nhưng đúng khách); cũng dùng khi tìm nhóm mới |
| `GROUP_MIN_POSTS_PER_DAY` | 0 | Chỉ quét nhóm có từ ... bài mới/ngày. `0` = không xét |
| `GROUP_STATS_CACHE_HOURS` / `GROUP_STATS_RETRY_MINUTES` | 24 / 60 | Số thành viên dùng lại ... giờ / đọc lỗi thì ... phút sau thử lại |
| `GROUP_SCAN_MAX_SECONDS` | 45 | Quét 1 nhóm tối đa ... giây |
| `INTENT_FILTER` | `True` | Chỉ bình luận bài người cần **MUA** (bỏ bài BÁN / không rõ). `False` = tắt bộ lọc này |
| `INTENT_KEYWORDS_FILE` | `data/tu_khoa_mua_ban.txt` | File từ khóa MUA / BÁN |
| `INTENT_MIN_SCORE` / `INTENT_MARGIN` | 3 / 2 | Bài là MUA khi điểm MUA ≥ ... và hơn điểm BÁN ít nhất ... |
| `REGION_FILTER` / `REGION_FILE` | `True` / `data/khu_vuc.txt` | Bỏ qua khách ghi rõ ở khu vực xa (danh sách tỉnh GẦN / XA trong file) |
| `REGION_REQUIRED_IN_NATIONAL_GROUPS` | `True` | Nhóm toàn quốc: chỉ bình luận bài ghi rõ Hà Nội / tỉnh lân cận. `False` = cả bài không ghi khu vực |
| `PARALLEL` / `SCAN_WINDOWS` | `True` / 2 | Chạy song song 2 cửa sổ QUÉT + 1 cửa sổ BÌNH LUẬN (cần `chrome_profile_quet/`, `chrome_profile_quet2/` — lệnh `taophienquet`) |
| `HOT_RESCAN_MINUTES` / `SCAN_ACTIVE_MINUTES` | 2 / 5 | Quét lại nhóm tương tác cao / nhóm có khách hoặc ≥ `SCAN_ACTIVE_POSTS_PER_DAY` (100) bài/ngày mỗi ... phút |
| `SCAN_OVERLAP_MINUTES` | 10 | Quét lại chỉ xét bài đăng sau lần quét trước + ... phút |
| `QUEUE_IDLE_SECONDS` / `QUEUE_HOUSEKEEP_MINUTES` | 15 / 30 | Hàng chờ trống: ... giây xem lại; ... phút 1 lần tham gia nhóm + kiểm tra lại bài cũ |
| `GROUP_RESCAN_MINUTES` | 60 | Nhóm thường quét xong thì ... phút sau mới quét lại (nhường lượt cho nhóm khác) |
| `YIELD_DAYS` / `LOW_YIELD_MIN_SCANS` / `LOW_YIELD_RESCAN_HOURS` | 7 / 3 / 24 | Nhóm quét ≥ 3 lần trong 7 ngày mà 0 bài cần mua = ít khách, 24 giờ quét 1 lần |
| `GROUP_UNAVAILABLE_RETRY_HOURS` | 24 | Nhóm báo "không xem được nội dung này": ... giờ sau mới thử lại |
| `POST_MIN_ENGAGEMENT` | 0 | Chỉ bình luận bài có điểm tương tác từ ... trở lên. `0` = không xét (bình luận bài cần mua ngay) |
| `ENGAGEMENT_WEIGHTS` | 1 / 2 / 3 | Trọng số cảm xúc / bình luận / chia sẻ khi tính điểm tương tác |
| `INTENT_AI` | `True` | Bài từ khóa chấm KHÔNG XÁC ĐỊNH thì hỏi Gemini (cần `GEMINI_API_KEY` trong file `.env`) |
| `GEMINI_MODEL` / `GEMINI_MAX_CALLS_PER_DAY` | `gemini-flash-lite-latest` / 500 | Model Gemini / số lần hỏi tối đa mỗi ngày |
| `BLOCK_COOLDOWN_HOURS` | 6 | Bị Facebook chặn thì nghỉ ... giờ |
| `VERIFY_AFTER_MINUTES` | 60 | Sau ... phút mở lại bài kiểm tra bình luận còn hay bị xóa |
| `HOT_GROUPS` | 2 nhóm | Nhóm tương tác cao: luôn quét đầu vòng, tự tham gia ngay nếu chưa vào, không cần có trong danh sách trên web |
| `WATCH_SCROLLS` | 60 | Số lần cuộn tối đa mỗi nhóm (dừng sớm khi gặp bài cũ hơn `MAX_POST_AGE_MINUTES`) |
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
| `python main.py quet [2]` | Cửa sổ **QUÉT** số 1 / 2 (chạy song song, `chay-ngam.bat` tự mở): tìm bài mới liên tục → hàng chờ |
| `python main.py taophienquet` | Tạo Chrome cho các cửa sổ quét: chép phiên đăng nhập (đóng các cửa sổ "QC-Facebook…" trước) |
| `python main.py login quet [2]` | Đăng nhập tay cho Chrome của cửa sổ quét số 1 / 2 |
| `python main.py thuquet [N\|link nhóm]` | **Chạy thử**: quét & phân loại N nhóm đầu (hoặc 1 nhóm), KHÔNG bình luận / tham gia nhóm |
| `python main.py phanloai "nội dung"` | Xem 1 câu được chấm MUA / BÁN / KHÔNG XÁC ĐỊNH và vì sao |
| `python main.py capnhatnhom` | Đọc lại ngay số thành viên của mọi nhóm, cho biết nhóm nào được quét |
| `python -m pytest` | Chạy test tự động (cần `pip install -r requirements-dev.txt`) |
| `python tools/import_groups.py` | Cập nhật `groups.xlsx` sau khi sửa `nhom_facebook_man_hinh_PC.xlsx` |

---

## 7️⃣ Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân / Cách xử lý |
|---|---|
| Web báo *script có thể đã dừng* | Cửa sổ "QC-Facebook" đã bị đóng hoặc lỗi → bấm đúp lại `chay-ngam.bat` |
| Nhiều bình luận **Bị chặn** | Facebook hạn chế tài khoản. Script tự nghỉ 6 giờ; nên đặt `MAX_COMMENTED_POSTS_PER_DAY` (vd 40) hoặc `MAX_POSTS_PER_GROUP` (vd 10) |
| Nhiều bình luận **Chờ duyệt** / kiểm tra lại **Không thấy** | Nhóm duyệt hoặc xóa bình luận quảng cáo → cân nhắc bỏ nhóm đó khỏi danh sách |
| `Lỗi — Không tìm thấy ô soạn bình luận` | Facebook đổi giao diện → cập nhật `XP_EDITOR` trong `modules/commenter.py` |
| Vòng quét luôn `0 bài mới` | Không có bài mới trong 6 giờ (hoặc đã bình luận hết), hoặc Facebook đổi giao diện bảng tin (`modules/watcher.py`) |
| Log báo `⚠ Tài khoản KHÔNG XEM ĐƯỢC nhóm …` | Mở nhóm bằng tài khoản khác: nhóm vẫn còn thì tài khoản bot đã bị chặn khỏi nhóm → bỏ nhóm khỏi `HOT_GROUPS` / danh sách |
| Không mở được Chrome | Chrome lần trước còn chạy ngầm; script tự đóng nó, nếu vẫn lỗi thì tắt `chrome.exe` trong Task Manager |
| `✗ Đăng nhập thất bại` | Chạy `python main.py login` |

---

## 🔒 Bảo mật

**Không chia sẻ** `.env`, `chrome_profile/` và `data/qc_facebook.db`.
