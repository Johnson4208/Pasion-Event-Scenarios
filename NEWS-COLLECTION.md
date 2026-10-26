# Kiểm tra tin tức đã thu thập và dữ liệu cũ

Màn hình Event Scenarios và Company News đọc các kho khác nhau. **“0 observations collected” trong Outcome Data không có nghĩa là không thu thập được tin tức.** Đó là số quan sát kết quả lịch sử trong kho dùng để chuẩn bị mô hình xác suất.

## Xem số liệu trong Event Scenarios

Sau khi phân tích, phần **News collection status** cho biết số mục nguồn trả về, số bài giữ lại sau lọc và số bài thuộc khu vực đang chọn. Mở **Collection and filtering details** để thấy số bài cũ, trùng, ngoài chủ đề, thời gian không hợp lệ và kết quả từng yêu cầu nguồn.

Bốn yêu cầu Google News theo các phiên bản ngôn ngữ và một yêu cầu GDELT không phải năm nhà xuất bản độc lập. Nhiều yêu cầu có thể trả cùng một bài. Tin ngoài khu vực vẫn có thể đọc trong **All sources**, nhưng không tự được tính thành bằng chứng trong nước.

Bản sửa này xử lý các lỗi đã xác nhận:

- Google News tiếng Việt dùng mã chuẩn `vi`; mã `vi-VN` trả chuyển hướng và từng khiến yêu cầu bị từ chối.
- Truy vấn tiếng Việt có từ khóa đúng cho từng yếu tố, thay vì dùng nguyên từ khóa tiếng Anh.
- Hà Nội/Hanoi, TP.HCM/Ho Chi Minh City và các địa danh đã định nghĩa được nhận diện trong nội dung. Tên hoặc nơi đặt tòa soạn không đủ chứng minh bài nói về khu vực đó.
- Khoảng lấy tin được chuyển xuống các nguồn đúng theo cửa sổ của báo cáo. Kỳ hạn dự báo và cửa sổ lấy tin vẫn là hai khái niệm khác nhau.
- Các tiêu đề giống nhau ở những ngày khác nhau được giữ thành các báo cáo riêng. Cùng tiêu đề, cùng ngày được gộp; thứ tự từ trong tiêu đề được giữ để không nhập nhầm hai nội dung khác nhau.
- Kết quả từng nguồn và mã lỗi HTTP được giữ cả khi mọi nguồn đều thất bại.

Các phép lọc vẫn dựa trên tiêu đề và đoạn trích. Ngày cập nhật của một bài không chứng minh sự kiện trong bài vừa xảy ra; cần đọc nguồn để đánh giá bối cảnh lịch sử, đối tượng và thời điểm.

## Mở lại tin đã lưu

Trong Event Scenarios, phần **Previously collected reporting** có hai nút:

- **Read collector archive** mở các phiên bản Event Agent đã lưu cho đúng yếu tố, khu vực và kỳ hạn. Chọn ngày thu thập để xem một bản cũ. Không có watch tương ứng khác với việc toàn bộ kho không tồn tại.
- **Read Company News library** mở tối đa 200 bài mới nhất do API kho tin trả về. Kho này bao gồm nhiều chủ đề; không phải mọi bài đều liên quan đến kịch bản đang chọn.

Các bài trong kho giữ thời gian và nguồn gốc. Mở chúng không đổi điểm số hoặc xác suất của báo cáo hiện tại. Giao diện không tự lấy bài cũ làm tin mới, không tự gán trạng thái kiểm định và không dựng lại phần trăm thử nghiệm từ báo cáo cũ.

Company News hiện phân biệt rõ đang tải, phiên đăng nhập hết hạn, lỗi truy cập, lỗi đọc kho, kho trống và bộ lọc không khớp. Nút **Retry loading news** đọc lại kho; nó không đăng ký nguồn hay tự tải dữ liệu từ Internet. Chỉ số nguồn đăng ký phản ánh lần tiếp nhận gần nhất, không chứng minh nguồn đã đầy đủ hoặc mọi khẳng định đã được duyệt.

## Khi đổi thư mục hoặc cài bản ZIP mới

| Dữ liệu | Nơi lưu mặc định |
| --- | --- |
| Bài và nguồn của Company News, bookmark theo tài khoản | `backend/accounts.sqlite3` |
| Các lần thu thập và bản tin Event Agent | `event-agent-state/intelligence.sqlite3` |
| Quan sát kết quả lịch sử phục vụ chuẩn bị mô hình | `backend/private-event-models/outcomes.sqlite3` |
| Báo cáo Event Scenarios do người dùng bấm lưu | localStorage của hồ sơ trình duyệt và địa chỉ web |

ZIP mã nguồn không chứa các kho riêng này. Chạy ứng dụng ở một thư mục mới không tự đọc dữ liệu trong thư mục cũ. Nếu bản cũ từng có nhiều tin, dùng **RECOVER-BACKEND.cmd** theo [BACKEND-RECOVERY.md](BACKEND-RECOVERY.md), chọn bản có dữ liệu cần giữ và khôi phục vào một thư mục hoàn chỉnh mới. Giữ nguyên bản gốc để đối chiếu; không gửi database hoặc cấu hình bí mật lên GitHub.

Event Agent chỉ tiếp tục thu thập nền khi được bật. Trên Windows CMD, sau khi cài môi trường, có thể bật các watch đã cấu hình bằng:

```cmd
set PASION_EVENT_AGENT_ENABLED=1
npm.cmd run dev
```

Tùy chọn này chỉ áp dụng cho cửa sổ CMD đó. Watch mặc định không bao phủ mọi yếu tố/khu vực/kỳ hạn. Bật agent không phục hồi dữ liệu đã mất và không tự cung cấp mô hình xác suất. Nếu đã đặt đường dẫn kho tùy chỉnh bằng biến môi trường, cần dùng đúng đường dẫn cũ hoặc chuyển dữ liệu có chủ đích.

Nhiều tin tức chưa tự tạo ra xác suất. Phần mô hình và kết quả lịch sử được giải thích riêng trong [EVENT_PROBABILITIES.md](EVENT_PROBABILITIES.md).
