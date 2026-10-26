# Chuẩn bị ZIP nhỏ để đối chiếu các phiên bản

Công cụ này tạo **một ZIP mã nguồn dưới 31 MiB** từ ZIP lớn của bạn. Nó giữ tên và đường dẫn của từng thư mục phiên bản để có thể đối chiếu cả ba bản. ZIP gốc không bị sửa, xóa hay giải nén ra máy.

Đây là bước chuẩn bị để kiểm tra mã nguồn trước khi gộp và phục hồi backend. Công cụ không tự chọn phiên bản thắng, gộp mã, đổi mật khẩu hay phục hồi tài khoản. Việc tạo công cụ cũng không có nghĩa là ZIP lớn của bạn đã được kiểm tra.

## Cách dùng trên Windows

1. Giữ ZIP gốc ở một thư mục dễ tìm. Không cần khôi phục thư mục cũ trước khi tạo ZIP đối chiếu nếu ZIP gốc đã chứa các bản cần giữ.
2. Mở thư mục có `PREPARE-RECOVERY.cmd` và thư mục `scripts` đi kèm. Cả hai phải nằm cạnh nhau như trong bộ mã nguồn.
3. Nhấp đúp **PREPARE-RECOVERY.cmd**. Chọn ZIP lớn chứa các phiên bản khi cửa sổ chọn file mở ra.
4. Chờ thông báo `Đã tạo:`. ZIP mới nằm cạnh ZIP gốc, tên kết thúc bằng `-recovery-source-NGAY-GIO.zip`.
5. Gửi **ZIP mới** để đối chiếu. Giữ ZIP gốc trên máy: dữ liệu tài khoản và cấu hình riêng cần được phục hồi từ bản gốc sau này.

Chỉ cần Python 3.12; không cần chạy `npm install`, cài thư viện Python, bật quyền quản trị hay cấp quyền chạy script PowerShell. Nếu cửa sổ đóng hoặc báo không tìm thấy Python, mở Command Prompt và kiểm tra `py -3.12 --version`.

Nếu muốn gõ lệnh, mở Command Prompt tại thư mục mã nguồn và chạy từng dòng:

```cmd
py -3.12 -X utf8 scripts\prepare_recovery_bundle.py --input "C:\Users\ASUS-PC\Downloads\cac-phien-ban.zip"
```

Có thể chỉ định tên đầu ra mới:

```cmd
py -3.12 -X utf8 scripts\prepare_recovery_bundle.py --input "D:\Pasion\cac-phien-ban.zip" --output "D:\Pasion\pasion-ma-nguon.zip"
```

Không dùng tên ZIP đã tồn tại. Nếu chạy lại trong cùng giây, đợi một giây hoặc đặt `--output` khác.

## ZIP mới chứa gì?

- Mã nguồn và tài liệu ở nguyên đường dẫn của từng phiên bản; không bị nhập chung vào một thư mục hay ghi đè lẫn nhau. Các mẫu cấu hình như `.env.example` được giữ nếu không chứa trường bí mật có giá trị thật mà công cụ nhận diện được.
- `RECOVERY-MANIFEST.json`: danh sách file nguồn và SHA-256 để đối chiếu; danh sách **đường dẫn tương đối, kích thước và lý do loại bỏ** của các file dữ liệu/cấu hình riêng. Không ghi nội dung database, giá trị mật khẩu, hash mật khẩu hoặc khóa của những file riêng đó.

Công cụ bỏ thư viện cài lại được (`.venv`, `node_modules`), `.git`, `dist`, cache, kết quả test, file thực thi và các file nhị phân/ảnh/font. Nó không mở database, kể cả các file SQLite `-wal`, `-shm`, `-journal` và bản sao có đuôi `.bak`. Các thư mục `event-agent-state`, `private-event-models`, `.env`, cấu hình email, thông tin đăng nhập và khóa riêng chỉ được đưa vào danh mục metadata khi nằm ngoài thư mục thư viện/cache đã loại bỏ.

ZIP mới phục vụ **đối chiếu mã nguồn**, không phải bản sao lưu đầy đủ để chạy ứng dụng. Ảnh, font và dữ liệu riêng vẫn ở ZIP gốc. Đường dẫn trong manifest cũng có thể chứa tên do bạn đặt; hãy kiểm tra trước khi gửi. Bộ lọc nhận diện tên file và một số trường cấu hình thông dụng; nó không thể đảm bảo phát hiện mọi bí mật viết thẳng trong mã nguồn. Không gửi mã có khóa riêng được viết trực tiếp trong đó.

## Khi có thông báo lỗi

- **Vượt 31 MiB:** đầu ra dở dang được xóa; ZIP gốc giữ nguyên. Chuẩn bị ZIP riêng cho từng thư mục phiên bản rồi chạy công cụ cho từng ZIP. Không xóa các bản gốc để giảm kích thước.
- **Phát hiện tệp nén con:** công cụ dừng trước khi tạo đầu ra nếu có ZIP, 7z, RAR, TAR hoặc các biến thể TAR nén nằm ngoài thư mục thư viện/cache, file sinh tự động và thư mục dữ liệu riêng đã loại bỏ. Điều này cũng áp dụng khi ZIP ngoài có README hoặc một phiên bản đã giải nén, vì các phiên bản còn nằm trong file nén con sẽ bị thiếu. Thông báo liệt kê tối đa 5 đường dẫn và số file còn lại. Giải nén từng file nén con vào một thư mục riêng, giữ tên phân biệt của cả ba bản, rồi nén chung những thư mục đó và chạy lại. Công cụ không tự mở nhiều tầng file nén; ZIP gốc giữ nguyên.
- **Đường dẫn trùng nhau/không an toàn, liên kết hoặc file lỗi:** tạo lại ZIP từ các thư mục nguồn. Tên chứa ký tự Windows không cho phép như `<`, `>`, `:`, `"`, `|`, `?`, `*` cũng bị từ chối trước khi tạo đầu ra. Công cụ không ghi đè hay cố giải nén những đường dẫn đó.
- **Không có cửa sổ chọn file:** dùng lệnh có `--input` ở trên. Python thiếu Tkinter vẫn dùng được cách gõ lệnh.
- **Không tìm thấy thư mục đầu ra:** tạo thư mục đó trước hoặc bỏ `--output` để tạo ZIP cạnh bản gốc.

Công cụ chỉ đọc file ZIP đã chọn và tạo file ZIP mới; không chạy chương trình hoặc chỉ dẫn nằm trong ZIP, không gọi mạng và không thay đổi mã nguồn của các phiên bản.
