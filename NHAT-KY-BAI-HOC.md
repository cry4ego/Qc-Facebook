# Nhật ký bài học (growth-log)

Mỗi mục: chuyện gì xảy ra → nguyên nhân gốc → **quy tắc dùng lại được** → dấu hiệu để nhận ra lần sau. Viết ngắn, thêm mục mới lên đầu.
Không ghi dữ liệu của khách hay SĐT vào file này.

## 29/10/2026 — Ca thử chép từ dữ liệu thật mang theo SĐT của khách
- **Chuyện:** ngay trước khi commit, soát lại thì thấy 3 số điện thoại trong test (`tests/test_danh_gia.py`) là số THẬT của khách (có trong 6, 1, 5 bài) — tôi lấy chính các ca bộ che bỏ sót làm ca thử. Remote GitHub lại công khai. Đã thay bằng số bịa cùng kiểu viết trước khi commit; lịch sử git chưa từng chứa chúng.
- **Quy tắc:** ca khó lấy từ production thì giữ KIỂU viết, thay GIÁ TRỊ (số, tên, link) bằng giá trị bịa. Trước mỗi commit, quét mọi chuỗi giống SĐT trong file sắp commit và đối chiếu với bài thật trong CSDL (bỏ qua SĐT của shop).
- **Nhận ra:** ca thử "giống thật quá" — một số điện thoại cụ thể, đầy đủ mà không phải số của shop.

## 29/10/2026 — Đo bằng số thật trước khi tin, và xem tay chính các ca "sai"
- **Chuyện:** bộ đánh giá báo "52 bài còn lộ chuỗi giống SĐT" sau khi che. Xem tay thì có 47 bài là SĐT thật bị che sót (dính liền chữ, thiếu số 0 đầu), nhưng sau khi sửa thì thước đo thô vẫn báo 35 bài — hóa ra là thông số máy, năm, giá.
- **Nguyên nhân gốc:** thước đo "≥ 9 chữ số bất kỳ" nối số qua cả dấu xuống dòng nên vừa bỏ sót vừa báo nhầm.
- **Quy tắc:** mỗi chỉ số tự động phải được kiểm bằng cách đọc tay cả ca nó báo "sai" lẫn một ít ca nó báo "đúng". Thước đo sai làm ta sửa nhầm chỗ hoặc yên tâm nhầm.
- **Nhận ra:** con số lỗi không giảm về 0 dù đã sửa; hoặc số lỗi lớn mà đọc mẫu thấy toàn thứ vô hại.

## 29/10/2026 — Bộ chặn chỉ tốt bằng bộ tấn công thử nó
- **Chuyện:** bộ chặn thẻ bình luận cho lọt số điện thoại viết tách từng chữ số (`0 9 0 2 …`), dù 90+ test của chính tôi đều xanh.
- **Nguyên nhân gốc:** người viết bộ chặn cũng là người viết ca thử, nên chỉ thử những kiểu mình đã nghĩ tới. Bộ đánh giá có danh sách tấn công tổng hợp riêng mới lộ ra.
- **Quy tắc:** với bộ chặn an toàn, luôn có một danh sách tấn công do người khác (hoặc dữ liệu thật) cung cấp. Lần này người duyệt thứ hai (agent red-team) bị bộ phân loại an toàn chặn nên KHÔNG hoàn thành — đừng coi bước đó là đã làm; ghi rõ là còn thiếu.
- **Nhận ra:** toàn bộ ca thử đều do một người viết; chưa từng có ca nào bị bộ chặn từ chối "ngoài dự kiến".

## 29/10/2026 — Hai người gán nhãn cùng họ mô hình thì đồng thuận bị thổi phồng
- **Chuyện:** hai người gán nhãn (tôi và một agent độc lập) khớp 95% (kappa 0,94–0,99). Con số đẹp nhưng cả hai đều là AI cùng họ, nên sai lệch giống nhau (ví dụ coi người hỏi tư vấn chọn màn là khách mua) không hiện ra.
- **Quy tắc:** đồng thuận giữa các bản sao của cùng một nguồn không chứng minh nhãn đúng. Cần ít nhất một lượt người thật (chủ shop) gán lại các ca bất đồng và một mẫu ngẫu nhiên các ca đồng thuận.
- **Nhận ra:** kappa cao bất thường trên dữ liệu mơ hồ như bài đăng mạng xã hội.

## 28/10/2026 — Tiến trình đang chạy giữ mã cũ trong bộ nhớ
- **Chuyện:** sửa xong khuôn bình luận nhưng cửa sổ họp và web vẫn là tiến trình cũ; nút "Đồng ý và làm luôn" vẫn có thể ghép khuôn cũ.
- **Nguyên nhân gốc:** Python nạp code một lần lúc khởi động; sửa file không đổi tiến trình đang chạy. Cửa sổ bình luận thì đọc mẫu từ CSDL mỗi bài nên không bị.
- **Quy tắc:** sau khi sửa code, hỏi "tiến trình nào đang chạy file này?" và khởi động lại đúng những cái đó. Dùng `tools/kiem_tra_van_hanh.py` (so giờ khởi động với giờ sửa file).
- **Nhận ra:** hành vi mới không xuất hiện dù test xanh; đề xuất sinh ra vẫn theo khuôn cũ.

## 28/10/2026 — Lệnh nạp nội dung tạo lại thứ chủ shop đã xóa
- **Chuyện:** chủ shop xóa sản phẩm MSI PRO MP273QP ở tab Sản phẩm; `main.py noidung` sẽ tạo lại nó vì còn trong `cau-hinh.json`.
- **Quy tắc:** trước khi chạy một lệnh "nạp lại từ nguồn" lên dữ liệu thật, đọc trạng thái hiện tại và đối chiếu — thứ người dùng vừa xóa bằng tay có thể bị nguồn khôi phục. Làm trên bản sao, loại các mục đã bị xóa, rồi mới nạp.
- **Nhận ra:** thử trên bản sao thấy số sản phẩm hoặc id khác với CSDL thật.

## 28/10/2026 — "Không thấy .git" không có nghĩa là không có kho git
- **Chuyện:** tôi nói kho git không tồn tại vì công cụ tìm file bỏ qua thư mục ẩn; thực ra kho có sẵn 5 commit và một remote GitHub công khai.
- **Quy tắc:** muốn biết có kho git hay không thì hỏi chính git (`git rev-parse --show-toplevel`, `git log`), đừng suy ra từ việc tìm file. Trước khi commit vào một kho đã có, xem `git remote -v` và đừng đẩy lên khi chưa được hỏi.
- **Nhận ra:** `git init` im lặng không in "Initialized empty repository".
