# QC-Facebook — tài liệu nhanh cho AI / người mới

Đọc file này trước khi mò code. Tài liệu chi tiết cho người dùng: `README.md`. Toàn bộ giao diện, log, chú thích code đều **tiếng Việt** — giữ nguyên phong cách đó.

## 1. Dự án làm gì

Bot Selenium (Python, Windows) điều khiển Chrome đã đăng nhập Facebook của **chủ shop bán màn hình máy tính cũ ở Hà Nội** (64 Cầu Diễn):

1. **Tự bình luận quảng cáo** vào bài mới (≤ 6 giờ, `MAX_POST_AGE_MINUTES`) trong các nhóm Facebook mua bán màn hình / PC. Mỗi bài nhận 1 bình luận / sản phẩm đang bật (hiện 3 màn MSI), kèm ảnh. Nội dung chọn **ngẫu nhiên** trong các mẫu đang bật, không trùng trong 1 bài, tránh lặp trong cùng nhóm.
2. **Chỉ bình luận bài đáng bình luận** — chuỗi bộ lọc `modules/filters.py`, mọi quyết định ghi kèm lý do (bảng `post_decisions`, web tab "Phân loại bài"):
   - **Nhóm**: ≥ `GROUP_MIN_MEMBERS` (5.000) thành viên — nhóm Hà Nội (`group_finder.is_hanoi_group`) chỉ cần ≥ `GROUP_MIN_MEMBERS_HANOI` (500), đọc ở trang Giới thiệu (`modules/group_stats.py`, cache 24 giờ trong bảng `group_stats`); không đọc được → bỏ nhóm.
   - **Bài**: chủ đề **màn hình** (COMMENT_TOPICS; bỏ PC / linh kiện lẻ / laptop / điện thoại) (`modules/topic.py`) → ý định **MUA** (bỏ BÁN / KHÔNG XÁC ĐỊNH; `modules/intent.py`, từ khóa trong `data/tu_khoa_mua_ban.txt`) ; từ khóa chấm KHÔNG XÁC ĐỊNH thì hỏi **Gemini** (`modules/ai_intent.py`, cache bảng `ai_intent`, khóa trong `.env`) → **khu vực**: khách ghi rõ ở xa (HCM, miền Nam/Trung, tỉnh xa) mà không nhắc Hà Nội/lân cận → bỏ (`modules/region.py`, danh sách GẦN/XA trong `data/khu_vuc.txt`; shop chỉ bán Hà Nội & lân cận — 08/10: 42/125 bài MUA là khách xa) → điểm tương tác ≥ `POST_MIN_ENGAGEMENT` (`modules/engagement.py`). **Chủ shop muốn bình luận bài cần mua càng sớm càng tốt, không chờ tương tác → `POST_MIN_ENGAGEMENT = 0`** (khi 0 không đọc tương tác). Bộ lọc đắt (đọc tương tác, rê chuột lấy link) chỉ chạy khi bộ lọc trước đạt; quét 1 nhóm tối đa `GROUP_SCAN_MAX_SECONDS` (120 s).
3. **Tự xử lý bị từ chối**: bình luận bị gắn "Bị từ chối" → xóa ngay → gửi lại bản **không SĐT/địa chỉ**; nhóm đó từ nay dùng bản an toàn; bản an toàn cũng bị từ chối → ngừng nhóm. Facebook báo chặn → nghỉ 6 giờ.
4. **Tự tham gia nhóm** chưa vào (cuối mỗi vòng, điền "ok" vào câu hỏi, tick hết) và **tự tìm nhóm mới** theo từ khóa mỗi ngày.
5. **Đăng bài theo lịch** (`data/schedule.xlsx`) — tính năng phụ.
6. **Web quản lý** Flask `http://127.0.0.1:5000`: tiến trình trực tiếp, nhật ký bình luận, sản phẩm + mẫu bình luận, danh sách nhóm (file Excel), tạm dừng.

Chạy liên tục theo **vòng**: lần lượt từng nhóm (đã xếp ưu tiên) → quét hết bài mới → bình luận hết → nhóm sau → cuối vòng tham gia nhóm + kiểm tra lại bài cũ + (mỗi 24h) tìm nhóm mới → quét lại.

