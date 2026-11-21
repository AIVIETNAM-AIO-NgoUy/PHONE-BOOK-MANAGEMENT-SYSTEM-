#set page(
  paper: "a4",
  margin: (x: 1.8cm, top: 2cm, bottom: 2cm),
  header: context {
    if here().page() > 1 {
      text(9pt, fill: rgb("#64748b"))[
        *Phone Book Management System* | Sổ tay vấn đáp thực chiến - *Hiếu (Lead Backend & DevOps)*
        #line(length: 100%, stroke: 0.5pt + rgb("#cbd5e1"))
      ]
    }
  },
  footer: context {
    text(9pt, fill: rgb("#64748b"))[
      #line(length: 100%, stroke: 0.5pt + rgb("#cbd5e1"))
      #grid(
        columns: (1fr, 1fr),
        [Tài liệu lưu hành nội bộ nhóm - Ôn tập bảo vệ đồ án],
        align(right)[Trang #here().page() / #counter(page).final().at(0)]
      )
    ]
  }
)

#set text(font: "Arial", size: 9.5pt, lang: "vi")
#set par(justify: true, leading: 0.65em)

#let callout(title: "", body, color: rgb("#1e3a8a")) = block(
  width: 100%,
  stroke: (left: 4pt + color),
  fill: rgb("#f8fafc"),
  inset: 9pt,
  radius: (right: 4pt),
  [
    #text(weight: "bold", fill: color, size: 10pt)[#title] \
    #v(3pt)
    #body
  ]
)

#let tip(title: "MẸO GHI ĐIỂM VỚI CÔ", body) = callout(title: title, body, color: rgb("#16a34a"))
#let trap(title: "CÔ HAY HỎI BẪY CHỖ NÀY", body) = callout(title: title, body, color: rgb("#dc2626"))

// Tiêu đề đầu trang
#align(center)[
  #text(16pt, weight: "bold", fill: rgb("#1e3a8a"))[SỔ TAY THỰC CHIẾN BẢO VỆ ĐỒ ÁN (POCKET REFERENCE)] \
  #v(2pt)
  #text(12pt, weight: "bold", fill: rgb("#0284c7"))[DÀNH CHO: HIẾU (LEAD BACKEND & INFRASTRUCTURE)] \
  #v(2pt)
  #text(9pt, fill: rgb("#64748b"))[Đề tài: Phone Book Management System | Kiến trúc Clean Architecture, Trigram GIN Search & Docker]
]

#v(10pt)

= PHẦN 1: ĐỊNH VỊ VAI TRÒ & KỊCH BẢN MỞ ĐẦU 1 PHÚT

== 1.1. Phạm vi trách nhiệm chính (Làm chủ 7 PRs trên Git)
- *PR \#1 (`feature/accounts-models`)*: Custom User model, Argon2id hashing, schema auth migrations.
- *PR \#3 (`feature/accounts-views-auth`)*: Authentication services, forms, login/session backend.
- *PR \#5 (`feature/contacts-models`)*: Core Contact & PhoneNumber models, 1-N relations, normalization.
- *PR \#7 (`feature/contacts-service`)*: Service layer xử lý nghiệp vụ danh bạ, CRUD, bulk operations.
- *PR \#9 (`feature/contacts-search-dedup`)*: Thuật toán Trigram GIN search & engine phát hiện trùng lặp.
- *PR \#11 (`feature/contacts-merge-service`)*: Thuật toán gộp thông minh (Smart Merge) & xử lý xung đột.
- *PR \#13 (`feature/database-backup-restore`)*: Kịch bản backup/restore tự động PostgreSQL, Docker & seed data.

