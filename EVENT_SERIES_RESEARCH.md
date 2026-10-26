# Xác suất nghiên cứu từ chuỗi quan sát thật

Event Scenarios ưu tiên **toàn bộ kết quả cuối kỳ trong cùng một nhóm**. Khi có mô hình phù hợp, giao diện hiển thị mọi xác suất, khoảng bất định 95%, chênh lệch và tổng của nhóm. Tin tức, các đường nghiên cứu chồng lấn và thông tin lấy nguồn nằm trong phần bằng chứng bổ sung.

Bạn đã chọn hiển thị **ước tính nghiên cứu kèm mức kiểm định**, nên hệ thống không yêu cầu gọi một mô hình thử nghiệm là “đã hiệu chuẩn” mới được xem kết quả. Các ước tính dưới đây dùng dữ liệu quan sát thật; chúng vẫn có giới hạn về tính đại diện, thay đổi chế độ và phiên bản dữ liệu.

## Hai câu hỏi có quy trình tự động

| Yếu tố và khu vực | Chuỗi nguồn | Nhóm kết quả |
| --- | --- | --- |
| Markets → Equity volatility → United States | FRED `VIXCLS`, mức đóng cửa chỉ số VIX | Năm khoảng thay đổi tương đối, với các ranh giới −25%, −10%, +10%, +25% |
| Real Estate → Mortgage rates → United States | FRED `MORTGAGE30US`, lãi suất khảo sát vay cố định 30 năm | Ba khoảng thay đổi theo điểm phần trăm, với các ranh giới −0,25 và +0,25 |

Hai nguồn đã được kiểm tra truy cập thực. Danh sách câu hỏi trong ứng dụng công bố những trường hợp được hỗ trợ, thay vì ngụ ý mọi yếu tố/khu vực đều có mô hình. Kỳ hạn vẫn phải phù hợp tần suất quan sát và có đủ lịch sử.

Trong ứng dụng, chọn một câu hỏi được hỗ trợ rồi bấm **Calculate scenario probabilities**. Máy chủ tự lấy hoặc dùng lại bản dữ liệu còn mới, lưu nguồn và dấu vết, tạo các kết quả lịch sử theo định nghĩa, kiểm tra kỳ sau và trả toàn bộ nhóm. Không cần tự viết JSON hay chạy lệnh xây catalog. Bấm xem tin bổ sung không thay đổi mô hình đã tính.

## Xác suất có nghĩa gì?

Đây là **ước tính tham chiếu từ tần suất thay đổi lịch sử**, không phải mô hình đã học tác động số học của tin tức hôm nay. Kết quả dự báo một giá trị của chỉ số được định nghĩa, không đại diện cho mọi khía cạnh của “thị trường tốt/xấu” hay “điều kiện cải thiện/xấu đi”.

Mỗi nhóm có các ranh giới đo lường công khai, không chồng lấn và bao phủ mọi giá trị. Thay định nghĩa kết quả phải thay phiên bản và tính lại cả nhóm. Không gán số cho từng đường nghiên cứu chồng lấn rồi ép chúng cộng thành 100%.

Với `K` kết quả và `N` cửa sổ huấn luyện, xác suất của kết quả có số lần quan sát `c` là `(c + 0,5) / (N + K/2)`. Nửa đếm Jeffreys áp dụng đối xứng cho mọi kết quả. Nó giữ bất định cho lớp chưa được quan sát, không phải một mức 50% riêng cho từng kịch bản. Khoảng 95% là khoảng hậu nghiệm cho tần suất của nhóm tham chiếu dưới các giả định mô hình; không phải bảo đảm bao phủ kết quả tương lai.

## Thời điểm và kiểm tra lịch sử

- Nguồn cho biết **ngày quan sát**, không cung cấp đầy đủ thời điểm xuất bản lịch sử. Hệ thống giữ thời điểm thu thập thực và không dựng `known_at`, ngày duyệt hay ngày công bố trong quá khứ.
- Đầu ra công khai mốc dự báo, ngày cuối kỳ, giá trị/ngày quan sát làm gốc và độ trễ của nguồn. Thời gian lịch sử tương ứng tính cả khoảng cách từ quan sát gốc đến ngày cuối kỳ.
- Các cửa sổ lịch sử không chồng lấn. Mỗi kết quả dùng quan sát hợp lệ cuối cùng tại hoặc trước ngày kết thúc cửa sổ, với giới hạn khoảng trống dữ liệu. Không có quan sát không được đổi thành giá trị 0.
- Dữ liệu được chia theo thời gian thành phần huấn luyện và phần kiểm tra về sau. Xác suất chỉ dùng phần huấn luyện. Đầu ra công khai cỡ mẫu, Brier score, log loss, sai lệch tần suất và mức hạn chế; dữ liệu ít hoặc lớp hiếm cần được đọc cùng khoảng bất định.
- Đây là kiểm tra hồi cứu trên phiên bản chuỗi có ở lúc thu thập. Sửa đổi dữ liệu có thể làm kết quả khác với những gì biết được tại thời điểm lịch sử. Kiểm tra này không chứng minh đã hiệu chuẩn cho tương lai.

## Lưu dự báo và theo dõi kết quả thật

Máy chủ có sổ theo dõi riêng cho các dự báo nghiên cứu từ nguồn công khai. Dự báo được ghi trước ngày cuối kỳ; việc đối chiếu kết quả chỉ diễn ra khi kỳ đã kết thúc và có bản nguồn đủ dữ liệu. Bản dự báo, định nghĩa, nguồn và lần đối chiếu đầu tiên giữ nguyên dấu vết.

Không tự gán nhãn “đã hiệu chuẩn” từ một vài dự báo đã kết thúc. Thống kê theo dõi phải thể hiện số kỳ thực đã đối chiếu và phiên bản dữ liệu. Sổ không lưu email, phiên đăng nhập, danh mục đầu tư hay lệnh giao dịch.

## Trường hợp chưa thể tính

Lựa chọn **Vietnam → Conflict risk** không tự chuyển thành dự báo VIX của Hoa Kỳ. Hệ thống giữ câu hỏi đó và nêu rõ phần thiếu: một thước đo/kết quả xung đột có thể đối chiếu, quy tắc phân loại, nguồn bao phủ phù hợp và lịch sử đủ để đánh giá. Số tin, tên tòa soạn hoặc việc không thấy sự kiện trong một nguồn không xác định xác suất xung đột.

Mô hình catalog đã duyệt với dữ liệu do người vận hành chuẩn bị vẫn được hỗ trợ riêng theo [EVENT_PROBABILITIES.md](EVENT_PROBABILITIES.md). Các mô hình đó cũng phải giữ đúng bối cảnh, kỳ hạn và toàn bộ nhóm kết quả.

## Dữ liệu trên máy

Quan sát gốc và sổ theo dõi nằm trong kho riêng của Event Scenarios; mô hình đã chuẩn bị nằm dưới `backend/private-event-models/`. Chúng không được đưa vào Git hay ZIP mã nguồn. Máy người dùng sẽ thu thập dữ liệu từ nguồn thật khi yêu cầu tính toán. Lỗi tải nguồn không xóa bản đã lưu; mô hình hết hạn hoặc nguồn cũ được báo rõ, không âm thầm đóng vai kết quả mới.
