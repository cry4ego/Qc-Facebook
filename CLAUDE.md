# QC-Facebook — tài liệu nhanh cho AI / người mới

Đọc file này trước khi mò code. Tài liệu chi tiết cho người dùng: `README.md`. Toàn bộ giao diện, log, chú thích code đều **tiếng Việt** — giữ nguyên phong cách đó.

## 1. Dự án làm gì

Bot Selenium (Python, Windows) điều khiển Chrome đã đăng nhập Facebook của **chủ shop bán màn hình máy tính cũ ở Hà Nội** (64 Cầu Diễn):

1. **Tự bình luận quảng cáo** vào bài mới (≤ 24 giờ) trong các nhóm Facebook mua bán màn hình / PC. Mỗi bài nhận 1 bình luận / sản phẩm đang bật (hiện 3 màn MSI), kèm ảnh. Nội dung chọn **ngẫu nhiên** trong các mẫu đang bật, không trùng trong 1 bài, tránh lặp trong cùng nhóm.
2. **Chỉ bình luận bài liên quan**: màn hình trước, rồi PC; **bỏ bài laptop**, điện thoại… (`topic()` trong `modules/watcher.py`).
3. **Tự xử lý bị từ chối**: bình luận bị gắn "Bị từ chối" → xóa ngay → gửi lại bản **không SĐT/địa chỉ**; nhóm đó từ nay dùng bản an toàn; bản an toàn cũng bị từ chối → ngừng nhóm. Facebook báo chặn → nghỉ 6 giờ.
4. **Tự tham gia nhóm** chưa vào (cuối mỗi vòng, điền "ok" vào câu hỏi, tick hết) và **tự tìm nhóm mới** theo từ khóa mỗi ngày.
5. **Đăng bài theo lịch** (`data/schedule.xlsx`) — tính năng phụ.
6. **Web quản lý** Flask `http://127.0.0.1:5000`: tiến trình trực tiếp, nhật ký bình luận, sản phẩm + mẫu bình luận, danh sách nhóm (file Excel), tạm dừng.

Chạy liên tục theo **vòng**: lần lượt từng nhóm (đã xếp ưu tiên) → quét hết bài mới → bình luận hết → nhóm sau → cuối vòng tham gia nhóm + kiểm tra lại bài cũ + (mỗi 24h) tìm nhóm mới → quét lại.

## 2. Chạy

**Máy mới** (Windows, cần Python ≥ 3.10 + Google Chrome): giải nén zip → bấm đúp `cai-dat.bat` (tạo `.venv`, cài `requirements.txt`, mở Chrome để **đăng nhập Facebook bằng tay**, nhấn Enter) → bấm đúp `chay-ngam.bat`.
Phiên đăng nhập nằm ở `chrome_profile/` — **không chép được sang máy khác** (cookie mã hóa DPAPI theo tài khoản Windows) nên máy mới luôn phải `python main.py login`. **Không chạy 2 máy cùng 1 tài khoản.**

| Lệnh / file | Tác dụng |
|---|---|
| `chay-ngam.bat` | Mở 2 cửa sổ thu nhỏ: `web.py` + `main.py` (chạy nền liên tục) và mở trình duyệt web quản lý |
| `mo-web.bat` | Chỉ mở web |
| `cai-dat.bat` / `dong-goi.bat` | Cài trên máy mới / đóng gói zip để chuyển máy (`tools/dong_goi.py`) |
| `python main.py` | Chạy nền liên tục (= `run_scheduler`) |
| `python main.py watch` | Chạy đúng 1 vòng |
| `python main.py login` | Mở Chrome để đăng nhập tay |
| `python main.py testcomment <link bài> [N]` | Bình luận tay 1 bài (N = chỉ sản phẩm thứ N) |
| `python main.py findgroups` / `join` / `cleanup [ngày]` | Tìm nhóm mới / kiểm tra-tham gia nhóm / xóa bình luận bị từ chối còn sót |
| `python main.py test [N\|link nhóm]` / `post` | Đăng thử / đăng ngay bài trong lịch |
| `python web.py` | Web quản lý |