**Xoay vòng nhóm** (`modules/group_yield.py`, bảng `group_scans`): trước 08/10 bot không bao giờ quét quá nhóm 7/56 (quét lại nhóm hot + bình luận chiếm hết thời gian, vòng luôn bắt đầu lại từ nhóm 1). Nay: thứ tự = hot → "Ưu tiên" → nhóm có nhiều bài cần mua (YIELD_DAYS) → nhóm chưa quét → nhóm ít khách; nhóm thường quét xong `GROUP_RESCAN_MINUTES` phút mới quét lại, nhóm ít khách `LOW_YIELD_RESCAN_HOURS` giờ. Nhóm báo "không xem được nội dung này" (`gc.UNAVAILABLE`, lưu trong `group_join`) bị bỏ qua `GROUP_UNAVAILABLE_RETRY_HOURS` giờ — nhóm Thanh Lý 760589759199370 (417k thành viên, nhóm hot) rơi vào trạng thái này sau khi bot bình luận 32 bài / 2,5 giờ tối 06/10.

**Chạy song song (10/10, `PARALLEL = True`)** — 1 cửa sổ BÌNH LUẬN + `SCAN_WINDOWS` (2) cửa sổ QUÉT, mỗi tiến trình 1 Chrome riêng (`chrome_profile`, `chrome_profile_quet`, `chrome_profile_quet2`); các cửa sổ quét chia nhóm qua bảng `scan_claims` (giữ chỗ khi quét, `finished_at` = lần thử gần nhất dùng chung, giữ chỗ quá 3 phút coi như bỏ). Chrome chạy với `--disable-features=AsyncDns,DnsOverHttps --dns-prefetch-disable` (3 Chrome dùng DNS riêng bị ERR_NAME_NOT_RESOLVED liên tục); lỗi mạng khi quét -> chờ 20 giây quét tiếp, bình luận thất bại chưa gửi được gì -> trả lại hàng chờ thử lại 1 lần. Chi tiết, nói chuyện qua bảng `post_queue`: **cửa sổ QUÉT** `python main.py quet` (`modules/scanner.py`, Chrome `chrome_profile_quet/` chép từ `chrome_profile/` bằng `python main.py taophienquet`) lặp: `group_yield.next_group` chọn nhóm (hot 3 phút, nhóm có khách/≥100 bài/ngày 10 phút, thường 60 phút, ít khách 24 giờ; cùng lúc thì `group_score` cao trước: khách tìm màn hình + tương tác TB mỗi bài (đo khi quét, cột `group_scans.avg_interactions`) + bài/ngày + thành viên) → `GroupWatcher.check_and_scan` chỉ xét bài sau lần quét trước (`scan_window`) → bài đạt lọc vào hàng chờ; chỉ đọc, ghi tiến trình riêng `settings.scan_progress`. **Cửa sổ BÌNH LUẬN** `python main.py` (`run_queue_scheduler` + `modules/queue_runner.py`): luôn lấy bài `posted_at` mới nhất (`db.next_queued`, quá MAX_POST_AGE → Quá hạn) → `comment_post`; rảnh thì tham gia ≤2 nhóm `Chưa tham gia` (cửa sổ quét ghi) + verify ≤5 bài + tìm nhóm mới; đăng bài theo lịch bằng `post_due(driver)` (KHÔNG dùng `schedule.run_pending` — sẽ mở Chrome thứ 3 trùng profile). `modules/browser.py`: so khớp profile CHÍNH XÁC (`chrome_profile` ≠ `chrome_profile_quet`) khi tắt Chrome sót. Chưa có `chrome_profile_quet/` → `run_scheduler` tự chạy cách cũ (1 cửa sổ). 09/10 cách cũ: bài đã đăng trung vị 60 phút mới được bình luận.

## 2. Chạy

**Máy mới** (Windows, cần Python ≥ 3.10 + Google Chrome): giải nén zip → bấm đúp `cai-dat.bat` (tạo `.venv`, cài `requirements.txt`, mở Chrome để **đăng nhập Facebook bằng tay**, nhấn Enter) → bấm đúp `chay-ngam.bat`.
Phiên đăng nhập nằm ở `chrome_profile/` — **không chép được sang máy khác** (cookie mã hóa DPAPI theo tài khoản Windows) nên máy mới luôn phải `python main.py login`. **Không chạy 2 máy cùng 1 tài khoản.**

