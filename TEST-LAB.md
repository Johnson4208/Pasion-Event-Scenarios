# PASION test lab / Môi trường kiểm thử

## Trang Distribution Lab dành cho admin

1. Cập nhật nhánh `master`, mở `RUN-PASION.cmd` hoặc chạy `npm run dev` để khởi động cả frontend và backend.
2. Đăng nhập bằng tài khoản admin. Mở **Administration → Trading & Distribution Monitor → Distribution Lab** tại [trang quản trị local](http://127.0.0.1:5173/#admin).
3. Chọn 365 ngày, 730 ngày, ngẫu nhiên hoặc nhập số ngày trong khoảng 1–730. Chọn ngày bắt đầu, số khách và seed. Bấm **Tạo lượt mô phỏng**, sau đó **Chạy mô phỏng** hoặc **Tiến 1 ngày**.
4. Trong lúc chạy, bấm **Thêm khách** hoặc **Chỉnh giới hạn và tốc độ → Áp dụng thông số**. Thay đổi có hiệu lực ở đầu ngày kế tiếp. Nhật ký điều chỉnh ghi ngày và các giá trị đã áp dụng.
5. Dùng **Tạm dừng** để xem kỹ biểu đồ và các quyết định gần nhất. Nút **Xuất kết quả JSON** tải cấu hình, lịch sử điều chỉnh, tổng hợp theo ngày, số lần chọn từng mã và 20 quyết định mới nhất.

**HOSE · phát lại 2024–2025** là chế độ mặc định. Mỗi mã FPT, HPG, MWG, PNJ và VCB có 748 phiên OHLCV từ 03/01/2023 đến 31/12/2025. Các CSV trong `backend/distribution/replay_data` lưu giá theo VND/cổ phiếu (giá biểu đồ × 1.000) và khối lượng theo cổ phiếu. Chuỗi năm 2023 khởi tạo chỉ báo. Bộ dữ liệu là ảnh chụp lịch sử biểu đồ của nhà cung cấp, có thể bao gồm điều chỉnh hồi tố. Lab phát lại được khi máy ngoại tuyến. [Nguồn DNSE / Entrade, ví dụ FPT](https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?symbol=FPT&resolution=1D&from=1672531200&to=1767225599)

Trước giờ mở cửa của từng phiên, lab dùng dữ liệu đến hết phiên trước để tính RSI14, SMA20, ATR14, RVOL20 và sự kiện VSA qua module Indicators & VSA. Hàm tạo đặc trưng của Stock Analytics cung cấp động lượng 5 phiên, độ lệch so với SMA20 và độ biến động. Ba hồ sơ khách (thận trọng, cân bằng, động lượng) dùng ngưỡng biến động và trọng số riêng. Distribution xếp các ứng viên phù hợp theo điểm thí nghiệm rồi áp dụng giới hạn mã, ngành và thời gian tránh lặp.

Khách ưu tiên giảm vị thế có giá đóng cửa dưới SMA20. Khi mua, mã đã qua Distribution phải có giá đóng cửa từ SMA20 trở lên. Trade Planner tính số lượng dựa trên tiền mặt, vị thế, mức rủi ro và khoảng dừng bằng hai lần ATR. Lệnh đủ điều kiện ghi vào sổ độc lập ở giá mở cửa của phiên tiếp theo. Mô hình giả định vốn mặc định 100 triệu VND/khách, lô 100 cổ phiếu, phí 0,1%, thanh toán tức thì, thuế và trượt giá bằng 0. Khả năng khớp thực tế, độ sâu sổ lệnh và chi trả cổ tức nằm ngoài mô hình. Dòng **giá trị giao dịch** cộng giá trị tuyệt đối mua và bán trước phí.

Trên cùng màn hình có tổng lượt mua và bán, khối lượng từng mã, 10 khách có giá trị giao dịch cao nhất, 20 giao dịch mới nhất và tín hiệu của phiên trước. JSON xuất ra chứa các bảng này và tổng hợp từng ngày. Nút **Sổ tài khoản & Shadow** mở dữ liệu nhập tay và theo dõi shadow hiện có.

Đồng hồ tiến theo ngày lịch. Ngày thiếu phiên giá có số yêu cầu và giao dịch bằng 0. Số yêu cầu trên mỗi phiên và khách gửi yêu cầu được lấy mẫu theo seed. Chọn **Kiểm thử hạn mức · mã SIM** để chạy kịch bản tổng hợp trên khoảng ngày tùy chọn. Khi thêm khách, những khách mới sẽ tham gia nhóm được lấy mẫu từ ngày kế tiếp. Cùng seed, cấu hình và ngày điều chỉnh sẽ tạo lại chuỗi quyết định.

Mỗi yêu cầu đi qua cùng hàm tính Distribution dùng trong bài thử đồng thời. KPI **Trong đó đổi mã** đếm các lượt đã gợi ý một mã khác với lựa chọn phù hợp có điểm cao nhất ban đầu. **Giữ lại** đếm yêu cầu hết ứng viên đủ điều kiện. Biểu đồ phân phối mã cộng dồn từ đầu lượt, còn hạn mức áp dụng theo cửa sổ trượt. Toàn bộ quyết định trong một ngày được ghi cùng giao dịch SQLite.

Mọi admin trên cùng backend dùng chung một lượt. Đóng tab hoặc tải lại trang vẫn giữ tiến trình khi backend còn chạy. Khi thay lượt hoặc dừng backend, kết quả trong lab hết hiệu lực. Hãy xuất JSON nếu cần lưu. Backend dùng SQLite tạm riêng cho các mã và khách giả lập. Đăng nhập và nhật ký truy cập vẫn dùng cơ chế quản trị của PASION. API chỉ chấp nhận admin qua localhost ở chế độ phát triển và tắt khi `PASION_ENV=production`.

Để kiểm tra lại, chạy `python -m unittest discover -s backend -p test_distribution_lab.py`. Sau `npm ci` và `npx playwright install chromium`, chạy `node testing/admin_lab_ui.mjs` để kiểm tra luồng trình duyệt một và hai năm trên hai cổng tạm. Job **admin-lab-ui** trên GitHub Actions cũng chạy các bước này.

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
