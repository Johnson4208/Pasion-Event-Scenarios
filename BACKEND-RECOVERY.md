# Giữ mã mới, khôi phục dữ liệu backend cũ

Mục tiêu là **một thư mục ứng dụng hoàn chỉnh**: mã nguồn mới nhất và bộ dữ liệu lấy từ **một bản cũ do bạn chọn**. Không cần chạy hai phiên bản song song. Không chép đè thư mục backend cũ lên mã mới.

Đối chiếu với mã gốc trong Git cho thấy bản Event Scenarios mới vẫn giữ các chức năng tài khoản, quản trị, tài liệu và kho dữ liệu. Chưa thể đối chiếu mã riêng của ba phiên bản trong ZIP lớn: công cụ chuyển tệp hiện giới hạn 32 MiB. Công cụ dưới đây phục hồi dữ liệu trên máy bạn; việc hợp nhất những thay đổi mã riêng của ba bản cần ZIP mã nguồn nhỏ hơn theo [RECOVERY-BUNDLE.md](RECOVERY-BUNDLE.md).

## Trên Windows

1. Giải nén bản mã nguồn mới vào một thư mục riêng. Giữ nguyên thư mục bản cũ có dữ liệu.
2. Dừng PASION ở các cửa sổ Terminal bằng `Ctrl+C`; dừng Event Agent nếu đã chạy riêng. Đóng cả hai phiên bản trong suốt quá trình khôi phục.
3. Trong **thư mục mã mới**, mở `RECOVER-BACKEND.cmd`. Chọn thư mục **bản cũ** có `package.json`, `backend` và `src`. Nếu ba bản đang trong ZIP, giải nén ra trước rồi chọn đúng một thư mục dự án bên trong.
4. Công cụ tạo thư mục `Pasion-recovered-YYYYMMDD-HHMMSS` cạnh thư mục mã mới. Khi thông báo thành công xuất hiện, dùng thư mục vừa tạo làm bản chính. Bản gốc không bị ghi đè.
5. Mở CMD trong thư mục vừa tạo, chạy **từng dòng**, chờ xong rồi mới chạy dòng tiếp:

```cmd
npm.cmd ci
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --timeout 120 --retries 10 --disable-pip-version-check -r backend/requirements-documents.txt
npm.cmd run dev
```

Mở **http://127.0.0.1:5173**. Các lần sau mở **RUN-PASION.cmd** hoặc chạy `npm.cmd run dev` trong cùng thư mục. Lệnh `dev:full` cũ vẫn hoạt động. Không dùng lại `.venv` hay `node_modules` chép từ bản cũ. Nếu cổng đang bận, dừng bản đã chạy; công cụ không tự chuyển sang địa chỉ khác.

Nếu không tìm thấy Python: cài bằng `winget install --exact --id Python.Python.3.12`, mở CMD mới và thử `py -3.12 --version`. Nếu cửa sổ chọn thư mục không hoạt động, dùng lệnh bên dưới.

## Dùng dòng lệnh

Ví dụ khi mã mới nằm ở `C:\Pasion-latest`, bản có dữ liệu ở `C:\Pasion-old`. Đổi đường dẫn cho đúng máy; dấu ngoặc kép giữ nguyên. Thư mục đầu ra phải **chưa tồn tại**, nằm ngoài cả hai dự án:

```cmd
cd /d C:\Pasion-latest
py -3.12 backend\recover_state.py inspect --source "C:\Pasion-old"
py -3.12 backend\recover_state.py assemble --state-source "C:\Pasion-old" --output "C:\Pasion-complete" --stopped
```

`inspect` chỉ in tên kho dữ liệu, bảng/cột, số bản ghi và kết quả kiểm tra. Nó không in email, mật khẩu, băm mật khẩu hay nội dung tài liệu. `--stopped` xác nhận bạn đã dừng hai bản và Event Agent; tùy chọn này không tự tắt tiến trình.

## Được giữ và giới hạn