| Lệnh / file | Tác dụng |
|---|---|
| `chay-ngam.bat` | Mở 3 cửa sổ thu nhỏ: `web.py`, `main.py` (cửa sổ BÌNH LUẬN) và — nếu có `chrome_profile_quet/` — `main.py quet` (cửa sổ "QC-Facebook Quet"), rồi mở web quản lý |
| `mo-web.bat` | Chỉ mở web |
| `cai-dat.bat` / `dong-goi.bat` | Cài trên máy mới / đóng gói zip để chuyển máy (`tools/dong_goi.py`) |
| `python main.py` | Chạy nền liên tục (= `run_scheduler`) |
| `python main.py watch` | Chạy đúng 1 vòng |
| `python main.py login` | Mở Chrome để đăng nhập tay |
| `python main.py testcomment <link bài> [N]` | Bình luận tay 1 bài (N = chỉ sản phẩm thứ N) |
| `python main.py findgroups` / `join` / `cleanup [ngày]` | Tìm nhóm mới / kiểm tra-tham gia nhóm / xóa bình luận bị từ chối còn sót |
| `python main.py test [N\|link nhóm]` / `post` | Đăng thử / đăng ngay bài trong lịch |
| `python main.py thuquet [N\|link nhóm]` | **Chạy thử an toàn**: quét + phân loại + đọc số thành viên, KHÔNG bình luận / tham gia nhóm (`GroupWatcher(dry_run=True)`) |
| `python main.py phanloai "nội dung"` / `capnhatnhom` | Chấm thử 1 câu MUA/BÁN / đọc lại số thành viên mọi nhóm |
| `python -m pytest` | Test (`tests/`, cần `requirements-dev.txt`) — không mở Chrome, dùng CSDL tạm |
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
                     check_and_scan (cửa sổ quét: kiểm tra nhóm + quét bài trong ... phút, ghi group_join/group_scans)
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
  poster.py          Đăng bài vào nhóm (ô "Bạn viết gì đi…", dialog chứa textbox + nút Đăng). Nhóm không đăng được vì lý do
                     của nhóm (chưa tham gia / không xem được / chỉ "Bán gì đó" / đầy bài chờ duyệt) không tính là hỏng,
                     ghi nhớ để bỏ qua (group_join / bảng post_skips); cửa sổ không đóng → ghi thông báo + ảnh chụp
  region.py          Khu vực người cần mua (GẦN / XA) từ data/khu_vuc.txt — dùng chung parse_sections/load_cached của intent.py
  group_yield.py     Xoay vòng nhóm: rank_by_yield (thứ tự quét), scan_due (tới lượt quét lại), posting_order (thứ tự đăng bài)
  scanner.py         Cửa sổ QUÉT (Scanner.step: chọn nhóm → check_and_scan → db.enqueue_post)
  queue_runner.py    Cửa sổ BÌNH LUẬN khi chạy song song (QueueRunner.step: bài mới nhất trong hàng chờ → comment_post; idle/housekeep)
  browser.py         Chrome profile: is_profile_process (khớp chính xác), close_leftover_chrome, copy_profile (bỏ cache/khóa)
  fb_selectors.py    ★ MỌI selector / aria-label / chữ giao diện Facebook (XPath, cụm "Bị từ chối", trang Giới thiệu,
                     nhãn cảm xúc…) — Facebook đổi giao diện thì sửa ở đây; module khác không tự viết XPath
  filters.py         Chuỗi bộ lọc POST_FILTERS (chủ đề → MUA/BÁN → khu vực → tương tác) / GROUP_FILTERS (thành viên → bài/ngày),
                     mỗi tiêu chí 1 hàm (subject, config) -> Verdict(ok, lý do); PostCandidate tính lười (cached_property)
  intent.py          Phân loại MUA / BÁN / KHÔNG XÁC ĐỊNH theo từ khóa có trọng số (data/tu_khoa_mua_ban.txt, tự đọc lại khi file đổi)
  engagement.py      Đọc số cảm xúc / bình luận / chia sẻ từ chữ ô bài + aria-label, tính điểm theo ENGAGEMENT_WEIGHTS
  ai_intent.py       Gemini (REST, urllib) chấm MUA / BÁN / KHÁC cho bài từ khóa chưa chắc; cache bảng ai_intent, giới hạn/ngày,
                     lỗi -> None (bài giữ KHÔNG XÁC ĐỊNH). Test dùng hàm hỏi giả, không gọi mạng
  group_stats.py     Đọc số thành viên / bài mỗi ngày ở trang Giới thiệu nhóm, cache trong bảng group_stats
  topic.py           topic(): Màn hình / PC / Laptop / None
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
| `settings` | paused, blocked_until, safe_all, groups_searched_at, variants_migrated, progress (JSON tiến trình cho web), group_stats_refresh (web bấm "Cập nhật số thành viên") |
| `group_stats` | Số thành viên / bài mỗi ngày từng nhóm + fetched_at, error (cache GROUP_STATS_CACHE_HOURS; lỗi thử lại sau GROUP_STATS_RETRY_MINUTES) |
| `post_decisions` | Mọi quyết định Bình luận / Bỏ qua: 1 dòng / (group_url, text_key = sha1 nội dung) — topic, intent + từ khóa khớp, cảm xúc/bình luận/chia sẻ/điểm, reason, seen_count |
| `group_scans` | Mỗi lần quét đầy đủ 1 nhóm (không tính quét lại nhóm hot, không ghi khi chạy thử): group_url, scanned_at, found — cùng post_decisions (decision Bình luận) tính `group_yields` cho xoay vòng nhóm; giữ 30 ngày |
| `post_skips` | Nhóm tạm không đăng bài bán: reason (chỉ "Bán gì đó" → 30 ngày, đầy bài chờ duyệt → 24 giờ), until |
| `post_queue` | Hàng chờ bình luận (chạy song song): post_url UNIQUE, group, post_text, topic, post_age_min, posted_at (ước = found_at − tuổi), group_score, status Chờ / Đang bình luận / Xong / Bỏ qua / Quá hạn, result; `requeue_interrupted` trả bài dở về Chờ khi khởi động; giữ 7 ngày |
| `scan_claims` | 1 dòng / nhóm: cửa sổ quét nào đang quét (scanner, claimed_at), finished_at = lần quét / thử gần nhất (dùng chung cho `next_group`) |

