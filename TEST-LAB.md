# PASION test lab / Môi trường kiểm thử

## Chạy phân bổ với khách hàng giả lập

Không cần tài khoản hoặc khách hàng thật:

```powershell
.venv\Scripts\python.exe testing\simulate_distribution.py --customers 1000 --workers 16
```

Mac/Linux: `python3 testing/simulate_distribution.py`.
Kết quả: `artifacts/distribution-lab.json`. Mỗi lần chạy tạo SQLite tạm riêng rồi xóa. Sáu mã SIM_* và điểm số là dữ liệu giả lập. So sánh với baseline luôn chọn mã điểm cao nhất. Hạn mức minh họa: 100 lượt/mã/giờ, 300 lượt/ngành/giờ, thời gian tránh lặp cho cùng khách hàng 600 giây, chỉ thay bằng ứng viên chênh tối đa 2 điểm utility. Đây là tham số test, chưa được hiệu chỉnh bằng dữ liệu sử dụng thật.

## Thuật toán đã có trong lab

`backend/distribution/recommendations.py` lọc ứng viên phù hợp, dữ liệu READY và cùng định nghĩa/phiên bản utility, kỳ hạn. Sau đó chỉ giữ tập gần tương đương. Ưu tiên mã điểm cao nhất còn hạn mức và chưa lặp cho khách hàng; nếu hết lựa chọn thì trả `NO_SUITABLE_ALTERNATIVE`. Không ép chọn mã yếu hoặc mở rộng dung sai. Giới hạn mã/ngành được chia sẻ giữa mọi yêu cầu trong cùng SQLite, tính theo cửa sổ thời gian trượt; không reset khi đổi phiên bản chính sách. Giao dịch `BEGIN IMMEDIATE` ngăn vượt hạn mức khi chạy đồng thời; khóa yêu cầu chống tính trùng khi retry. Các giới hạn đo số gợi ý đã phát hành, không phải số lệnh, lượng vốn hay thanh khoản thị trường. Lượt phát hành không có cơ chế hoàn hạn mức.

Module này chưa nối vào luồng gợi ý cho người dùng thật. Trường `suitable` và utility trong lab là đầu vào giả lập. Trước khi nối vào production cần đầu vào được backend xác thực và cơ chế ghi nhận gợi ý ngay tại điểm phát hành chung cho mọi tính năng. Không được tin nhãn suitable do trình duyệt gửi. Cần bổ sung thời hạn dữ liệu/utility và kiểm tra thông tin danh mục từ server. Không dùng nhiều SQLite độc lập nếu muốn hạn mức chung giữa các máy chủ. SQLite trong bản này phù hợp kiểm thử một máy.

## Kiểm thử toàn dự án bằng một lệnh

1. Dùng bản Git đầy đủ từ GitHub Desktop. Cài Python, Node.js và Git.
2. Tạo môi trường Python nếu chưa có:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend/requirements-documents.txt
```

3. Dừng bản web dev đang chiếm cổng 5173 rồi mở `RUN-TEST-LAB.cmd`.

Hoặc chạy `.venv\Scripts\python.exe scripts\test_lab.py --ui`. Bỏ `--ui` để chỉ chạy backend, unit, build và giả lập. Lệnh sao chép file Git theo dõi sang thư mục tạm, loại cơ sở dữ liệu runtime, uploads, `.env` và biến cấu hình PASION/SOLVAI hiện tại; không sao chép tài khoản/danh mục máy bạn. Bản sao bị xóa sau khi chạy. Các bài test backend dùng fixture và database test của dự án. npm và trình duyệt cần mạng khi cài. Phần UI chạy toàn bộ các bài Playwright hiện có, nhiều bài dùng API mock; chưa tương đương kiểm thử mọi luồng với dịch vụ dữ liệu thật. Nguồn bên ngoài còn tùy kết nối. Báo cáo/log nằm trong `artifacts/test-lab/`; bài nào lỗi vẫn được ghi rõ, runner không chuyển lỗi thành pass.

Trên GitHub: Actions → Project test lab → Run workflow để chạy toàn bộ trong máy ảo mới. Push thay đổi module tự chạy suite phân bổ và full project; có thể chạy lại bằng Run workflow. Mỗi job dùng dữ liệu riêng. Đây là nền tảng kiểm thử toàn dự án hiện có, không khẳng định bao phủ mọi tính năng hay mô phỏng được phản ứng thị trường, lợi nhuận, rủi ro hoặc hành vi khách hàng thật.

## Kịch bản đã kiểm tra

- 1.000 khách hàng cùng chọn một mã tốt nhất; 16 luồng đồng thời.
- 50 yêu cầu đua nhau: không vượt giới hạn từng mã, không thay bằng mã kém xa.
- Giới hạn ngành áp dụng qua nhiều mã.
- Cùng khách hàng: tránh lặp lại mã trong thời gian chờ.
- Retry cùng mã yêu cầu: trả kết quả cũ, không cộng thêm lượt.
- Retry thay nội dung, utility NaN và utility không cùng kỳ: từ chối.
- Cửa sổ hết hạn: cho phép gợi ý lại.

Giả lập kiểm chứng tính đúng của cơ chế phân bổ. Hiệu chỉnh chất lượng cần chạy shadow với dữ liệu thật về sau, theo dõi mức tập trung, tỷ lệ không có lựa chọn, chất lượng phương án thay thế và sự phù hợp từng khách hàng.
