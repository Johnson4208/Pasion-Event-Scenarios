# PASION trên máy chủ HTTPS

Dùng một máy chủ có ổ đĩa lưu lâu dài, DNS tên miền trỏ tới máy chủ và Caddy 2. Đặt mã nguồn tại /srv/pasion. Chạy npm ci và npm run build ở thư mục đó. Cài các gói Python theo hướng dẫn khởi chạy của dự án.

Dừng backend cũ trước khi sao lưu SQLite. Chuyển bản sao nhất quán của backend/accounts.sqlite3 qua kênh riêng vào đúng vị trí trên máy chủ. Giữ bản sao dự phòng, quyền đọc/ghi cho tài khoản dịch vụ backend và chỉ cấp Caddy quyền đọc dist và deploy/access.html. Không đưa cơ sở dữ liệu vào Git hoặc thư mục web. Chuyển riêng các kho tài liệu và dữ liệu đã nhập nếu cần sử dụng trên máy chủ mới.

Đặt PASION_ENV=production, PASION_ADMIN_EMAIL bằng email chủ sở hữu đã có trong cơ sở dữ liệu, PASION_DOMAIN bằng tên miền thật (không có giao thức hay đường dẫn) trong môi trường dịch vụ backend. Khởi chạy python backend/server.py. Backend lắng nghe tại 127.0.0.1:8000. Nếu chưa có chủ sở hữu, dùng backend/setup_admin.py trên máy chủ với đúng biến môi trường. Công cụ này đặt lại mật khẩu nếu tài khoản đã tồn tại.

Đặt cùng PASION_DOMAIN trong môi trường Caddy, dùng deploy/Caddyfile làm cấu hình. Mở cổng HTTPS và cổng HTTP phục vụ xác thực tên miền/chuyển hướng. Chạy hai tiến trình dưới trình quản lý dịch vụ. Truy cập tên miền trong cửa sổ riêng tư để kiểm tra: khách thấy trang đăng nhập, truy cập trực tiếp /api/permissions trả 401, tài khoản mới chờ duyệt, chủ sở hữu mở Administration → Accounts → Approve access. Kiểm tra tài khoản cũ trước khi chuyển người dùng sang tên miền mới.

Các file trong dist, bao gồm tin tức tĩnh, được Caddy kiểm tra phiên trước khi trả về. Chỉ triển khai lên origin này. Một bản demo GitHub Pages đã xuất bản riêng phải được gỡ nếu muốn ngừng chia sẻ demo đó. Tài khoản demo bị chặn khi chạy production. Lab ở tên miền này chỉ dành cho chủ sở hữu, dữ liệu mô phỏng có vòng đời theo tiến trình backend.