== 1.2. Kịch bản mở đầu 60 giây (Nói tự tin, dứt khoát)
#tip(title: "KỊCH BẢN PHÁT BIỂU 60S ĐẦU TIÊN KHI BƯỚC VÀO BÁO CÁO")[
  "Dạ em chào cô. Trong đồ án Phone Book Management System, em phụ trách toàn bộ *Kiến trúc Backend Core, Cơ sở dữ liệu và Hạ tầng DevOps*. Mục tiêu cốt lõi của em là giải quyết 3 bài toán kỹ thuật lớn:
  1. *Hiệu năng tìm kiếm mờ cực đại*: Sử dụng PostgreSQL Trigram GIN Indexing, cho phép gõ sai dấu, sai chính tả vẫn tìm ra liên hệ với độ trễ dưới 15ms.
  2. *Toàn vẹn dữ liệu và Chống trùng lặp*: Xây dựng thuật toán Smart Deduplication quét trùng và Smart Merge xử lý gộp an toàn trong `transaction.atomic()`.
  3. *Bảo mật & Hạ tầng sẵn sàng*: Băm mật khẩu Argon2 chống GPU crack, phân quyền đa người dùng và đóng gói Docker container hóa chuẩn production."
]

---

= PHẦN 2: CHECKLIST DEMO THỰC CHIẾN 3 PHÚT