| Dữ liệu | Cách xử lý |
| --- | --- |
| Tài khoản, mật khẩu đã băm, quyền quản trị, dữ liệu gắn với tài khoản | Giữ toàn bộ `backend/accounts.sqlite3`; không đặt lại mật khẩu |
| Tài liệu, nội dung đã trích xuất, tệp gốc đã lưu | Giữ `backend/documents.sqlite3`; không thể dựng lại tệp gốc nếu bản cũ chưa lưu |
| Tài chính, macro, mô hình cổ phiếu, dữ liệu kỹ thuật | Giữ toàn bộ các SQLite chuẩn, cùng một phiên bản nguồn |
| Event Agent và dữ liệu lịch sử phục vụ xác suất | Giữ kho SQLite chuẩn nếu có; dữ liệu vẫn giữ trạng thái kiểm duyệt/thời hạn cũ |
| Phiên đăng nhập, mã đặt lại mật khẩu đang chờ, khóa tạm của Event Agent | Không giữ phiên; xóa mã đặt lại và khóa tạm trong **bản sao** |
| Cấu hình email, biến môi trường, khóa API, JSON mô hình riêng | Không tự chuyển; cấu hình lại trên máy. Không gửi các tệp này lên GitHub |
| Báo cáo Event đã lưu, watchlist và tùy chọn trong trình duyệt | Không nằm trong backend. Giữ cùng trình duyệt, hồ sơ và địa chỉ `http://127.0.0.1:5173` |

Mật khẩu cũ phụ thuộc cơ sở dữ liệu tài khoản đã chọn. Bạn cần đăng nhập lại sau khi khởi động backend; đăng xuất phiên không đổi mật khẩu. Công cụ không chạy `setup_admin.py`. Biến `PASION_ADMIN_EMAIL` có thể ảnh hưởng quyền chủ sở hữu độc lập với quyền lưu trong SQLite; cấu hình cũ không được tự nhập.

Các kho được nhận diện: `backend/accounts.sqlite3`, `documents.sqlite3`, `finance.sqlite3`, `macro.sqlite3`, `stock_models.sqlite3`, `technical.sqlite3`, `event-agent-state/intelligence.sqlite3` và `backend/private-event-models/outcomes.sqlite3`. Đường dẫn tùy chỉnh ngoài dự án không tự được tìm hoặc chuyển. JSON mô hình riêng chỉ dùng lại sau khi đối chiếu với định dạng và yêu cầu kiểm định trong [EVENT_PROBABILITIES.md](EVENT_PROBABILITIES.md).

Công cụ tạo bản sao tạm của SQLite và WAL rồi dùng SQLite Backup API, nên các giao dịch đã commit trong WAL được giữ. Nó không mở SQLite trên tệp gốc, không nối bảng từ nhiều bản, và không bỏ qua lỗi dữ liệu. Nó kiểm tra tính toàn vẹn, khóa ngoại, liên kết tài liệu được biết, lược đồ tối thiểu và định dạng băm hiện hành; không thể chứng minh mọi quy tắc nghiệp vụ của một bản cũ chưa được đối chiếu. Các tệp phải đứng yên trong suốt quá trình: kiểm tra từng SQLite không thay thế việc dừng dịch vụ để có một bộ dữ liệu nhất quán.

Đầu ra không ghi đè thư mục có sẵn. Công cụ đối chiếu mã nguồn và dữ liệu ở đầu/cuối quá trình, đồng thời kiểm tra bản sao SQLite/WAL trước khi mở chúng. Khi có lỗi thông thường, thư mục đầu ra mới được dọn; bản gốc còn nguyên. Nếu mất điện hoặc tiến trình bị kết thúc giữa lúc hoàn tất, thư mục có thể còn `RECOVERY-INCOMPLETE.txt`: **không chạy thư mục đó**, chọn tên đầu ra mới rồi làm lại. Thư mục nguồn có dấu này cũng bị từ chối; `npm run dev` và `RUN-PASION.cmd` chặn khởi động bản dở dang. Nếu lỗi quyền truy cập ngăn việc dọn hoặc đánh dấu, thông báo lỗi chỉ rõ đầu ra không dùng được. Giữ bản gốc đến khi kiểm tra được đăng nhập, quyền quản trị, tài liệu và dữ liệu tài chính trên bản mới.

`recovery-manifest.json` ghi các kho đã chuyển và kết quả kiểm tra, không chứa dữ liệu từng bản ghi. **Toàn bộ thư mục khôi phục có dữ liệu riêng tư: không nén gửi lại và không đẩy lên Git.** Nếu cần gửi mã để đối chiếu, dùng `PREPARE-RECOVERY.cmd` để tạo gói chỉ chứa mã nguồn.
