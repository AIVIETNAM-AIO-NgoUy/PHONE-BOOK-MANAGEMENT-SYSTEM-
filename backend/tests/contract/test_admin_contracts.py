"""Contract tests for administrative user governance endpoints (T088)."""

import pytest
from django.contrib.messages import get_messages
from django.test import Client


@pytest.mark.django_db
class TestAdminRbacGuardContract:
    """Contract tests verifying RBAC 403 Forbidden across all 5 admin endpoints."""

    def test_anonymous_and_standard_users_receive_403_on_all_admin_endpoints(
        self, user_factory, caplog
    ):
        standard_user = user_factory(
            username="std_user",
            email="stduser@example.com",
            role="User",
            is_staff=False,
        )
        target_user = user_factory(username="target_rbac", email="targetrbac@example.com")

        endpoints = [
            ("get", "/admin-panel/", {}),
            ("get", "/admin-panel/users/", {}),
            ("get", "/admin-panel/users/create/", {}),
            ("post", "/admin-panel/users/create/", {"username": "guard_u", "email": "gu@test.com"}),
            ("get", f"/admin-panel/users/{target_user.pk}/", {}),
            ("get", f"/admin-panel/users/{target_user.pk}/edit/", {}),
            ("post", f"/admin-panel/users/{target_user.pk}/edit/", {"email": "edit@test.com"}),
            ("post", f"/admin-panel/users/{target_user.pk}/delete/", {"confirm": "true"}),
            ("post", f"/admin-panel/users/{target_user.pk}/lock/", {"reason": "Policy"}),
            ("post", f"/admin-panel/users/{target_user.pk}/unlock/", {}),
        ]

        anon_client = Client()
        std_client = Client()
        std_client.force_login(standard_user)

        for method, path, data in endpoints:
            anon_resp = getattr(anon_client, method)(path, data)
            assert anon_resp.status_code == 403, f"Expected 403 for anon {method.upper()} {path}"

            std_resp = getattr(std_client, method)(path, data)
            assert std_resp.status_code == 403, f"Expected 403 for std user {method.upper()} {path}"

        target_user.refresh_from_db()
        assert target_user.account_status == "Active"