Dừng: đóng cửa sổ "QC-Facebook" hoặc bấm **Tạm dừng** trên web (lưu ở `settings.paused` — sau khi khởi động lại vẫn tạm dừng cho tới khi bấm "Tiếp tục chạy").

## 3. Cấu trúc thư mục

```
main.py              Điểm vào CLI + scheduler: tạo Chrome (create_driver, profile chrome_profile/, tự kill Chrome mồ côi),
                     login, task_* (watch/post/join/findgroups/cleanup/testcomment), run_scheduler (vòng liên tục),
                     load_target_groups, pick_comments, set_progress
web.py               Flask: mọi /api/* cho web (xem mục 6)
config.py            Mọi tham số (Config.*). Sửa xong phải khởi động lại main.py/web.py
modules/
  watcher.py         Lõi vòng chạy: GroupWatcher.run (quét → bình luận → tham gia → verify), scan_group (cuộn bảng tin
                     ?sorting_setting=CHRONOLOGICAL, lấy link bài bằng hover mốc thời gian), comment_post (logic từ chối /
                     bản an toàn / bị chặn), verify/review/cleanup, topic() phân loại Màn hình / PC / Laptop
  commenter.py       Thao tác 1 bài: open_post, send_comment (gõ bằng CDP Input.insertText + Shift+Enter, đối chiếu nội dung
                     trước khi gửi, gắn ảnh, đọc nhãn "Bị từ chối"), delete_comment, review_post, nhận diện bình luận của mình
                     theo uid cookie c_user
  group_checker.py   Trạng thái thành viên (detect_status), auto_join (điền "ok", tick, Gửi), dismiss_welcome; lệnh join cũ
  group_finder.py    Tìm nhóm trên facebook.com/search/groups theo từ khóa, lọc (qualifies) → data/groups_found.xlsx
  group_lists.py     Các "danh sách nhóm" (file Excel) bật/tắt trên web: đọc/chuẩn hóa file bất kỳ có link nhóm, gộp + bỏ
                     trùng (load_groups), xếp ưu tiên (group_priority), sửa/xóa/dán link ghi thẳng vào Excel
  products.py        Sản phẩm + mẫu bình luận: pick_pool (chọn ngẫu nhiên mỗi bài), fill_price ({giá} {giá_mới}
                     {tiết_kiệm}), make_safe, nhập mẫu từ file (split_blocks, guess_product theo mã máy + giá)
  db.py              SQLite (WAL) data/qc_facebook.db — mọi bảng + hàm truy cập, migration ALTER TABLE trong __init__
  poster.py          Đăng bài vào nhóm (ô "Bạn viết gì đi…", dialog chứa textbox + nút Đăng)
  excel_reader.py, image_manager.py   tiện ích nhỏ
web/index.html       Toàn bộ giao diện (1 file, JS thuần): tab Bình luận (khung Tiến trình + nhật ký + bài đã bình luận),
                     tab Sản phẩm (sản phẩm, mẫu bình luận, nhập file), tab Danh sách nhóm (ưu tiên, dán link, sửa/xóa)
tools/import_groups.py  data/nhom_facebook_man_hinh_PC.xlsx → data/groups.xlsx (chạy tay khi sửa file gốc)
tools/dong_goi.py    Tạo zip chuyển máy
data/
  qc_facebook.db     ★ CSDL — nguồn sự thật cho sản phẩm, mẫu bình luận, nhật ký, cài đặt (đừng xóa)
  images/            Ảnh sản phẩm (đăng kèm bình luận)
  groups.xlsx        Danh sách nhóm gốc (215 nhóm; danh sách "main", đang lọc chỉ Hà Nội)
  groups_found.xlsx  Nhóm tự tìm (danh sách "found")
  group_lists/       File Excel nhóm tải lên / dán link từ web (đã chuẩn hóa cột); goc/ = file gốc tải lên
  Coment-Ver3/       30 mẫu bình luận bán hàng hiện dùng (bản đầy đủ + bản không liên hệ, cách nhau bằng ---)
  Coment-Ver2/, comments.txt   Nội dung cũ (chỉ để tham khảo; comments.txt chỉ dùng 1 lần để tạo 3 sản phẩm đầu)
  screenshots/       Ảnh chụp bài sau khi bình luận (<post_id>.png)
  nhat_ky_binh_luan.xlsx  Bản Excel xuất từ CSDL sau mỗi vòng
  schedule.xlsx, group_status.xlsx, group_rules/, post_history.json, schedule_done.json   đăng bài theo lịch / lệnh join cũ
chrome_profile/      Phiên Chrome đã đăng nhập (không đóng gói)   logs/app.log   nhật ký chạy (web đọc đuôi file)
_original/qc-scrip.py   Script gốc trước khi tái cấu trúc (không dùng)
```