## 5. Tham số quan trọng (`config.py`)

`MAX_POST_AGE_MINUTES` 360 · `REGION_FILTER` True, `REGION_FILE` data/khu_vuc.txt, `REGION_REQUIRED_IN_NATIONAL_GROUPS` True (nhóm toàn quốc chỉ nhận bài ghi Hà Nội/lân cận; nhóm Hà Nội = `watcher.is_hanoi_group`) · `GROUP_RESCAN_MINUTES` 120, `YIELD_DAYS` 7, `LOW_YIELD_MIN_SCANS` 3, `LOW_YIELD_RESCAN_HOURS` 24, `GROUP_UNAVAILABLE_RETRY_HOURS` 24 · `MAX_POSTS_PER_GROUP` 0 (= không giới hạn) · `COMMENT_TOPICS` ["Màn hình"] (chủ shop 08/10: chỉ bài tìm màn hình, bỏ bài tìm PC / linh kiện) · `MAX_COMMENTED_POSTS_PER_DAY` 40 (đủ thì nghỉ tới 0 giờ; 0 = không giới hạn) · `TARGET_REGION`/`PRIORITY_REGION` "Hà Nội" · `COMMENT_GAP_MIN/MAX` 15/40 s (giữa các bình luận) · `MIN_DELAY/MAX_DELAY` 30/120 s (giữa các bài) · `BLOCK_COOLDOWN_HOURS` 6 · `VERIFY_AFTER_MINUTES` 60 · `HOT_GROUPS` (nhóm tương tác cao, đứng đầu vòng) + `HOT_RESCAN_MINUTES` 5 (quét lại xen giữa vòng, `GroupWatcher._rescan_hot`) · `GROUP_MIN_MEMBERS` 5000, `GROUP_MIN_POSTS_PER_DAY` 0, `GROUP_STATS_CACHE_HOURS` 24, `GROUP_SCAN_MAX_SECONDS` 120 · `INTENT_FILTER` True, `INTENT_KEYWORDS_FILE`, `INTENT_MIN_SCORE` 3 / `INTENT_MARGIN` 2 · `POST_MIN_ENGAGEMENT` 0, `ENGAGEMENT_WEIGHTS` 1/2/3 · `INTENT_AI` True, `GEMINI_MODEL` "gemini-flash-lite-latest", `GEMINI_MAX_CALLS_PER_DAY` 500 (`GEMINI_API_KEY` từ `.env` — không đóng gói, không commit) · `AUTO_JOIN` True, `JOIN_ANSWER` "ok", `JOIN_PER_DAY` 20 · `GROUP_KEYWORDS`, `GROUP_SEARCH_QUERIES`, `GROUP_SEARCH_EVERY_HOURS` 24 · `WATCH_SCROLLS` 60 · `HEADLESS` False · `WEB_PORT` 5000.