#table(
  columns: (0.8fr, 2fr, 3.2fr),
  fill: (col, row) => if row == 0 { rgb("#1e3a8a") } else if calc.even(row) { rgb("#f8fafc") } else { none },
  stroke: 0.5pt + rgb("#cbd5e1"),
  inset: 6pt,
  [#text(fill: white, weight: "bold")[Bước]],
  [#text(fill: white, weight: "bold")[Thao tác trên màn hình]],
  [#text(fill: white, weight: "bold")[Câu nói đắt giá thuyết minh với cô]],
  
  [1 (30s)],
  [Bật Docker terminal -> `docker compose ps` -> Mở trang web đăng nhập],
  [Dạ hệ thống được container hóa bằng Docker, chạy PostgreSQL 16 Alpine độc lập. Toàn bộ tài khoản được băm mật khẩu chuẩn Argon2id.],
  
  [2 (45s)],
  [Tạo mới liên hệ có *3 số điện thoại* (Mobile, Work, Home)],
  [Mô hình dữ liệu được chuẩn hóa 3NF tách bảng `PhoneNumber`, một liên hệ có thể có vô số số điện thoại và đánh dấu số chính `is_primary`.],
  
  [3 (45s)],
  [Gõ tìm kiếm từ khóa sai chính tả hoặc không dấu (vd: `nguyen` hoặc `thang`)],
  [Nhờ kích hoạt extension `pg_trgm` và GIN Index trên các trường họ tên, email, hệ thống tính toán `TrigramSimilarity` trả về kết quả mờ tức thì.],
  
  [4 (45s)],
  [Tạo 1 liên hệ mới trùng tên hoặc số điện thoại -> Xem cảnh báo Duplicate -> Bấm Merge Preview -> Merge],
  [Hệ thống tự động phát hiện trùng qua thuật toán so khớp đa tiêu chí. Khi gộp, toàn bộ số điện thoại và tag được bảo lưu trong một Transaction nguyên tử.],
  
  [5 (15s)],
  [Mở terminal chạy `./scripts/backup_restore.sh backup`],
  [Toàn bộ CSDL được sao lưu nén tự động kèm mã kiểm tra tính toàn vẹn md5, phục hồi chỉ trong một lệnh.]
)

---

= PHẦN 3: CHEAT SHEET MÃ NGUỒN CẦN MỞ SẴN TRÊN VS CODE

#table(
  columns: (2.2fr, 2fr, 3.8fr),
  fill: (col, row) => if row == 0 { rgb("#1e3a8a") } else if calc.even(row) { rgb("#f8fafc") } else { none },
  stroke: 0.5pt + rgb("#cbd5e1"),
  inset: 6pt,
  [#text(fill: white, weight: "bold")[Đường dẫn File]],
  [#text(fill: white, weight: "bold")[Class / Hàm Lõi]],
  [#text(fill: white, weight: "bold")[Điểm kỹ thuật cần chỉ vào khi cô hỏi]],
  
  [`backend/apps/accounts/models.py`],
  [`CustomUser`, `UserManager`],
  [Kế thừa `AbstractBaseUser`, đăng nhập bằng `email` thay vì username, chuẩn hóa email.],
  
  [`backend/apps/contacts/models.py`],
  [`Contact`, `PhoneNumber`],
  [Quan hệ `ForeignKey` với `on_delete=CASCADE`, trường `is_primary`, chỉ mục Indexing.],
  
  [`backend/apps/contacts/services.py`],
  [`search_contacts()`],
  [Dùng `TrigramSimilarity`, gán ngưỡng `similarity__gte=0.3` kết hợp `Q(icontains).`],
  
  [`backend/apps/contacts/services.py`],
  [`detect_duplicates()`, `merge_contacts()`],
  [Bọc trong `@transaction.atomic`, chuyển đổi các foreign key từ secondary sang primary.],
  
  [`.../migrations/0003_add_trigram_gin_indexes.py`],
  [`TrigramExtension`, `GinIndex`],
  [Tạo extension `pg_trgm` và GIN index tăng tốc tìm kiếm từ $O(N)$ về $O(log N)$.],
  
  [`scripts/backup_restore.sh`],
  [`backup_database()`, `restore_database()`],
  [Lệnh `pg_dump`, nén `gzip`, kiểm tra quyền và kết nối Docker an toàn.]
)

---

= PHẦN 4: 50 CÂU HỎI VẤN ĐÁP & ĐÁP ÁN ĐẮT GIÁ CHO HIẾU

== A. Cơ sở dữ liệu & Data Modeling (Câu 1 - 10)

*Câu 1: Tại sao em tách bảng `PhoneNumber` riêng thay vì lưu thẳng cột `phone_number` trong bảng `Contact`?*
- *Đáp án*: Tuân thủ chuẩn hóa 3NF (Third Normal Form). Trong thực tế, một người có nhiều số điện thoại (Mobile, Work, Home). Nếu để chung cột sẽ vi phạm tính nguyên tử hoặc phải tạo nhiều cột `phone_1`, `phone_2` gây lãng phí và giới hạn mở rộng. Tách bảng giúp liên kết 1-N linh hoạt và dễ gán cờ `is_primary`.

*Câu 2: Tại sao dự án chọn PostgreSQL mà không dùng MySQL hay SQLite?*
- *Đáp án*: PostgreSQL hỗ trợ vượt trội về: (1) Extension `pg_trgm` và GIN Indexing chuyên biệt cho tìm kiếm mờ; (2) Cơ chế Transaction MVCC xử lý đồng thời cực tốt; (3) Độ tin cậy và tuân thủ chuẩn ACID nghiêm ngặt hơn MySQL.

*Câu 3: Thuật toán Trigram trong PostgreSQL hoạt động thế nào?*
- *Đáp án*: Trigram băm chuỗi ký tự thành các bộ 3 ký tự liên tiếp (ví dụ: "thang" -> ["  t", " th", "tha", "han", "ang", "ng "]). Khi tìm kiếm, nó so sánh tỷ lệ trigram trùng khớp giữa từ khóa và dữ liệu qua độ đo tương đồng Dice/Jaccard Coefficient để chấm điểm từ 0.0 đến 1.0.

*Câu 4: Sự khác biệt cơ bản giữa B-Tree Index và GIN Index là gì?*
- *Đáp án*: 
  - *B-Tree*: Phù hợp tìm kiếm chính xác (`=`) hoặc tìm kiếm tiền tố (`prefix%`).
  - *GIN (Generalized Inverted Index)*: Phù hợp dữ liệu đa phần tử (mảng, full-text, trigrams). Nó lập chỉ mục từng bộ 3 ký tự trỏ về danh sách các row chứa nó, cho phép tìm kiếm chuỗi con ở bất kỳ vị trí nào (`%sub%`) với độ phức tạp $O(log N)$.

*Câu 5: Tại sao trong migration cần chạy lệnh kích hoạt `TrigramExtension()`?*
- *Đáp án*: Vì `pg_trgm` là module mở rộng (extension) không bật mặc định trong PostgreSQL core. Cần gọi `CREATE EXTENSION IF NOT EXISTS pg_trgm` trước để database hiểu được các toán tử và hàm trigram (`%`, `<->`, `similarity()`).

*Câu 6: Em xử lý thế nào khi một Contact bị xóa để không sinh ra dữ liệu mồ côi (orphaned data)?*
- *Đáp án*: Khai báo `on_delete=models.CASCADE` ở khóa ngoại của `PhoneNumber` trỏ tới `Contact`. Khi Contact bị xóa, toàn bộ số điện thoại liên thuộc tự động bị dọn dẹp sạch sẽ ở mức CSDL.

*Câu 7: Làm sao đảm bảo một Contact chỉ có duy nhất một số điện thoại là `is_primary`?*
- *Đáp án*: Xử lý trong Service Layer: Trước khi đặt một số thành `is_primary=True`, câu lệnh ORM sẽ cập nhật tất cả số khác của contact đó thành `is_primary=False`. Ngoài ra có thể bổ sung Partial Unique Constraint trong Django (`UniqueConstraint(fields=['contact'], condition=Q(is_primary=True))`).

*Câu 8: Khóa ngoại `user` trong bảng `Contact` đóng vai trò gì trong bảo mật?*
- *Đáp án*: Bảo đảm phân lập dữ liệu đa người dùng (Multi-tenant Data Isolation). Bất kỳ truy vấn danh bạ nào đều bắt buộc lọc qua `Contact.objects.filter(user=request.user)`. Điều này ngăn chặn triệt để lỗ hổng IDOR.

*Câu 9: Hệ thống của em dùng Soft Delete (xóa mềm) hay Hard Delete (xóa cứng)? Vì sao?*
- *Đáp án*: Dự án dùng Hard Delete kết hợp với Modal xác nhận 2 lớp và Audit Log. Lý do: Giữ CSDL gọn gàng, tuân thủ quyền riêng tư dữ liệu (Right to be Forgotten của GDPR). Toàn bộ hành vi xóa vẫn được lưu vết chi tiết trong bảng `AuditLog`.

*Câu 10: Cơ sở dữ liệu của dự án có tổng cộng bao nhiêu bảng? Kể tên các bảng chính?*
- *Đáp án*: Gồm 18 bảng (bao gồm bảng core hệ thống Django). Các bảng nghiệp vụ chính: `accounts_customuser`, `contacts_contact`, `contacts_phonenumber`, `groups_group`, `groups_groupmember`, `favorites_favoriteitem`, `admin_panel_auditlog`.

---

== B. Thuật toán, Xử lý Nghiệp vụ & Service Layer (Câu 11 - 20)

*Câu 11: Trình bày quy trình tìm kiếm trong hàm `search_contacts()`?*
- *Đáp án*: Gồm 4 bước: (1) Chuẩn hóa từ khóa tìm kiếm (strip khoảng trắng); (2) Nếu rỗng, trả về queryset mặc định sắp xếp theo ngày; (3) Nếu có từ khóa, dùng `TrigramSimilarity` trên `first_name`, `last_name`, `email`, `company` kết hợp `Q(icontains)`; (4) Lọc các bản ghi có similarity >= ngưỡng 0.3 và order_by `-similarity`.

*Câu 12: Cơ chế phát hiện liên hệ trùng lặp (Duplicate Detection) hoạt động theo những tiêu chí nào?*
- *Đáp án*: Quét theo 3 cấp độ:
  1. *Trùng số điện thoại*: Số điện thoại sau khi chuẩn hóa giống nhau 100%.
  2. *Trùng email*: Địa chỉ email trùng khớp.
  3. *Trùng tên tương đối*: Điểm tương đồng `TrigramSimilarity` giữa họ tên lớn hơn ngưỡng 0.85.

*Câu 13: Khi thực hiện Gộp danh bạ (Merge Contacts), thuật toán xử lý dữ liệu thế nào?*
- *Đáp án*: 
  - Chọn 1 bản ghi làm *Primary* (giữ lại), 1 bản ghi làm *Secondary* (sẽ xóa).
  - Chuyển toàn bộ `PhoneNumber` của Secondary sang Primary (loại bỏ số trùng lặp).
  - Gộp các liên kết `Group` và trạng thái `Favorite`.
  - Nối ghi chú (notes) nếu có, giữ lại `created_at` cũ nhất.
  - Xóa Secondary an toàn và ghi một bản ghi vào `AuditLog`.

*Câu 14: Tại sao bắt buộc phải dùng `transaction.atomic()` khi thực hiện Merge?*
- *Đáp án*: Đảm bảo tính nguyên tử (Atomicity). Merge là chuỗi gồm nhiều thao tác: update số điện thoại, gộp nhóm, xóa bản ghi phụ. Nếu không có transaction, lỡ bước cuối bị crash CSDL sẽ rơi vào trạng thái rác nửa vời. `@transaction.atomic` đảm bảo hoặc thành công toàn bộ, hoặc rollback 100%.

*Câu 15: Tại sao em lại tách riêng `services.py` thay vì viết logic trong `views.py` hay `models.py`?*
- *Đáp án*: Áp dụng nguyên lý Separation of Concerns (SoC) và Clean Architecture. `views.py` chỉ làm nhiệm vụ nhận request và trả response (HTTP Transport layer). `services.py` chứa nghiệp vụ thuần túy (Domain logic), giúp code tái sử dụng được ở cả CLI, API, background job và dễ viết Unit Test độc lập.

*Câu 16: Chuẩn hóa số điện thoại được thực hiện thế nào trước khi lưu vào CSDL?*
- *Đáp án*: Dùng regex loại bỏ toàn bộ ký tự không phải số, khoảng trắng, dấu ngoặc. Giữ định dạng E.164 hoặc đầu số quốc dân `+84` để việc đánh index và so khớp trùng lặp chính xác tuyệt đối.

*Câu 17: Dữ liệu mẫu (Seed Data) được tạo ra bằng cách nào?*
- *Đáp án*: Em viết Custom Django Management Command: `python manage.py seed_contacts` và `seed_demo_accounts`. Sử dụng thư viện `Faker` để tạo ra dữ liệu người thật, số điện thoại chuẩn, avatar và ghi chú sinh động phục vụ test tải và demo.

*Câu 18: Khi phân trang ở Backend, em làm thế nào để không bị nghẽn bộ nhớ RAM?*
- *Đáp án*: Dùng Django `Paginator` trên `QuerySet`. Django QuerySet có tính chất *Lazy Evaluation*, câu lệnh SQL sinh ra có mệnh đề `LIMIT 20 OFFSET ...`. Dữ liệu chỉ được nạp đúng 20 dòng vào RAM của Python process thay vì load hàng triệu dòng.

*Câu 19: Độ phức tạp thuật toán tìm kiếm danh bạ trước và sau khi có GIN Index?*
- *Đáp án*: Trước khi có index: Phải quét toàn bộ bảng (Full Table Scan) với `LIKE %...%`, độ phức tạp là $O(N times M)$ (chậm khi danh bạ lớn). Sau khi có GIN Index: Tra cứu cây chỉ mục đảo, độ phức tạp giảm xuống xấp xỉ $O(log N)$.

*Câu 20: Khi hai danh bạ gộp nhau có cùng một số điện thoại thì xử lý thế nào?*
- *Đáp án*: Hệ thống kiểm tra số đó đã tồn tại trên Primary chưa. Nếu đã có thì bỏ qua (hoặc xóa số thừa bên secondary), nếu chưa có thì đổi khóa ngoại `contact_id` sang Primary, đảm bảo không bị lỗi trùng lặp khóa duy nhất.

---

== C. Bảo mật, Xác thực & Hệ thống (Câu 21 - 30)

*Câu 21: Tại sao em dùng thuật toán băm Argon2 thay vì PBKDF2 mặc định của Django?*
- *Đáp án*: Argon2 là thuật toán chiến thắng cuộc thi Password Hashing Competition (PHC). Nó là thuật toán *Memory-Hard*, tức là đòi hỏi cả CPU và dung lượng RAM lớn khi băm, ngăn chặn hiệu quả các cuộc tấn công bẻ khóa mật khẩu hàng loạt bằng card đồ họa GPU hoặc chip chuyên dụng ASIC.

*Câu 22: Em cấu hình Argon2 ở đâu trong source code?*
- *Đáp án*: Trong file `backend/config/settings/base.py`, em khai báo mảng `PASSWORD_HASHERS` và đặt `'django.contrib.auth.hashers.Argon2PasswordHasher'` ở vị trí đầu tiên.

*Câu 23: Làm thế nào hệ thống chống được tấn công Session Hijacking (cướp phiên)?*
- *Đáp án*: (1) Cờ `SESSION_COOKIE_HTTPONLY = True` (JavaScript không đọc được session ID, chống XSS); (2) `SESSION_COOKIE_SAMESITE = 'Lax'` (chống CSRF gửi chéo domain); (3) Sau khi đăng nhập, hệ thống tự động tái sinh Session ID (`session.cycle_key()`) để chống Session Fixation.

*Câu 24: Django bảo vệ API và Form chống CSRF như thế nào?*
- *Đáp án*: Thông qua `CsrfViewMiddleware`. Mọi form POST bắt buộc kèm `{% csrf_token %}` ẩn. Middleware sẽ so khớp token được mã hóa trong cookie và trong body request. Đối với HTMX, script client đính kèm token vào header `X-CSRFToken`.

*Câu 25: SQL Injection có thể xảy ra trong dự án này không? Vì sao?*
- *Đáp án*: Không thể xảy ra. Vì 100% các câu truy vấn đều sử dụng Django ORM. Django ORM sử dụng cơ chế Parameterized Queries (truy vấn tham số hóa), tách rời mã SQL và giá trị input của người dùng, CSDL coi input thuần túy là dữ liệu thô.

*Câu 26: Lỗ hổng IDOR (Insecure Direct Object Reference) là gì và em đã phòng chống ra sao?*
- *Đáp án*: IDOR là lỗi khi người dùng thay đổi ID trên URL (vd: `contacts/15/delete/`) để thao tác dữ liệu người khác. Em phòng chống bằng cách mọi truy vấn luôn kèm điều kiện quyền sở hữu: `get_object_or_404(Contact, id=pk, user=request.user)`. Nếu không đúng chủ sở hữu sẽ trả về 404/403 ngay lập tức.

*Câu 27: Script `scripts/security_audit.sh` thực hiện những bài kiểm tra nào?*
- *Đáp án*: Kiểm tra 5 tiêu chí trước khi lên production: (1) Biến `DEBUG=False`; (2) `SECRET_KEY` không bị hardcode mặc định; (3) Cờ `ALLOWED_HOSTS` được thiết lập chặt chẽ; (4) Quyền phân quyền file cấu hình nhạy cảm; (5) Kiểm tra SSL/TLS cookie flags.

*Câu 28: Thiết kế `CustomUser` bằng cách kế thừa `AbstractBaseUser` có lợi ích gì?*
- *Đáp án*: Cho phép loại bỏ trường `username` truyền thống và dùng `email` làm định danh duy nhất (phù hợp xu hướng hiện đại). Dễ dàng thêm các trường chuyên dụng như `avatar`, `phone_number`, `is_locked`, `failed_login_attempts` mà không phải dùng bảng OneToOne lỉnh kỉnh.

*Câu 29: Cơ chế khóa tài khoản (Account Lockout) hoạt động thế nào trong code?*
- *Đáp án*: Model `CustomUser` có cờ `is_active=False` hoặc `is_locked=True`. Khi đăng nhập, Authentication Backend kiểm tra cờ này, nếu tài khoản bị khóa sẽ từ chối cấp session và ném thông báo tài khoản bị vô hiệu hóa.

*Câu 30: Mật khẩu người dùng được lưu trữ như thế nào trong PostgreSQL?*
- *Đáp án*: Lưu trữ dưới dạng chuỗi hash một chiều có định dạng: `argon2$argon2id$v=19$m=102400,t=2,p=8$<salt>$<hash>`. Tuyệt đối không thể giải mã ngược lại thành mật khẩu gốc.

---

== D. Hạ tầng, Docker & DevOps (Câu 31 - 35)

*Câu 31: Giải thích kiến trúc các container trong `docker-compose.yml`?*
- *Đáp án*: Gồm 2 services:
  - `web`: Chạy Django ứng dụng qua WSGI server Gunicorn trên cổng 8000.
  - `db`: Chạy PostgreSQL 16 Alpine, sử dụng Docker Named Volume `postgres_data` để dữ liệu bền vững không bị mất khi stop container.
  Hai service giao tiếp nội bộ qua bridge network riêng an toàn.

*Câu 32: Cơ chế sao lưu và phục hồi dữ liệu trong `scripts/backup_restore.sh` hoạt động ra sao?*
- *Đáp án*:
  - *Backup*: Gọi `pg_dump` từ container PostgreSQL, nén bằng `gzip`, đặt tên file kèm timestamp `phonebook_backup_YYYYMMDD_HHMMSS.sql.gz` và tạo mã băm sha256 để kiểm tra toàn vẹn.
  - *Restore*: Giải nén, kiểm tra mã băm, dùng `psql` hoặc `pg_restore` để nạp lại vào database trong transaction an toàn.

*Câu 33: Tối ưu hóa Gunicorn cho Production được cấu hình như thế nào?*
- *Đáp án*: Trong `backend/config/gunicorn.conf.py`: Thiết lập số worker theo công thức chuẩn: `workers = (2 * CPU_CORES) + 1`, cấu hình `timeout = 60`, `keepalive = 2`, và log lỗi ra stdout/stderr để Docker thu thập.

*Câu 34: Biến môi trường được quản lý như thế nào để không bị lộ trên Git?*
- *Đáp án*: Tất cả thông tin nhạy cảm (`SECRET_KEY`, `DB_PASSWORD`) lưu trong file `.env`. File `.env` được khai báo trong `.gitignore`. Trong code dùng `python-decouple` để đọc biến môi trường. Repo chỉ commit file `.env.example` làm khung mẫu.

*Câu 35: File `backups/phonebook_db.sql` có dung lượng lớn phục vụ mục đích gì?*
- *Đáp án*: Đây là file SQL dump tiêu chuẩn chứa toàn bộ DDL (cấu trúc 18 bảng) và dữ liệu hạt giống đầy đủ. Giúp cô hoặc bất kỳ lập trình viên nào khi clone dự án về có thể import ngay vào database để test mà không cần mất công chạy seed lại từ đầu.

---

== E. Toàn diện Hệ thống & Phối hợp Nhóm (Câu 36 - 50)

*Câu 36: Tại sao nhóm chọn mô hình Monorepo thay vì tách riêng 2 repo Frontend và Backend?*
- *Đáp án*: Monorepo giúp: (1) Quản lý phiên bản mã nguồn đồng bộ tuyệt đối giữa giao diện và logic; (2) Dễ dàng thiết lập CI/CD và Docker Compose chung; (3) Tránh độ trễ đồng bộ API giữa 2 thành viên; (4) Giảm thiểu chi phí quản trị repository.

*Câu 37: Trình bày quy trình làm việc trên Git (Branching & PR Model) của nhóm?*
- *Đáp án*: Nhóm áp dụng GitHub Flow chuẩn hóa gồm 14 PRs. Từ commit gốc, mỗi tính năng được rẽ nhánh `feature/...`, commit theo chuẩn *Conventional Commits* (`feat:`, `test:`, `fix:`), sau đó tạo PR và merge vào nhánh chính bằng `--no-ff` ("Merge pull request \#X from ...").

*Câu 38: Cơ chế Cross-Review giữa Hiếu và Sinh diễn ra như thế nào?*
- *Đáp án*: Nhóm chia đều 7-7. Khi Hiếu làm author của các commit tính năng backend (PRs lẻ: \#1, \#3, \#5, \#7, \#9, \#11, \#13), Sinh sẽ review mã nguồn và là người thực hiện Merge commit vào `main`. Ngược lại, khi Sinh làm UI và Test (PRs chẵn: \#2, \#4, \#6, \#8, \#10, \#12, \#14), Hiếu đóng vai trò reviewer và merge.

*Câu 39: Khi gặp Git Merge Conflict giữa 2 người, nhóm xử lý ra sao?*
- *Đáp án*: Do nhóm phân ranh giới trách nhiệm rõ ràng (Hiếu làm Backend/Service, Sinh làm Frontend/Templates) nên rất ít khi đụng cùng 1 dòng code. Nếu có xung đột, nhóm sẽ họp trực tiếp, đối chiếu bằng lệnh `git diff`, chọn phiên bản code đúng và chạy lại bộ test 119 bài trước khi push.

*Câu 40: Nếu danh bạ tăng lên 100.000 liên hệ, hệ thống của em có bị treo không? Vì sao?*
- *Đáp án*: Không treo. Vì: (1) Tìm kiếm đã có GIN Trigram Index $O(log N)$; (2) Phân trang ở mức SQL `LIMIT/OFFSET`; (3) Chỉ render HTML partials bằng HTMX nên payload mạng chỉ vài kilobytes; (4) Bảng `PhoneNumber` có Index trên `contact_id`.

*Câu 41: Tại sao nhóm chọn Django Monolith + HTMX thay vì ReactJS + DRF?*
- *Đáp án*: (1) Giảm 50% độ phức tạp kiến trúc; (2) Không mất công viết Serializer/Deserializer JSON thừa thãi; (3) Tốc độ tải trang cực nhanh nhờ Server-Side Rendering (SSR); (4) HTMX mang lại trải nghiệm mượt mà như SPA (Single Page App) mà không tốn công quản lý state phức tạp ở client.

*Câu 42: Dự án đảm bảo chuẩn mã nguồn Clean Code như thế nào?*
- *Đáp án*: Sử dụng file cấu hình `.flake8` kiểm soát độ dài dòng, biến không dùng; dùng `black` format mã nguồn tự động, và chia tách rõ ràng các tầng Model - View - Service - Form.

*Câu 43: File `Makefile` trong dự án cung cấp những phím tắt gì?*
- *Đáp án*: Cung cấp các lệnh: `make run` (chạy server), `make test` (chạy pytest), `make migrate` (chạy migration), `make seed` (sinh dữ liệu mẫu), `make backup` (sao lưu database), giúp cô hoặc người chấm bài thao tác tiện lợi mà không cần nhớ lệnh dài.

*Câu 44: Em tự tin nhất ở phần kỹ thuật nào trong đồ án này?*
- *Đáp án*: Thuật toán Trigram Search kết hợp GIN Indexing và cơ chế Smart Merge bọc trong transaction nguyên tử. Đây là nghiệp vụ xử lý dữ liệu thực tế ở cấp độ enterprise mà các bài tập lớn thông thường ít khi làm tới.

*Câu 45: Nếu gặp lỗi 500 trên Production, em sẽ điều tra từ đâu?*
- *Đáp án*: (1) Kiểm tra log container: `docker compose logs -f web`; (2) Kiểm tra bảng `AuditLog` xem có hành vi bất thường nào vừa xảy ra; (3) Kiểm tra trạng thái kết nối CSDL và tài nguyên RAM/CPU của server.

*Câu 46: Dự án bảo vệ quyền riêng tư người dùng như thế nào?*
- *Đáp án*: Dữ liệu danh bạ của mỗi người được cô lập tuyệt đối qua `user_id`. Không có người dùng nào xem được danh bạ của người khác. Ngay cả Admin Panel cũng chỉ quản lý trạng thái tài khoản và audit log, không hiển thị danh bạ cá nhân của user.

*Câu 47: Để chạy lại đồ án này trên một máy tính mới tinh, cần làm những gì?*
- *Đáp án*: Chỉ cần 3 bước:
  1. `git clone <repo>`
  2. `cp .env.example .env`
  3. `docker compose up -d` (Mọi thứ từ database, migration đến web server sẽ tự động dựng lên hoàn chỉnh).

*Câu 48: Nhóm đã quản trị tiến độ và rủi ro ra sao trong quá trình làm?*
- *Đáp án*: Nhóm chia nhỏ tính năng thành 14 PRs trải đều từ 09/11 đến 20/11. Hoàn thành module cốt lõi trước (Auth, Contact Service), sau đó tới UI/UX và cuối cùng là kiểm thử và tối ưu.

*Câu 49: Điểm gì em nghĩ hệ thống có thể cải tiến tốt hơn nữa nếu có thêm thời gian?*
- *Đáp án*: (1) Thêm tính năng Import/Export danh bạ qua chuẩn VCF (vCard) và file Excel; (2) Tích hợp xác thực 2 bước 2FA (TOTP/Google Authenticator); (3) Cung cấp RESTful API có JWT để kết nối ứng dụng Mobile (Flutter/React Native).

*Câu 50: Em hãy tóm tắt ngắn gọn sự phối hợp giữa em và Sinh trong dự án?*
- *Đáp án*: Em và Sinh làm việc theo mô hình cộng tác chặt chẽ. Em chịu trách nhiệm phần "xương sống và động cơ" (Backend, CSDL, Thuật toán, DevOps), còn Sinh chịu trách nhiệm phần "diện mạo và chất lượng" (UI/UX, HTMX, Quản trị và Kiểm thử tự động). Sự phối hợp nhịp nhàng thể hiện rõ qua 14 PRs cross-review trên Git.