@pytest.mark.django_db
class TestAdminDashboardContract:
    """Contract tests for GET /admin-panel/ (admin-contracts.md 2.1)."""

    def test_dashboard_renders_kpis_recent_registrations_and_audit_logs(self, user_factory):
        from apps.admin_panel.models import AuditLog

        admin_user = user_factory(
            username="admin_dash",
            email="admindash@example.com",
            role="Admin",
            is_staff=True,
        )
        # Create 11 standard users (9 active, 2 locked) -> total 12 including admin
        created_users = []
        for idx in range(1, 12):
            status = "Locked" if idx in {10, 11} else "Active"
            created_users.append(
                user_factory(
                    username=f"reg_user_{idx:02d}",
                    email=f"reg{idx:02d}@example.com",
                    account_status=status,
                )
            )

        AuditLog.objects.create(
            actor=admin_user,
            actor_username_snapshot=admin_user.username,
            target_user=created_users[-1],
            target_username_snapshot=created_users[-1].username,
            action="ACCOUNT_LOCKED",
            details={"reason": "Initial audit check"},
        )

        client = Client()
        client.force_login(admin_user)
        response = client.get("/admin-panel/")

        assert response.status_code == 200
        template_names = [t.name for t in response.templates if t.name]
        assert "admin_panel/dashboard.html" in template_names
        assert response.context["total_users_count"] == 12
        assert response.context["active_users_count"] == 10
        assert response.context["locked_users_count"] == 2
        assert len(response.context["recent_registrations"]) <= 10
        assert len(response.context["recent_registrations"]) == 10
        assert len(response.context["recent_audit_logs"]) >= 1
        assert b"ACCOUNT_LOCKED" in response.content or b"Account Locked" in response.content

    def test_staff_user_with_is_staff_true_can_access_dashboard(self, user_factory):
        staff_user = user_factory(
            username="staff_only",
            email="staffonly@example.com",
            role="User",
            is_staff=True,
        )
        client = Client()
        client.force_login(staff_user)
        response = client.get("/admin-panel/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestAdminUserListContract:
    """Contract tests for GET /admin-panel/users/ (admin-contracts.md 2.2)."""

    def test_user_list_paginates_25_per_page_searches_filters_sorts_and_htmx(self, user_factory):
        admin_user = user_factory(
            username="aaa_admin",
            email="admin@example.com",
            role="Admin",
            is_staff=True,
        )
        for idx in range(1, 28):
            user_factory(
                username=f"member_{idx:02d}",
                email=f"member_{idx:02d}@example.com",
                account_status="Locked" if idx % 5 == 0 else "Active",
            )
        searchable = user_factory(
            username="ZebraLookup",
            email="Special.Match@OrgTest.COM",
            account_status="Locked",
        )

        client = Client()
        client.force_login(admin_user)

        # Page 1 has 25 rows, page 2 has remaining 4 rows (total 29 users)
        page_1 = client.get("/admin-panel/users/")
        assert page_1.status_code == 200
        template_names = [t.name for t in page_1.templates if t.name]
        assert "admin_panel/user_list.html" in template_names
        assert len(page_1.context["page_obj"].object_list) == 25

        page_2 = client.get("/admin-panel/users/?page=2")
        assert page_2.status_code == 200
        assert len(page_2.context["page_obj"].object_list) == 4

        # Search by username substring (case-insensitive)
        q_username = client.get("/admin-panel/users/?q=zebralook")
        assert q_username.status_code == 200
        assert [u.pk for u in q_username.context["page_obj"].object_list] == [searchable.pk]

        # Search by email substring (case-insensitive)
        q_email = client.get("/admin-panel/users/?q=special.match")
        assert q_email.status_code == 200
        assert [u.pk for u in q_email.context["page_obj"].object_list] == [searchable.pk]

        # Status filter Active / Locked / all
        locked_resp = client.get("/admin-panel/users/?status=Locked")
        assert locked_resp.status_code == 200
        locked_users = list(locked_resp.context["page_obj"].object_list)
        assert len(locked_users) == 6
        assert all(u.account_status == "Locked" for u in locked_users)

        active_resp = client.get("/admin-panel/users/?status=Active")
        assert active_resp.status_code == 200
        active_users = list(active_resp.context["page_obj"].object_list)
        assert all(u.account_status == "Active" for u in active_users)

        all_resp = client.get("/admin-panel/users/?status=all")
        assert all_resp.status_code == 200
        assert all_resp.context["page_obj"].paginator.count == 29

        # Sorting: username_asc, date_asc, date_desc
        sort_user_asc = client.get("/admin-panel/users/?sort=username_asc")
        assert sort_user_asc.status_code == 200
        first_user_asc = sort_user_asc.context["page_obj"].object_list[0]
        assert first_user_asc.username == "aaa_admin"

        sort_date_asc = client.get("/admin-panel/users/?sort=date_asc")
        assert sort_date_asc.status_code == 200
        assert sort_date_asc.context["page_obj"].object_list[0].pk == admin_user.pk

        sort_date_desc = client.get("/admin-panel/users/?sort=date_desc")
        assert sort_date_desc.status_code == 200
        assert sort_date_desc.context["page_obj"].object_list[0].pk == searchable.pk

        # HTMX partial response
        htmx_resp = client.get(
            "/admin-panel/users/?q=Zebra",
            HTTP_HX_REQUEST="true",
        )
        assert htmx_resp.status_code == 200
        htmx_templates = [t.name for t in htmx_resp.templates if t.name]
        assert "admin_panel/partials/user_table_rows.html" in htmx_templates
        assert "admin_panel/user_list.html" not in htmx_templates
        assert b"ZebraLookup" in htmx_resp.content

    def test_htmx_filter_search_sort_synchronizes_oob_count_pills_and_hidden_status(
        self, user_factory
    ):
        admin_user = user_factory(
            username="oob_admin",
            email="oobadmin@example.com",
            role="Admin",
            is_staff=True,
        )
        user_factory(username="oob_active", email="oobactive@example.com", account_status="Active")
        user_factory(username="oob_locked", email="ooblocked@example.com", account_status="Locked")

        client = Client()
        client.force_login(admin_user)

        # Full page render should not contain hx-swap-oob="true"
        full_resp = client.get("/admin-panel/users/")
        assert full_resp.status_code == 200
        assert b'hx-swap-oob="true"' not in full_resp.content
        assert b'id="admin-user-count-badge"' in full_resp.content
        assert b'id="admin-status-filter-pills"' in full_resp.content
        assert b'id="admin-status-hidden-input"' in full_resp.content

        # HTMX request with status=Locked, q=oob, sort=username_asc emits OOB sync blocks
        htmx_resp = client.get(
            "/admin-panel/users/?status=Locked&q=oob&sort=username_asc",
            HTTP_HX_REQUEST="true",
        )
        assert htmx_resp.status_code == 200
        html = htmx_resp.content.decode("utf-8")
        assert 'id="admin-user-count-badge"' in html
        assert 'id="admin-status-filter-pills"' in html
        assert 'id="admin-status-hidden-input"' in html
        assert 'hx-swap-oob="true"' in html
        assert 'value="Locked"' in html
        assert "?status=Active&q=oob&sort=username_asc" in html
        assert "oob_locked" in html
        assert "oob_active" not in html


@pytest.mark.django_db
class TestAdminUserDetailContract:
    """Contract tests for GET /admin-panel/users/<id>/ (admin-contracts.md 2.3)."""

    def test_detail_renders_safe_metadata_contact_count_and_masks_password_hash(self, user_factory):
        from apps.contacts.models import Contact, PhoneNumber

        admin_user = user_factory(
            username="admin_detail",
            email="admindetail@example.com",
            role="Admin",
            is_staff=True,
        )
        target = user_factory(
            username="johndoe",
            email="johndoe@example.com",
            full_name="John Doe",
        )
        for idx in range(3):
            c = Contact.objects.create(
                book=target.contact_book,
                full_name=f"Private Contact {idx}",
                email=f"private{idx}@secret.test",
            )
            PhoneNumber.objects.create(
                contact=c,
                phone_number=f"090123450{idx}",
                phone_type="Mobile",
                is_primary=True,
            )

        client = Client()
        client.force_login(admin_user)

        resp = client.get(f"/admin-panel/users/{target.pk}/")
        assert resp.status_code == 200
        template_names = [t.name for t in resp.templates if t.name]
        assert "admin_panel/user_detail.html" in template_names

        ctx_user = resp.context["target_user"]
        assert ctx_user.id == target.id
        assert ctx_user.username == "johndoe"
        assert ctx_user.email == "johndoe@example.com"
        assert ctx_user.full_name == "John Doe"
        assert ctx_user.role == "User"
        assert ctx_user.account_status == "Active"
        assert ctx_user.created_at is not None
        assert ctx_user.contact_count == 3

        html = resp.content.decode("utf-8")
        assert "johndoe" in html
        assert "johndoe@example.com" in html
        assert "John Doe" in html
        assert "3" in html
        # Credential masking
        assert target.password not in html
        assert "argon2" not in html
        assert "pbkdf2" not in html

        # Nonexistent user -> 404
        assert client.get("/admin-panel/users/999999/").status_code == 404


@pytest.mark.django_db
class TestAdminLockUnlockContract:
    """Contract tests for POST /admin-panel/users/<id>/lock/ and /unlock/."""

    def test_lock_account_standard_post_htmx_and_error_cases(self, user_factory):
        from apps.admin_panel.models import AuditLog

        admin_user = user_factory(
            username="admin_locker",
            email="adminlocker@example.com",
            role="Admin",
            is_staff=True,
        )
        target = user_factory(username="johndoe", email="johndoe@example.com")
        target2 = user_factory(username="janedoe", email="janedoe@example.com")

        client = Client()
        client.force_login(admin_user)

        # Standard POST lock with reason -> 302 + flash message + AuditLog
        resp = client.post(
            f"/admin-panel/users/{target.pk}/lock/",
            {"reason": "Suspicious activity"},
        )
        assert resp.status_code == 302
        assert resp.url == f"/admin-panel/users/{target.pk}/"
        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        assert "Account for user 'johndoe' has been locked and active sessions revoked." in msgs

        target.refresh_from_db()
        assert target.account_status == "Locked"
        log = AuditLog.objects.get(target_user=target, action="ACCOUNT_LOCKED")
        assert log.actor == admin_user
        assert log.actor_username_snapshot == "admin_locker"
        assert log.target_username_snapshot == "johndoe"
        assert log.details.get("reason") == "Suspicious activity"

        # Duplicate lock -> 400 ERR_ACCOUNT_ALREADY_LOCKED
        dup_resp = client.post(f"/admin-panel/users/{target.pk}/lock/", {})
        assert dup_resp.status_code == 400
        assert b"This account is already in Locked status." in dup_resp.content

        # Self-lock -> 400 ERR_ADMIN_SELF_LOCK
        self_resp = client.post(f"/admin-panel/users/{admin_user.pk}/lock/", {})
        assert self_resp.status_code == 400
        assert b"You cannot lock your own administrative account." in self_resp.content
        admin_user.refresh_from_db()
        assert admin_user.account_status == "Active"

        # HTMX lock -> 200 with updated badge and Unlock button
        htmx_resp = client.post(
            f"/admin-panel/users/{target2.pk}/lock/",
            {"reason": "HTMX test"},
            HTTP_HX_REQUEST="true",
        )
        assert htmx_resp.status_code == 200
        assert b"Locked" in htmx_resp.content
        assert b"Unlock" in htmx_resp.content

        # Missing target -> 404
        assert client.post("/admin-panel/users/999999/lock/", {}).status_code == 404

    def test_unlock_account_standard_post_htmx_and_error_cases(self, user_factory):
        from apps.admin_panel.models import AuditLog

        admin_user = user_factory(
            username="admin_unlocker",
            email="adminunlocker@example.com",
            role="Admin",
            is_staff=True,
        )
        locked_1 = user_factory(
            username="johndoe",
            email="johndoe@example.com",
            account_status="Locked",
        )
        locked_2 = user_factory(
            username="janedoe",
            email="janedoe@example.com",
            account_status="Locked",
        )

        client = Client()
        client.force_login(admin_user)

        # Standard POST unlock -> 302 + flash message + AuditLog
        resp = client.post(f"/admin-panel/users/{locked_1.pk}/unlock/", {})
        assert resp.status_code == 302
        assert resp.url == f"/admin-panel/users/{locked_1.pk}/"
        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        assert "Account for user 'johndoe' has been restored to Active status." in msgs

        locked_1.refresh_from_db()
        assert locked_1.account_status == "Active"
        log = AuditLog.objects.get(target_user=locked_1, action="ACCOUNT_UNLOCKED")
        assert log.actor == admin_user
        assert log.actor_username_snapshot == "admin_unlocker"
        assert log.target_username_snapshot == "johndoe"

        # Already active -> 400 ERR_ACCOUNT_ALREADY_ACTIVE
        dup_resp = client.post(f"/admin-panel/users/{locked_1.pk}/unlock/", {})
        assert dup_resp.status_code == 400
        assert b"Account is already active." in dup_resp.content

        # HTMX unlock -> 200 with updated badge and Lock button
        htmx_resp = client.post(
            f"/admin-panel/users/{locked_2.pk}/unlock/",
            {},
            HTTP_HX_REQUEST="true",
        )
        assert htmx_resp.status_code == 200
        assert b"Active" in htmx_resp.content
        assert b"Lock" in htmx_resp.content

        # Missing target -> 404
        assert client.post("/admin-panel/users/999999/unlock/", {}).status_code == 404


@pytest.mark.django_db
class TestAdminUserCreateContract:
    """Contract tests for GET and POST /admin-panel/users/create/."""

    def test_get_user_create_renders_form(self, user_factory):
        admin_user = user_factory(
            username="admin_c_get", email="adminget@example.com", role="Admin", is_staff=True
        )
        client = Client()
        client.force_login(admin_user)

        resp = client.get("/admin-panel/users/create/")
        assert resp.status_code == 200
        html = resp.content.decode("utf-8")
        assert "Create User Account" in html
        assert 'name="username"' in html
        assert 'name="email"' in html
        assert 'name="password"' in html
        assert 'name="role"' in html
        assert 'name="account_status"' in html

    def test_post_user_create_success_htmx_and_validations(self, user_factory):
        from apps.accounts.models import CustomUser
        from apps.admin_panel.models import AuditLog
        from apps.contacts.models import ContactBook
        from apps.favorites.models import FavoriteList

        admin_user = user_factory(
            username="admin_c_post", email="admincpost@example.com", role="Admin", is_staff=True
        )
        client = Client()
        client.force_login(admin_user)

        # Successful standard POST
        post_data = {
            "username": "new_person",
            "email": "person@example.com",
            "full_name": "New Person",
            "password": "ValidPass123!",
            "role": "User",
            "account_status": "Active",
        }
        resp = client.post("/admin-panel/users/create/", post_data)
        assert resp.status_code == 302
        new_user = CustomUser.objects.get(username="new_person")
        assert resp.url == f"/admin-panel/users/{new_user.pk}/"
        assert new_user.email == "person@example.com"
        assert new_user.role == "User"
        assert new_user.account_status == "Active"
        assert ContactBook.objects.filter(user=new_user).exists()
        assert FavoriteList.objects.filter(book__user=new_user).exists()

        log = AuditLog.objects.get(target_user=new_user, action="USER_CREATED")
        assert log.actor == admin_user
        assert log.actor_username_snapshot == "admin_c_post"

        # HTMX creation
        htmx_data = {
            "username": "htmx_person",
            "email": "htmxperson@example.com",
            "full_name": "HTMX Person",
            "password": "ValidPass123!",
            "role": "Admin",
            "account_status": "Active",
        }
        htmx_resp = client.post("/admin-panel/users/create/", htmx_data, HTTP_HX_REQUEST="true")
        assert htmx_resp.status_code == 200
        htmx_user = CustomUser.objects.get(username="htmx_person")
        assert htmx_resp["HX-Redirect"] == f"/admin-panel/users/{htmx_user.pk}/"
        assert htmx_user.role == "Admin"
        assert htmx_user.is_staff is True

        # Duplicate username validation -> 400
        dup_user_resp = client.post(
            "/admin-panel/users/create/",
            {**post_data, "email": "unique@example.com"},
        )
        assert dup_user_resp.status_code == 400
        assert b"This username is already taken" in dup_user_resp.content

        # Duplicate email validation -> 400
        dup_email_resp = client.post(
            "/admin-panel/users/create/",
            {**post_data, "username": "other_unique"},
        )
        assert dup_email_resp.status_code == 400
        assert b"An account with this email address already exists" in dup_email_resp.content

        # Weak password validation (< 8 chars) -> 400
        weak_resp = client.post(
            "/admin-panel/users/create/",
            {
                **post_data,
                "username": "weak_user",
                "email": "weak@example.com",
                "password": "weak",
            },
        )
        assert weak_resp.status_code == 400
        assert b"at least 8 characters" in weak_resp.content


@pytest.mark.django_db
class TestAdminUserEditContract:
    """Contract tests for GET and POST /admin-panel/users/<id>/edit/."""

    def test_get_user_edit_renders_form_with_user_data(self, user_factory):
        admin_user = user_factory(
            username="admin_e_get", email="admineget@example.com", role="Admin", is_staff=True
        )
        target = user_factory(
            username="target_edit", email="targetedit@example.com", full_name="Target Edit"
        )
        client = Client()
        client.force_login(admin_user)

        resp = client.get(f"/admin-panel/users/{target.pk}/edit/")
        assert resp.status_code == 200
        html = resp.content.decode("utf-8")
        assert "target_edit" in html
        assert "targetedit@example.com" in html
        assert "Target Edit" in html

        # 404 on nonexistent user
        assert client.get("/admin-panel/users/999999/edit/").status_code == 404

    def test_post_user_edit_updates_fields_and_validates_self_protection(self, user_factory):
        from apps.admin_panel.models import AuditLog

        admin_user = user_factory(
            username="admin_e_post", email="adminepost@example.com", role="Admin", is_staff=True
        )
        target = user_factory(
            username="target_e_post", email="targetepost@example.com", full_name="Old Name"
        )
        client = Client()
        client.force_login(admin_user)

        # Successful update of target user
        edit_data = {
            "full_name": "New Full Name",
            "email": "newtarget@example.com",
            "role": "Admin",
            "account_status": "Active",
            "new_password": "NewValidPass123!",
        }
        resp = client.post(f"/admin-panel/users/{target.pk}/edit/", edit_data)
        assert resp.status_code == 302
        assert resp.url == f"/admin-panel/users/{target.pk}/"

        target.refresh_from_db()
        assert target.full_name == "New Full Name"
        assert target.email == "newtarget@example.com"
        assert target.role == "Admin"
        assert target.is_staff is True
        assert target.check_password("NewValidPass123!")

        log = AuditLog.objects.get(target_user=target, action="USER_UPDATED")
        assert log.actor == admin_user
        assert "full_name" in log.details

        # Self-demotion protection -> 400
        self_demote_resp = client.post(
            f"/admin-panel/users/{admin_user.pk}/edit/",
            {
                "full_name": admin_user.full_name,
                "email": admin_user.email,
                "role": "User",
                "account_status": "Active",
            },
        )
        assert self_demote_resp.status_code == 400
        assert b"You cannot remove your own administrative role" in self_demote_resp.content

        # Self-lockout protection -> 400
        self_lock_resp = client.post(
            f"/admin-panel/users/{admin_user.pk}/edit/",
            {
                "full_name": admin_user.full_name,
                "email": admin_user.email,
                "role": "Admin",
                "account_status": "Locked",
            },
        )
        assert self_lock_resp.status_code == 400
        assert b"You cannot lock your own administrative account" in self_lock_resp.content

        # Duplicate email belonging to someone else -> 400
        user_factory(username="other_e", email="othere@example.com")
        dup_email_resp = client.post(
            f"/admin-panel/users/{target.pk}/edit/",
            {
                "full_name": target.full_name,
                "email": "othere@example.com",
                "role": "User",
                "account_status": "Active",
            },
        )
        assert dup_email_resp.status_code == 400
        assert b"already registered to another account" in dup_email_resp.content


@pytest.mark.django_db
class TestAdminUserDeleteContract:
    """Contract tests for POST /admin-panel/users/<id>/delete/."""

    def test_post_user_delete_requires_confirm_and_protects_self(self, user_factory):
        from apps.accounts.models import CustomUser
        from apps.admin_panel.models import AuditLog

        admin_user = user_factory(
            username="admin_d_post", email="admindpost@example.com", role="Admin", is_staff=True
        )
        target = user_factory(username="target_d_post", email="targetdpost@example.com")
        client = Client()
        client.force_login(admin_user)

        # Missing confirm=true -> 400
        unconfirmed = client.post(f"/admin-panel/users/{target.pk}/delete/", {})
        assert unconfirmed.status_code == 400
        assert b"Deletion confirmation is required" in unconfirmed.content
        assert CustomUser.objects.filter(pk=target.pk).exists()

        # Self-delete attempt -> 400 ERR_ADMIN_SELF_DELETE
        self_del = client.post(
            f"/admin-panel/users/{admin_user.pk}/delete/",
            {"confirm": "true"},
        )
        assert self_del.status_code == 400
        assert b"You cannot delete your own administrative account" in self_del.content
        assert CustomUser.objects.filter(pk=admin_user.pk).exists()

        # Successful standard POST delete with confirm=true -> 302 to user_list
        target_id = target.pk
        target_username = target.username
        resp = client.post(
            f"/admin-panel/users/{target_id}/delete/",
            {"confirm": "true"},
        )
        assert resp.status_code == 302
        assert resp.url == "/admin-panel/users/"
        assert not CustomUser.objects.filter(pk=target_id).exists()

        log = AuditLog.objects.get(action="USER_DELETED", target_username_snapshot=target_username)
        assert log.actor == admin_user
        assert log.target_user is None
        assert log.details["deleted_user_id"] == target_id

        # HTMX delete
        target_htmx = user_factory(username="target_htmx_del", email="targethtmxdel@example.com")
        htmx_resp = client.post(
            f"/admin-panel/users/{target_htmx.pk}/delete/",
            {"confirm": "true"},
            HTTP_HX_REQUEST="true",
        )
        assert htmx_resp.status_code == 200
        assert htmx_resp["HX-Redirect"] == "/admin-panel/users/"
        assert not CustomUser.objects.filter(pk=target_htmx.pk).exists()

        # Nonexistent user -> 404
        assert (
            client.post("/admin-panel/users/999999/delete/", {"confirm": "true"}).status_code == 404
        )