Nội dung bình luận / sản phẩm / danh sách nhóm **không** nằm trong config — sửa trên web (lưu CSDL / file Excel), có hiệu lực từ bài / vòng tiếp theo mà không cần khởi động lại.

## 6. Web API (`web.py`)

`/api/summary` `/api/posts?date&status` `/api/runs` `/api/joins` `/api/progress` (+ kiểm tra pid main.py còn sống bằng psutil) `/api/log?n` · `POST /api/pause` `/api/unblock` · `/api/safe`, `POST /api/safe/reset` · sản phẩm: `GET|POST /api/products`, `POST /api/products/<id>` (multipart), `/active`, `DELETE` · mẫu: `GET|POST /api/products/<id>/variants`, `POST …/variants/active`, `POST|DELETE /api/variants/<id>`, `POST /api/variants/import` · nhóm: `GET|POST /api/lists`, `POST|DELETE /api/lists/<key>`, `/api/lists/new`, `/api/lists/<key>/groups` (+`/update`, `/delete`), `/api/lists/<key>/links`, `POST /api/groups/priority`, `/lists/<key>.xlsx` · `/images/*` `/screenshots/*` `/export.xlsx`.

## 7. Lưu ý khi sửa code

- **Facebook đổi giao diện thường xuyên.** Mọi selector nằm trong `modules/fb_selectors.py` — thêm selector mới cũng đặt ở đó. Lưu ý: sau khi vào nhóm, mục "Nhóm liên quan" cũng có nút "Tham gia nhóm" nên `group_checker` lấy nút trên cùng và xét "Đã tham gia" trước. Tương tác (10/2026): các con số ngay dưới nội dung bài theo thứ tự cảm xúc → bình luận → chia sẻ (số 0 không hiện), có cảm xúc thì có nhãn "Thích: N người"; trang Giới thiệu ghi "Tổng cộng 417.705 thành viên", "Hôm nay có 236 bài viết mới". Kiểm tra lại giao diện bằng `python main.py thuquet 1` (không bình luận).
- **Thêm tiêu chí lọc**: viết hàm `(post|stats, config) -> Verdict` trong `filters.py`, thêm vào `POST_FILTERS` / `GROUP_FILTERS` — không sửa `watcher.py`. Bộ lọc tốn công đặt cuối.
- **Sửa từ khóa MUA/BÁN**: chạy lại `python -m pytest tests/test_intent.py` (nghiệm thu 20 bài, không bài BÁN nào thành MUA). Không gõ regex có `\` qua heredoc shell — dùng Edit/Write.
- **Chỉ 1 Chrome dùng `chrome_profile/` một lúc.** `create_driver` tự kill Chrome có `chrome_profile` trong command line → chạy thử Selenium khi `main.py` đang chạy sẽ giết Chrome của nó. Kiểm tra trước (psutil, tìm `main.py`).
- **Không tự đăng bài / bình luận / tham gia nhóm thật khi thử nghiệm** nếu chủ dự án chưa đồng ý — dùng `submit=False` (poster), chỉ đọc (scan_group), hoặc CSDL bản sao.
- Thử nghiệm an toàn: sao CSDL bằng `sqlite3.connect(src).backup(dst)` (chép file thường sẽ thiếu dữ liệu nằm trong `-wal`), gán `Config.DB_FILE` trước khi `import web`, dùng `web.app.test_client()`.
- Migration: thêm cột bằng `ALTER TABLE` có kiểm tra `PRAGMA table_info` trong `Database.__init__`; bảng mới thêm vào `SCHEMA` (`CREATE TABLE IF NOT EXISTS`).
- Gõ bình luận: sau khi gõ, nội dung ô soạn được so với văn bản gốc (`_norm`) — **tránh emoji** trong mẫu bình luận (Facebook đổi emoji thành ảnh → lệch → không gửi).
- Ghi file Excel từ web: qua file tạm rồi `os.replace` (file đang mở trong Excel → báo lỗi rõ).
- Console Windows: chạy Python với `PYTHONIOENCODING=utf-8`, file .bat dùng `chcp 65001`. Khi sửa regex qua shell heredoc, `\b` dễ bị biến thành ký tự backspace — dùng công cụ Edit/Write.
- Không đóng gói / chia sẻ: `chrome_profile/`, `.env` (nếu có), và nhớ CSDL chứa SĐT + nhật ký của chủ shop.