## 4. Dữ liệu (SQLite `data/qc_facebook.db`)

| Bảng | Nội dung |
|---|---|
| `posts` | 1 dòng / bài đã xử lý: post_url (UNIQUE — có trong bảng = không bình luận lại), group, status (Hoàn tất / Một phần / Thất bại / Bỏ qua… / "Đang bình luận" = bị tắt giữa chừng, `fix_interrupted` dọn), screenshot, verify_result |
| `comments` | Từng bình luận: post_id, idx, text, image, status (Đã đăng / Chờ duyệt / Bị chặn / Lỗi / Bị từ chối[ · đã xóa]), variant (Đầy đủ / Không SĐT/địa chỉ), variant_id |
| `products` | Sản phẩm: name, price (giá đang bán), new_price (giá mua mới), image, active. Cột text/safe_text = nội dung cũ, chỉ dùng khi sản phẩm chưa từng có mẫu |
| `comment_variants` | Mẫu bình luận: product_id, text, safe_text (trống = tự bỏ dòng SĐT), active, used_count, last_used_at |
| `group_lists` | Danh sách nhóm: key (main / found / u<timestamp>), path, kind, enabled, region_filter (chỉ Hà Nội), priority |
| `priority_groups`, `group_names`, `removed_groups` | Nhóm tick ưu tiên / tên nhóm đọc từ tiêu đề trang / nhóm xóa khỏi danh sách tự tìm (không thêm lại) |
| `group_join` | Kết quả tự tham gia nhóm |
| `safe_groups` | Nhóm dùng bản không SĐT; stop=1 = ngừng bình luận nhóm |
| `runs` | Mỗi vòng quét |
| `settings` | paused, blocked_until, safe_all, groups_searched_at, variants_migrated, progress (JSON tiến trình cho web) |

## 5. Tham số quan trọng (`config.py`)

`MAX_POST_AGE_MINUTES` 1440 · `MAX_POSTS_PER_GROUP` 0 (= không giới hạn) · `COMMENT_TOPICS` ["Màn hình","PC"] · `MAX_COMMENTED_POSTS_PER_DAY` 0 (= không giới hạn) · `TARGET_REGION`/`PRIORITY_REGION` "Hà Nội" · `COMMENT_GAP_MIN/MAX` 15/40 s (giữa các bình luận) · `MIN_DELAY/MAX_DELAY` 30/120 s (giữa các bài) · `BLOCK_COOLDOWN_HOURS` 6 · `VERIFY_AFTER_MINUTES` 60 · `AUTO_JOIN` True, `JOIN_ANSWER` "ok", `JOIN_PER_DAY` 20 · `GROUP_KEYWORDS`, `GROUP_SEARCH_QUERIES`, `GROUP_SEARCH_EVERY_HOURS` 24 · `WATCH_SCROLLS` 60 · `HEADLESS` False · `WEB_PORT` 5000.

