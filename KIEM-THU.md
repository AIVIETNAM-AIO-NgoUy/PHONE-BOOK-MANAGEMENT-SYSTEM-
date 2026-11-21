# Kết quả kiểm thử và rà soát

**Ngày:** 2026-11-21  
**Phạm vi:** mã nguồn Django trong repository `PHONE-BOOK-MANAGEMENT-SYSTEM--feature-admin-governance`.

## Phát hiện

### [Cao] Thiếu toàn bộ template HTML được các view yêu cầu

Repo không có file `*.html` (đã dò bằng `rg --files | rg "\.html$"`), nhưng ứng dụng gọi `render()` cho các đường dẫn như `accounts/register.html`, `admin_panel/dashboard.html`, `contacts/...` và cả `404.html`, `403.html`, `500.html`. Vì vậy các trang HTML không thể render và sẽ phát sinh `TemplateDoesNotExist`; trang lỗi tùy chỉnh cũng không có template để hiển thị. Đây ảnh hưởng đến đăng nhập/đăng ký và các màn hình nghiệp vụ, trừ khi template được cung cấp bên ngoài repo theo cấu hình deploy.

**Vị trí tham chiếu:** `backend/apps/accounts/views.py` (`RegisterView.template_name`), `backend/apps/admin_panel/views.py` (`AdminDashboardView.template_name`), `backend/apps/core/views.py` (error handlers); cấu hình tìm template nằm tại `backend/config/settings/base.py`.

**Khuyến nghị:** bổ sung template vào `frontend/templates` (đường dẫn được cấu hình trong settings) hoặc vào thư mục `templates` bên trong app phù hợp; xác nhận tất cả tên template được các view tham chiếu tồn tại.

## Kết quả kiểm tra đã chạy

- `python -m compileall -q backend`: **đạt** — không phát hiện lỗi cú pháp Python.
- `python -m pytest` trong `backend`: **không chạy được** — môi trường Python hiện tại báo `No module named pytest`.
- Không tìm thấy file test `test_*.py` / `*_test.py` hoặc thư mục `backend/tests` trong repository, dù pytest được cấu hình trỏ tới `tests`.
- Do thiếu pytest và dependency Django trong môi trường chưa được xác nhận, chưa chạy được kiểm tra Django, test tích hợp hoặc kiểm tra kết nối database. Kết quả compileall chỉ xác nhận cú pháp, không xác nhận ứng dụng khởi động hay các luồng nghiệp vụ hoạt động.
