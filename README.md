# Phone Book Management System

Hệ thống Quản lý Danh bạ Điện thoại (Phone Book Management System) được tổ chức theo mô hình **Monorepo chuyên nghiệp** với sự phân tách tường minh giữa tầng giao diện (`frontend/`) và tầng xử lý nghiệp vụ (`backend/`).

---

## 📁 Cấu Trúc Dự Án (Repository Structure)

```text
PhoneBookManagementSystem/
├── backend/                  # Toàn bộ mã nguồn và logic backend (Django 5.1)
│   ├── apps/                 # Các domain applications
│   │   ├── accounts/         # Quản lý người dùng, xác thực, phân quyền
│   │   ├── admin_panel/      # Bảng điều khiển quản trị hệ thống
│   │   ├── contacts/         # Nghiệp vụ danh bạ, tìm kiếm, gộp trùng lặp
│   │   ├── core/             # Core models, middleware, security decorators
│   │   ├── favorites/        # Danh sách liên hệ yêu thích
│   │   └── groups/           # Nhóm liên hệ và phân loại
│   ├── config/               # Cấu hình dự án Django (settings, urls, wsgi, asgi)
│   ├── tests/                # Bộ kiểm thử tự động toàn diện (unit, contract, security, integration)
│   ├── manage.py             # Django management CLI
│   ├── pyproject.toml        # Cấu hình kiểm thử độc lập cho backend
│   └── requirements.txt      # Danh sách dependencies của Python
│
├── frontend/                 # Toàn bộ tầng giao diện (Presentation Layer)
│   ├── static/               # Static assets (Zero-dependency, Vanilla CSS & JS)
│   │   ├── css/              # Stylesheet và Custom CSS Variable Design System
│   │   ├── js/               # Client-side scripts
│   │   └── vendor/           # Thư viện bên ngoài (HTMX)
│   └── templates/            # Django HTML Templates & HTMX Partial Components
│
├── deploy/                   # Cấu hình triển khai hạ tầng
│   ├── docker-entrypoint.sh  # Script khởi động web container
│   └── nginx/                # Cấu hình Nginx reverse proxy
│
├── backups/                  # Tệp sao lưu cơ sở dữ liệu
│   └── phonebook_db.sql      # Tệp SQL dump chuẩn (DDL 18 bảng + dữ liệu mẫu hoàn chỉnh)
│
├── scripts/                  # Tiện ích quản trị hệ thống
│   ├── backup_restore.sh     # Sao lưu & phục hồi cơ sở dữ liệu (.sql & .dump)
│   └── security_audit.sh     # Kiểm tra an ninh trước khi triển khai production
│
├── docker-compose.yml        # Docker compose điều phối Web và PostgreSQL
├── Dockerfile                # Multi-layer Docker image build spec
├── Makefile                  # Bộ phím tắt quản lý tác vụ phát triển tiêu chuẩn
├── pyproject.toml            # Cấu hình pytest, black, isort ở cấp repository
└── .flake8                   # Quy chuẩn linting mã nguồn
```

---

## 🚀 Hướng Dẫn Phát Triển Nhanh (Quick Start)

Dự án cung cấp sẵn tệp `Makefile` tại thư mục gốc để thao tác thuận tiện:

### 1. Khởi động môi trường phát triển cục bộ
```bash
# Chạy Django Development Server (mặc định tại http://localhost:8000)
make dev
```

### 2. Kiểm thử tự động (Test Suite)
Dự án đi kèm 249 bài test tự động bao phủ hợp đồng API, bảo mật, tích hợp và unit test:
```bash
# Chạy toàn bộ test suite từ thư mục gốc
make test

# Chạy test kèm báo cáo độ bao phủ mã nguồn (Coverage Report)
make test-cov

# Hoặc nếu bạn đang đứng tại thư mục backend/:
cd backend && pytest
```

### 3. Kiểm tra chất lượng và định dạng mã nguồn (Lint & Format)
```bash
# Kiểm tra định dạng với flake8, black và isort
make lint

# Tự động format mã nguồn theo quy chuẩn
make format
```

### 4. Cơ sở dữ liệu và dữ liệu mẫu
```bash
# Thực thi migrations
make migrate

# Nạp dữ liệu mẫu ban đầu (demo accounts)
make seed
```

### 5. Sao lưu và phục hồi cơ sở dữ liệu (Database Backup & Restore)
Dự án cung cấp tệp dump cơ sở dữ liệu hoàn chỉnh [backups/phonebook_db.sql](file:///Users/vuthang/Documents/PhoneBookManagementSystem/backups/phonebook_db.sql) bao gồm toàn bộ DDL (18 bảng), constraints, sequences và dữ liệu mẫu (demo accounts, 10,000+ contacts).

Tệp được xuất với các tùy chọn `--clean --if-exists --no-owner --no-privileges`, hoàn toàn portable và tương thích để import vào PostgreSQL thông qua DBeaver, pgAdmin hoặc dòng lệnh psql mà không gặp lỗi quyền hạn (permissions/owner).

Thao tác nhanh bằng `Makefile`:
```bash
# Xuất database hiện tại ra tệp backups/phonebook_db.sql
make db-dump

# Nạp dữ liệu từ tệp backups/phonebook_db.sql vào database hiện tại
make db-restore
```

Hoặc sử dụng trực tiếp script quản trị [scripts/backup_restore.sh](file:///Users/vuthang/Documents/PhoneBookManagementSystem/scripts/backup_restore.sh):
```bash
# Xuất database ra tệp SQL
./scripts/backup_restore.sh --dump backups/phonebook_db.sql

# Khôi phục dữ liệu từ tệp SQL
./scripts/backup_restore.sh --restore backups/phonebook_db.sql

# Kiểm tra tính toàn vẹn của tệp sao lưu trên database scratch tạm thời
./scripts/backup_restore.sh --verify-only backups/phonebook_db.sql
```

---

## 🐳 Triển Khai Với Docker

Khởi chạy toàn bộ hệ thống gồm PostgreSQL, Gunicorn Web App và Nginx:

```bash
# Khởi động dịch vụ trong nền
make docker-up

# Dừng và dọn dẹp các container
make docker-down
```
Sau khi khởi chạy, hệ thống sẵn sàng hoạt động tại cổng `8088` (hoặc cấu hình tùy chỉnh qua tệp `.env`).