Nội dung bình luận / sản phẩm / danh sách nhóm **không** nằm trong config — sửa trên web (lưu CSDL / file Excel), có hiệu lực từ bài / vòng tiếp theo mà không cần khởi động lại.

## 6. Web API (`web.py`)

`/api/summary` `/api/posts?date&status` `/api/runs` `/api/joins` `/api/progress` (+ kiểm tra pid main.py còn sống bằng psutil) `/api/log?n` · `POST /api/pause` `/api/unblock` · `/api/safe`, `POST /api/safe/reset` · sản phẩm: `GET|POST /api/products`, `POST /api/products/<id>` (multipart), `/active`, `DELETE` · mẫu: `GET|POST /api/products/<id>/variants`, `POST …/variants/active`, `POST|DELETE /api/variants/<id>`, `POST /api/variants/import` · nhóm: `GET|POST /api/lists`, `POST|DELETE /api/lists/<key>`, `/api/lists/new`, `/api/lists/<key>/groups` (+`/update`, `/delete`), `/api/lists/<key>/links`, `POST /api/groups/priority`, `/lists/<key>.xlsx` · `/images/*` `/screenshots/*` `/export.xlsx`.

## 7. Lưu ý khi sửa code

- **Facebook đổi giao diện thường xuyên.** Selector nằm ở: `commenter.py` (ô bình luận `div[role=textbox][contenteditable]` aria-label "Bình luận dưới tên…", nhãn "Bị từ chối", nút "Chỉnh sửa hoặc xóa bình luận này" → "Xóa"), `watcher.py` (`//div[@role='feed']/div`, XP_MESSAGE, link bài `/posts/<id>` hoặc `set=pcb.<id>`), `group_checker.py` (nút "Tham gia nhóm"/"Đã tham gia"/"Hủy yêu cầu" — sau khi vào nhóm, mục "Nhóm liên quan" cũng có nút "Tham gia nhóm" nên lấy nút trên cùng và xét "Đã tham gia" trước), `poster.py` ("Bạn viết gì đi…").
- **Chỉ 1 Chrome dùng `chrome_profile/` một lúc.** `create_driver` tự kill Chrome có `chrome_profile` trong command line → chạy thử Selenium khi `main.py` đang chạy sẽ giết Chrome của nó. Kiểm tra trước (psutil, tìm `main.py`).
- **Không tự đăng bài / bình luận / tham gia nhóm thật khi thử nghiệm** nếu chủ dự án chưa đồng ý — dùng `submit=False` (poster), chỉ đọc (scan_group), hoặc CSDL bản sao.
- Thử nghiệm an toàn: sao CSDL bằng `sqlite3.connect(src).backup(dst)` (chép file thường sẽ thiếu dữ liệu nằm trong `-wal`), gán `Config.DB_FILE` trước khi `import web`, dùng `web.app.test_client()`.
- Migration: thêm cột bằng `ALTER TABLE` có kiểm tra `PRAGMA table_info` trong `Database.__init__`; bảng mới thêm vào `SCHEMA` (`CREATE TABLE IF NOT EXISTS`).
- Gõ bình luận: sau khi gõ, nội dung ô soạn được so với văn bản gốc (`_norm`) — **tránh emoji** trong mẫu bình luận (Facebook đổi emoji thành ảnh → lệch → không gửi).
- Ghi file Excel từ web: qua file tạm rồi `os.replace` (file đang mở trong Excel → báo lỗi rõ).
- Console Windows: chạy Python với `PYTHONIOENCODING=utf-8`, file .bat dùng `chcp 65001`. Khi sửa regex qua shell heredoc, `\b` dễ bị biến thành ký tự backspace — dùng công cụ Edit/Write.
- Không đóng gói / chia sẻ: `chrome_profile/`, `.env` (nếu có), và nhớ CSDL chứa SĐT + nhật ký của chủ shop.
