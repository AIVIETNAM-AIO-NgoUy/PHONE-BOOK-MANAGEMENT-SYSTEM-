#set page(
  paper: "a4",
  margin: (x: 1.8cm, top: 2cm, bottom: 2cm),
  header: context {
    if here().page() > 1 {
      text(9pt, fill: rgb("#64748b"))[
        *Phone Book Management System* | Sổ tay vấn đáp thực chiến - *Sinh (UI/UX, Admin & QA)*
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

#let callout(title: "", body, color: rgb("#0284c7")) = block(
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
  #text(12pt, weight: "bold", fill: rgb("#0284c7"))[DÀNH CHO: SINH (LEAD FRONTEND UI/UX, ADMIN GOVERNANCE & QA SPECIALIST)] \
  #v(2pt)
  #text(9pt, fill: rgb("#64748b"))[Đề tài: Phone Book Management System | Kiến trúc HTMX Dynamic UI, Admin Audit Log & Automation Testing]
]

#v(10pt)

= PHẦN 1: ĐỊNH VỊ VAI TRÒ & KỊCH BẢN MỞ ĐẦU 1 PHÚT

== 1.1. Phạm vi trách nhiệm chính (Làm chủ 7 PRs trên Git)
- *PR \#2 (`feature/ui-design-system`)*: CSS Design Token system, Typography, responsive base layout & static assets.
- *PR \#4 (`feature/groups-management`)*: Contact Groups model, quan hệ N-N, categorization services & UI quản lý nhóm.
- *PR \#6 (`feature/favorites-priority`)*: Hệ thống quản lý danh bạ yêu thích & phân cấp mức độ ưu tiên Priority (1-5).
- *PR \#8 (`feature/admin-governance`)*: Bảng điều khiển quản trị (Admin Dashboard), hệ thống giám sát Audit Logging & khóa tài khoản.
- *PR \#10 (`feature/contacts-ui-htmx`)*: Giao diện tương tác thời gian thực với HTMX, Live Search, Modal xác nhận xóa hàng loạt.
- *PR \#12 (`feature/test-backend-suites`)*: Bộ 119 bài kiểm thử tự động toàn diện: Unit test, Contract test & Security isolation test.
- *PR \#14 (`feature/test-e2e-benchmarks`)*: Kịch bản kiểm thử tích hợp E2E, UI navigation và kiểm thử chịu tải bằng Locust.

== 1.2. Kịch bản mở đầu 60 giây (Nói tự tin, dứt khoát)
#tip(title: "KỊCH BẢN PHÁT BIỂU 60S ĐẦU TIÊN KHI BƯỚC VÀO BÁO CÁO")[
  "Dạ em chào cô. Trong đồ án Phone Book Management System, em phụ trách toàn bộ *Trải nghiệm người dùng UI/UX, Kiến trúc Frontend động với HTMX, Phân hệ Quản trị Admin & Giám sát Audit Log, cùng Hệ thống kiểm thử tự động toàn diện*. Ba đóng góp kỹ thuật trọng tâm của em gồm:
  1. *Trải nghiệm người dùng hiện đại không tải lại trang*: Ứng dụng HTMX kết hợp hệ thống CSS Tokens tự xây dựng, mang lại tốc độ phản hồi tức thì dưới 50ms mà không cần phụ thuộc thư viện nặng như React.
  2. *Quản trị hệ thống & Audit Logging bất biến*: Giám sát toàn bộ hoạt động hệ thống, lưu vết chi tiết từng thay đổi dữ liệu dạng JSON diff để bảo đảm an ninh và chống chối bỏ.
  3. *Chất lượng phần mềm bảo đảm tuyệt đối*: Xây dựng 119 bài kiểm thử tự động bao phủ từ tính năng, phân lập bảo mật đến bài test tải mô phỏng 100 người dùng đồng thời bằng Locust."
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
  [Mở trang chủ danh bạ -> Thu nhỏ cửa sổ trình duyệt sang kích thước Mobile],
  [Dạ giao diện sử dụng hệ thống CSS Design Tokens tự viết 100%, hỗ trợ Responsive mượt mà, tự động chuyển đổi bảng dữ liệu sang dạng thẻ Card trên di động.],
  
  [2 (45s)],
  [Gõ từ khóa vào ô tìm kiếm danh bạ -> Quan sát bảng cập nhật tức thì],
  [Đây là tính năng Live Search thời gian thực bằng HTMX với cơ chế debounce 300ms. Chỉ có phần thân bảng (`tbody`) được hoán đổi nội dung mà không cần reload trang.],
  
  [3 (30s)],
  [Bấm vào icon ngôi sao của một liên hệ -> Icon đổi màu vàng ngay lập tức],
  [Thao tác đánh dấu Favorite được xử lý qua HTMX `hx-post` với `hx-swap="outerHTML"`. Trang Favorites cho phép lọc theo 5 mức độ ưu tiên từ khẩn cấp đến bình thường.],
  
  [4 (30s)],
  [Tạo một Nhóm mới "Đối tác 2026" -> Thêm 2 liên hệ vào nhóm],
  [Mô hình Nhóm được thiết kế theo quan hệ nhiều-nhiều (N-N), một liên hệ có thể thuộc nhiều nhóm mà khi xóa nhóm thì liên hệ gốc không hề bị ảnh hưởng.],
  
  [5 (45s)],
  [Đăng nhập quyền Admin -> Mở Admin Dashboard -> Chỉ vào bảng Audit Log -> Bấm khóa 1 tài khoản],
  [Toàn bộ hoạt động trong hệ thống đều được tự động ghi lại trong Audit Log. Giao diện cho phép xem chi tiết sai khác (diff) dữ liệu trước và sau khi sửa.],
  
  [6 (15s)],
  [Mở Terminal chạy `./venv/bin/pytest` -> Chỉ vào kết quả 119 tests xanh lá],
  [Toàn bộ hệ thống được bảo vệ bởi 119 bài kiểm thử tự động, chạy xong trong 6 giây, đảm bảo không có bất kỳ lỗi hồi quy hay rò rỉ dữ liệu giữa các người dùng.]
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
  
  [`frontend/static/css/styles.css`],
  [`:root` Design Tokens],
  [Hệ thống biến CSS chuẩn: `--primary-600`, `--surface-bg`, thang spacing và border-radius.],
  
  [`.../contacts/partials/search_bar.html`],
  [`hx-get`, `hx-trigger`],
  [Cấu hình `hx-trigger="keyup changed delay:300ms"`, `hx-target="#contact-table-body"`.],
  
  [`frontend/static/js/app.js`],
  [`htmx:configRequest`],
  [Tự động bắt sự kiện HTMX để nhúng `X-CSRFToken` vào mọi HTTP header request ngầm.],
  
  [`backend/apps/admin_panel/models.py`],
  [`AuditLog`],
  [Trường `changes = models.JSONField()`, lưu trữ vết thay đổi bất biến (immutable trail).],
  
  [`backend/apps/admin_panel/services.py`],
  [`AuditService.log_action()`],
  [Hàm ghi nhật ký tập trung, tự động bóc tách IP, User-Agent và tính toán diff dữ liệu.],
  
  [`backend/tests/security/...`],
  [`test_contact_isolation.py`],
  [Kiểm thử phân lập người dùng (Tenant Isolation), chứng minh User A không thể đọc trộm User B.],
  
  [`backend/tests/performance/locustfile.py`],
  [`PhoneBookUser`],
  [Kịch bản test tải Locust, giả lập 100 người dùng đồng thời tìm kiếm và cập nhật dữ liệu.]
)

---

= PHẦN 4: 50 CÂU HỎI VẤN ĐÁP & ĐÁP ÁN ĐẮT GIÁ CHO SINH

== A. Frontend Architecture, UI/UX & HTMX (Câu 1 - 10)

*Câu 1: HTMX hoạt động như thế nào trong dự án này?*
- *Đáp án*: HTMX cho phép các thẻ HTML thông thường (`input`, `button`, `form`) gửi request AJAX trực tiếp lên server thông qua các thuộc tính khai báo (`hx-get`, `hx-post`). Server Django xử lý và trả về một đoạn HTML nhỏ (Partial Template), HTMX sẽ tự động hoán đổi (swap) đoạn HTML đó vào vị trí DOM được chỉ định (`hx-target`) mà không cần viết code JavaScript phức tạp.

*Câu 2: Thuộc tính `hx-trigger="keyup changed delay:300ms"` trong ô tìm kiếm có tác dụng gì?*
- *Đáp án*: Đây là kỹ thuật *Debounce*: 
  - `keyup`: Lắng nghe sự kiện người dùng nhả phím.
  - `changed`: Chỉ kích hoạt nếu giá trị ô nhập thực sự thay đổi.
  - `delay:300ms`: Chờ người dùng ngừng gõ trong 300ms mới gửi request lên server. Kỹ thuật này giúp giảm 90% số lượng request rác không cần thiết lên CSDL khi người dùng đang gõ liên tục.

*Câu 3: Phân biệt `hx-swap="innerHTML"` và `hx-swap="outerHTML"`? Khi nào dùng cái nào?*
- *Đáp án*: 
  - `innerHTML`: Thay thế nội dung *bên trong* của thẻ mục tiêu. Dùng khi cập nhật danh sách bảng (`tbody`), giữ nguyên thẻ cha.
  - `outerHTML`: Thay thế *toàn bộ* thẻ mục tiêu (bao gồm cả thẻ cha). Dùng khi toggle nút bấm (như nút ngôi sao Favorite) hoặc modal popup.

*Câu 4: Em xử lý bảo mật CSRF Token trong HTMX như thế nào để không bị lỗi 403 Forbidden?*
- *Đáp án*: Trong file `frontend/static/js/app.js`, em lắng nghe sự kiện vòng đời `htmx:configRequest`. Khi có bất kỳ request HTMX nào chuẩn bị gửi đi, script sẽ tự động đọc cookie `csrftoken` và gán vào header `evt.detail.headers['X-CSRFToken']`.

*Câu 5: Tại sao em chọn HTMX thay vì sử dụng ReactJS hoặc VueJS?*
- *Đáp án*: (1) Giữ vững kiến trúc Server-Side Rendering (SSR) an toàn và tối ưu SEO; (2) Không mất công cài đặt Node.js, Webpack hay quản lý state Redux phức tạp; (3) Dung lượng script cực nhẹ chỉ ~14KB (so với hàng megabytes của React bundle); (4) Phát triển nhanh gấp đôi mà vẫn đạt được trải nghiệm mượt mà như Single Page App.

*Câu 6: Hệ thống CSS Design Tokens trong `styles.css` được xây dựng theo nguyên tắc nào?*
- *Đáp án*: Em xây dựng hệ thống biến CSS Custom Properties `:root` theo chuẩn 3 tầng:
  - *Primitive Tokens*: Bảng màu gốc từ 50 đến 900 (`--blue-600`, `--gray-100`).
  - *Semantic Tokens*: Biến mang ý nghĩa ngữ cảnh (`--primary-bg`, `--text-danger`, `--surface-card`).
  - *Component Tokens*: Khoảng cách Spacing scale 4px-32px, Typography font-size, và Border-radius. Giúp giao diện đồng nhất tuyệt đối và dễ dàng chuyển đổi Dark/Light mode.

*Câu 7: Giao diện có Responsive trên điện thoại không? Em xử lý giao diện bảng (Table) trên màn hình nhỏ thế nào?*
- *Đáp án*: Hoàn toàn Responsive qua CSS Media Queries `@media (max-width: 768px)`. Trên desktop hiển thị bảng đa cột đầy đủ; trên mobile, bảng tự động chuyển đổi sang dạng thẻ Card dọc, ẩn bớt các cột ít quan trọng (như chức danh, công ty) và đưa các nút thao tác nhanh xuống chân thẻ.

*Câu 8: Thuộc tính `hx-indicator="#search-spinner"` có vai trò gì trong trải nghiệm người dùng?*
- *Đáp án*: Quản lý trạng thái tải (Loading State). Khi request tìm kiếm bắt đầu gửi đi, HTMX tự động thêm class `htmx-request` để làm hiển thị icon xoay (spinner). Khi nhận được response, spinner tự động ẩn đi, giúp người dùng biết hệ thống đang phản hồi mà không bị cảm giác "đơ" web.

*Câu 9: Modal xác nhận xóa hàng loạt (Batch Delete Modal) được triển khai thế nào?*
- *Đáp án*: Sử dụng JavaScript lắng nghe checkbox các dòng -> Gửi danh sách ID đã chọn qua HTMX POST lên server -> Server kiểm tra quyền và trả về đoạn HTML Modal hiển thị số lượng bản ghi sắp xóa kèm cảnh báo -> Người dùng bấm nút "Xác nhận xóa" thì một request DELETE/POST mới được kích hoạt để dọn dẹp CSDL.

*Câu 10: Tại sao dự án không sử dụng Bootstrap hay TailwindCSS mà tự viết CSS thuần?*
- *Đáp án*: Thể hiện năng lực làm chủ CSS chuyên sâu, loại bỏ 100% các class CSS rác không dùng đến, kiểm soát hoàn toàn tính thẩm mỹ theo đúng nhận diện thương hiệu, và giúp tốc độ tải trang đạt điểm tối đa (Lighthouse Performance 98-100).

---

== B. Module Quản trị (Admin Panel) & Audit Logging (Câu 11 - 20)

*Câu 11: Phân hệ Admin Panel do em phụ trách giải quyết bài toán gì cho doanh nghiệp?*
- *Đáp án*: Giải quyết bài toán Quản trị & Tuân thủ (Governance & Compliance). Giúp ban quản trị: (1) Nắm bắt bức tranh tổng thể qua các chỉ số thống kê Dashboard; (2) Quản lý trạng thái và vòng đời tài khoản người dùng; (3) Giám sát an ninh, phát hiện hành vi bất thường thông qua nhật ký kiểm toán Audit Log.

*Câu 12: Model `AuditLog` lưu trữ những thông tin cốt lõi nào?*
- *Đáp án*: Lưu 7 trường dữ liệu trọng yếu: `timestamp` (thời điểm), `actor` (ai thực hiện), `action` (CREATE, UPDATE, DELETE, MERGE, LOCK), `entity_type` (đối tượng tác động), `entity_id` (ID đối tượng), `ip_address` (địa chỉ IP mạng), và trường `changes` kiểu JSON lưu chi tiết dữ liệu sai khác.

*Câu 13: Làm thế nào em ghi nhận được chi tiết "dữ liệu trước và sau khi thay đổi" (diff) vào trường `changes`?*
- *Đáp án*: Trong `AuditService`, trước khi lưu đối tượng, em lấy bản snapshot dữ liệu cũ từ database, sau đó so sánh từng trường với dữ liệu mới từ Form. Nếu có sự khác biệt, em đóng gói thành dict JSON: `{"email": {"old": "a@gmail.com", "new": "b@gmail.com"}}` và lưu vào `changes`.

*Câu 14: Tính năng Khóa tài khoản (Account Lockout) trên bảng quản trị hoạt động ra sao?*
- *Đáp án*: Admin bấm nút Toggle trạng thái trên bảng người dùng -> HTMX gửi request POST `toggle-user-status` -> Server đảo cờ `is_active` (hoặc `is_locked`) của `CustomUser` -> Ghi log vào `AuditLog` -> Server chỉ trả về đúng thành phần HTML Badge (`Active`/`Locked`) để HTMX cập nhật tại chỗ mà không phải tải lại cả trang Admin.

*Câu 15: Em bảo vệ Admin Panel chống lại sự truy cập trái phép của người dùng thông thường như thế nào?*
- *Đáp án*: Sử dụng Decorator `@staff_member_required` hoặc kiểm tra quyền trong View: `if not request.user.is_staff: raise PermissionDenied`. Nếu người dùng thường cố tình truy cập vào URL `/admin-panel/`, hệ thống sẽ trả về mã lỗi HTTP 403 Forbidden cùng trang thông báo lỗi tùy biến thân thiện.

*Câu 16: Tại sao nhóm lại tự viết phân hệ Admin Panel mà không dùng Django Admin mặc định?*
- *Đáp án*: Django Admin mặc định có giao diện thô ráp, không đồng bộ với Design System của dự án, thiếu tính năng tương tác thời gian thực bằng HTMX, và khó mở rộng các báo cáo Dashboard thống kê chuyên sâu kèm tính năng phân tích JSON diff của Audit Log.

*Câu 17: Bảng Audit Log có cho phép Quản trị viên sửa hoặc xóa dòng nhật ký không? Vì sao?*
- *Đáp án*: Tuyệt đối KHÔNG. Audit Log được thiết kế theo nguyên lý Bất biến (Append-Only / Immutable). Không có bất kỳ giao diện hay API nào cho phép Update hay Delete bản ghi audit. Điều này đảm bảo tính toàn vẹn pháp lý (non-repudiation) khi xảy ra sự cố bảo mật cần điều tra vết.

*Câu 18: Bộ lọc Audit Log trên giao diện hỗ trợ tìm kiếm theo những tiêu chí nào?*
- *Đáp án*: Hỗ trợ lọc đa chiều: (1) Lọc theo loại hành vi (Action: Tạo, Sửa, Xóa, Gộp danh bạ, Khóa tài khoản); (2) Lọc theo Người thực hiện (Actor); (3) Lọc theo khoảng thời gian (Từ ngày - Đến ngày).

*Câu 19: Trang Dashboard Admin cung cấp những biểu đồ và chỉ số thống kê nào?*
- *Đáp án*: Cung cấp 4 thẻ chỉ số nhanh: Tổng User, Số User đang hoạt động, Tổng số liên hệ Contact, Số thao tác thực hiện trong 24h; kèm danh sách 10 hoạt động gần nhất theo thời gian thực.

*Câu 20: Nếu bảng Audit Log có hàng triệu bản ghi thì giao diện có bị đơ không? Em tối ưu thế nào?*
- *Đáp án*: Không bị đơ. Vì em đã thiết lập chỉ mục (Indexing) trên trường `timestamp` và `actor` ở cấp độ CSDL, kết hợp phân trang Server-Side với `Paginator` 25 dòng/trang. Trình duyệt chỉ nhận về đúng 25 dòng HTML nhẹ, không tiêu tốn tài nguyên client.

---

== C. Nghiệp vụ Nhóm (Groups) & Yêu thích (Favorites) (Câu 21 - 30)

*Câu 21: Mối quan hệ giữa bảng `Contact` và `Group` được thiết kế như thế nào?*
- *Đáp án*: Quan hệ Nhiều - Nhiều (Many-to-Many). Một liên hệ có thể thuộc nhiều nhóm (ví dụ: vừa thuộc nhóm "Đồng nghiệp", vừa thuộc nhóm "Bạn đại học"), và một nhóm chứa nhiều liên hệ. Quan hệ này được hiện thực hóa qua bảng trung gian `GroupMember`.

*Câu 22: Khi xóa một Nhóm (Group) thì các liên hệ (Contact) bên trong nhóm đó có bị xóa theo không?*
- *Đáp án*: Tuyệt đối KHÔNG. Khi xóa một Group, nhờ thiết lập quan hệ bảng trung gian, CSDL chỉ xóa các liên kết trong bảng `GroupMember`. Các đối tượng `Contact` gốc vẫn tồn tại nguyên vẹn trong danh bạ của người dùng.

*Câu 23: Phân hệ Favorites quản lý các mức độ ưu tiên (Priority) ra sao?*
- *Đáp án*: Model `FavoriteItem` có trường `priority` kiểu số nguyên từ 1 đến 5:
  - *Mức 1 (Khẩn cấp / Gia đình)*: Hiển thị Badge đỏ nổi bật.
  - *Mức 2 - 3 (Công việc / Thường xuyên)*: Hiển thị Badge cam/vàng.
  - *Mức 4 - 5 (Ưu tiên tiêu chuẩn)*: Hiển thị Badge xanh.
  Người dùng có thể sắp xếp hoặc lọc danh bạ yêu thích theo đúng mức độ ưu tiên này.

*Câu 24: Cơ chế hoạt động của Nút ngôi sao Favorite trên bảng danh bạ qua HTMX diễn ra thế nào?*
- *Đáp án*: Khi click vào ngôi sao: HTMX gửi POST tới endpoint `/favorites/toggle/<contact_id>/` -> Server kiểm tra nếu đã thích thì xóa khỏi `FavoriteItem`, nếu chưa thì thêm mới -> Server render lại partial template `favorite_toggle_button.html` -> HTMX hoán đổi `outerHTML`, biểu tượng lập tức chuyển giữa sao vàng và sao xám trong 20ms.

*Câu 25: Làm sao để ngăn chặn người dùng vô tình thêm một liên hệ vào Favorites nhiều lần?*
- *Đáp án*: Trong Model `FavoriteItem`, em khai báo ràng buộc duy nhất trong `Meta`: `unique_together = ('user', 'contact')`. CSDL PostgreSQL sẽ tạo một Unique Index trên cặp khóa này, ngăn chặn triệt để dữ liệu trùng lặp ở cả tầng code và tầng database.

*Câu 26: Giao diện quản lý thành viên của Nhóm (Group Member Section) hỗ trợ những tính năng gì?*
- *Đáp án*: Hỗ trợ: (1) Hiển thị danh sách thành viên hiện có; (2) Ô tìm kiếm nhanh liên hệ để thêm vào nhóm; (3) Nút gỡ liên hệ ra khỏi nhóm bằng HTMX với hiệu ứng mờ dần (fade out) mượt mà không cần load lại trang.

*Câu 27: Người dùng khác có xem trộm được danh sách Nhóm hoặc Favorites của nhau không?*
- *Đáp án*: Hoàn toàn không. Mọi truy vấn trong `Group` và `FavoriteItem` đều bắt buộc lọc qua điều kiện `user=request.user`. Cơ chế bảo mật cách ly này được kiểm chứng qua các bài test tự động trong test suite.

*Câu 28: Sự khác biệt về mặt trải nghiệm UX giữa Nhóm (Group) và Danh sách yêu thích (Favorites)?*
- *Đáp án*: 
  - *Nhóm*: Dùng để phân loại theo ngữ cảnh công việc/tổ chức (Gia đình, Công ty, Khách hàng).
  - *Favorites*: Dùng để truy cập tức thời (Quick Dial / Emergency), đánh giá mức độ thân thiết dựa trên tần suất liên lạc.

*Câu 29: Nhóm hỗ trợ tùy biến nhận diện thị giác như thế nào?*
- *Đáp án*: Mỗi nhóm có trường `color_code` (mã màu Hex) và `icon`. Trên giao diện, mỗi liên hệ thuộc nhóm sẽ có một Badge nhỏ mang màu sắc đặc trưng của nhóm đó, giúp người dùng nhận diện đối tượng bằng mắt chỉ trong 0.5 giây.

*Câu 30: Khi hai danh bạ được Gộp (Merge), các liên kết Nhóm và Yêu thích được bảo toàn ra sao?*
- *Đáp án*: Trong service `merge_contacts`, hệ thống duyệt qua toàn bộ nhóm của liên hệ phụ. Nếu liên hệ chính chưa có trong nhóm đó, nó sẽ tự động gán liên hệ chính vào nhóm, đảm bảo sau khi gộp không bị mất mát bất kỳ mối quan hệ xã hội nào của danh bạ.

---

== D. Kiểm thử Tự động (Testing Automation) & Performance (Câu 31 - 35)

*Câu 31: Hệ thống kiểm thử tự động của dự án gồm có những tầng nào?*
- *Đáp án*: Em tổ chức bộ test theo 4 tầng chuẩn kiểm thử phần mềm trong `backend/tests/`:
  1. *Unit Tests*: Kiểm tra độc lập logic các hàm trong Model, Service, Form.
  2. *Contract Tests*: Kiểm tra tính đúng đắn của hợp đồng dữ liệu đầu vào/ra.
  3. *Security Boundary Tests*: Kiểm thử phân lập bảo mật chống truy cập chéo giữa các người dùng.
  4. *Integration Tests & Performance*: Kiểm thử luồng nghiệp vụ E2E từ đăng nhập đến merge và bài test tải Locust.

*Câu 32: Dự án có tổng cộng bao nhiêu bài test và tỷ lệ Pass là bao nhiêu?*
- *Đáp án*: Có tổng cộng *119 bài test tự động*, tỷ lệ Pass tuyệt đối *100% (119 passed)* với thời gian chạy siêu tốc chỉ *6.22 giây*.

*Câu 33: Bài test `test_contact_isolation.py` kiểm tra điều gì và tại sao nó sống còn với bảo mật?*
- *Đáp án*: Nó kiểm tra ranh giới cách ly dữ liệu (Tenant Isolation). Kịch bản: Tạo 2 người dùng User A và User B. Cho User A cố tình gửi request đọc, sửa, xóa ID danh bạ thuộc quyền sở hữu của User B. Bài test khẳng định hệ thống phải luôn ném ra mã lỗi 404/403, chứng minh không bao giờ có chuyện lộ lọt dữ liệu chéo.

*Câu 34: Bộ test Contract (`test_contact_contracts.py`) giải quyết bài toán gì trong làm việc nhóm?*
- *Đáp án*: Đóng vai trò là "bản cam kết" giữa Backend và Frontend. Nó kiểm tra nghiêm ngặt xem các Service khi nhận dữ liệu đầu vào không hợp lệ (sai số điện thoại, email sai định dạng, thiếu trường bắt buộc) có trả về đúng các mã lỗi và exception đã quy định hay không.

*Câu 35: Em đã sử dụng Locust để kiểm thử hiệu năng (Load Testing) như thế nào? Kết quả ra sao?*
- *Đáp án*: Trong `backend/tests/performance/locustfile.py`, em viết kịch bản mô phỏng đồng thời 100 người dùng thực hiện liên tục các hành vi: Tìm kiếm danh bạ, xem chi tiết, thêm liên hệ mới. Kết quả đo được: Tỷ lệ lỗi 0% (Failure Rate: 0%), thời gian phản hồi trung bình (Average Response Time) đạt dưới 45ms, đáp ứng tiêu chuẩn phần mềm thương mại.

---

== E. Toàn diện Hệ thống & Phối hợp Nhóm (Câu 36 - 50)

*Câu 36: Tại sao nhóm chọn mô hình Monorepo thay vì tách riêng 2 repo Frontend và Backend?*
- *Đáp án*: Monorepo giúp em và Hiếu làm việc trên cùng một lịch sử commit, đảm bảo template frontend và backend logic luôn đồng bộ phiên bản 100%, không bao giờ bị lệch cấu trúc và dễ dàng chạy test toàn diện trên một lệnh duy nhất.

*Câu 37: Trình bày quy trình làm việc trên Git (Branching & PR Model) của nhóm?*
- *Đáp án*: Nhóm áp dụng mô hình GitHub Flow chuẩn hóa gồm 14 PRs. Mỗi tính năng được tách nhánh `feature/...`, commit theo chuẩn *Conventional Commits* (`feat:`, `test:`, `fix:`), sau đó tạo PR và merge vào nhánh chính bằng lệnh `--no-ff` ("Merge pull request \#X from ...").

*Câu 38: Cơ chế Cross-Review giữa Hiếu và Sinh diễn ra như thế nào?*
- *Đáp án*: Nhóm chia đều 7-7. Khi Sinh làm author của các tính năng UI, Admin và Test (PRs chẵn: \#2, \#4, \#6, \#8, \#10, \#12, \#14), Hiếu sẽ review code và là người thực hiện Merge commit vào `main`. Ngược lại, khi Hiếu làm backend (PRs lẻ: \#1, \#3, \#5, \#7, \#9, \#11, \#13), Sinh sẽ review và merge.

*Câu 39: Khi gặp Git Merge Conflict giữa 2 người, nhóm xử lý ra sao?*
- *Đáp án*: Phân chia công việc theo ranh giới rõ ràng: Hiếu làm backend core, Sinh làm templates UI và test suites. Nếu có xung đột (thường ở file `urls.py` hoặc `settings`), hai bạn sẽ đối chiếu qua `git diff`, trao đổi trực tiếp và chạy lại 119 bài test trước khi merge.

*Câu 40: Nếu danh bạ tăng lên 100.000 liên hệ, giao diện của em có bị đơ không? Vì sao?*
- *Đáp án*: Hoàn toàn không. Vì em áp dụng phân trang Server-side, mỗi lần chỉ nạp đúng 20 dòng HTML lên DOM. Phía client không phải lưu trữ danh sách khổng lồ trong bộ nhớ JavaScript như các ứng dụng React truyền thống.

*Câu 41: Tại sao nhóm chọn Django Monolith + HTMX thay vì ReactJS + DRF?*
- *Đáp án*: Giảm thiểu một nửa số lượng code boilerplate, không phải viết serialize JSON rồi ở client lại parse ngược lại. Tốc độ render từ server cực nhanh, tận dụng được sức mạnh bảo mật session và CSRF sẵn có của Django.

*Câu 42: Dự án đảm bảo chuẩn mã nguồn Clean Code như thế nào?*
- *Đáp án*: Sử dụng công cụ linting `.flake8` kiểm soát cú pháp, dùng `black` tự động format code nhất quán, và phân tách các component HTML thành các partial templates tái sử dụng trong thư mục `partials/`.

*Câu 43: File `Makefile` trong dự án hỗ trợ những gì cho công tác kiểm thử?*
- *Đáp án*: Lệnh `make test` tự động kích hoạt `pytest` chạy toàn bộ 119 bài test và xuất báo cáo coverage; lệnh `make run` tự động khởi động máy chủ thử nghiệm cục bộ nhanh chóng.

*Câu 44: Em tự tin nhất ở phần kỹ thuật nào trong đồ án này?*
- *Đáp án*: Tự tin nhất ở việc làm chủ công nghệ HTMX kết hợp CSS Design Tokens thuần và hệ thống kiểm thử tự động 119 bài test. Giao diện mượt mà không thua kém Single Page App nhưng mã nguồn vô cùng tinh gọn và tin cậy.

*Câu 45: Nếu gặp lỗi 500 trên Production, em sẽ điều tra từ đâu?*
- *Đáp án*: Mở Admin Panel xem chi tiết dòng ghi nhận trong bảng `AuditLog`, sau đó vào Terminal kiểm tra log thời gian thực của Docker `docker compose logs web`.

*Câu 46: Dự án bảo vệ quyền riêng tư người dùng như thế nào?*
- *Đáp án*: Áp dụng triệt để nguyên lý "Zero Trust" giữa các tài khoản: Mọi dữ liệu danh bạ, nhóm, yêu thích đều bị giới hạn bởi `user_id`, được chứng minh qua bài test bảo mật `test_contact_isolation.py`.

*Câu 47: Để chạy lại đồ án này trên một máy tính mới tinh, cần làm những gì?*
- *Đáp án*: Rất đơn giản qua 3 bước: `git clone`, `cp .env.example .env`, và chạy `docker compose up -d` hoặc chạy môi trường ảo Python với `make migrate && make seed`.

*Câu 48: Nhóm đã quản trị tiến độ và rủi ro ra sao trong quá trình làm?*
- *Đáp án*: Lập kế hoạch 14 PRs tuần tự từ ngày 09/11 đến 20/11. Hoàn thành chức năng cốt lõi trước, tiếp theo là giao diện và phân hệ quản trị, cuối cùng hoàn thiện toàn bộ bộ test kiểm thử chất lượng trước khi báo cáo.

*Câu 49: Điểm gì em nghĩ hệ thống có thể cải tiến tốt hơn nữa nếu có thêm thời gian?*
- *Đáp án*: (1) Bổ sung giao diện Dark Mode tự động theo hệ điều hành; (2) Tích hợp thông báo đẩy (Web Push Notifications) khi có danh bạ mới hoặc có cảnh báo đăng nhập bất thường; (3) Hỗ trợ thao tác kéo thả (Drag and Drop) liên hệ vào nhóm.

*Câu 50: Em hãy tóm tắt ngắn gọn sự phối hợp giữa em và Hiếu trong dự án?*
- *Đáp án*: Em và Hiếu phối hợp theo thế "Song kiếm hợp bích": Hiếu phụ trách nền móng backend vững chắc, cơ sở dữ liệu và thuật toán tối ưu; em phụ trách diện mạo giao diện mượt mà, phân hệ quản trị an ninh và bộ test tự động bảo vệ chất lượng. Cây Git 14 PRs cross-review chính là minh chứng rõ nhất cho tinh thần làm việc nhóm chuyên nghiệp.
