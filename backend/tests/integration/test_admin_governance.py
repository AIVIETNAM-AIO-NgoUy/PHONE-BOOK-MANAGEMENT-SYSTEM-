"""Integration and security tests for User Story 7: Administrative Governance (T089)."""

import pytest
from django.contrib.sessions.models import Session
from django.test import Client


@pytest.mark.django_db
class TestAdminGovernanceIntegration:
    """End-to-end tests covering RBAC, instant session eviction, masking, and privacy."""

    def test_standard_user_cannot_access_admin_panel_routes(self, user_factory):
        standard = user_factory(
            username="normal_gov",
            email="normalgov@example.com",
            role="User",
            is_staff=False,
        )
        client = Client()
        client.force_login(standard)

        assert client.get("/admin-panel/").status_code == 403
        assert client.get("/admin-panel/users/").status_code == 403
        assert client.get(f"/admin-panel/users/{standard.pk}/").status_code == 403
        assert client.post(f"/admin-panel/users/{standard.pk}/lock/", {}).status_code == 403
        assert client.post(f"/admin-panel/users/{standard.pk}/unlock/", {}).status_code == 403

    def test_locking_user_immediately_evicts_active_session_and_unlock_restores_login(
        self, user_factory
    ):
        admin_user = user_factory(
            username="gov_admin",
            email="govadmin@example.com",
            role="Admin",
            is_staff=True,
        )
        target_user = user_factory(
            username="victim_session",
            email="victimsession@example.com",
            password="TargetPass123!",
        )

        # Target user logs in and holds an active session
        target_client = Client()
        login_resp = target_client.post(
            "/accounts/login/",
            {"username_or_email": "victim_session", "password": "TargetPass123!"},
        )
        assert login_resp.status_code == 302
        assert login_resp.url == "/contacts/"
        target_session_key = target_client.session.session_key
        assert target_session_key is not None
        assert Session.objects.filter(session_key=target_session_key).exists()
        assert target_client.get("/contacts/").status_code == 200

        # Admin logs in and locks target user
        admin_client = Client()
        admin_client.force_login(admin_user)
        lock_resp = admin_client.post(
            f"/admin-panel/users/{target_user.pk}/lock/",
            {"reason": "Compromised credentials"},
        )
        assert lock_resp.status_code == 302

        # Target session has been flushed from django_session
        assert not Session.objects.filter(session_key=target_session_key).exists()

        # Target user's very next request is immediately evicted/redirected to login
        evicted_resp = target_client.get("/contacts/")
        assert evicted_resp.status_code == 302
        assert evicted_resp.url.startswith("/accounts/login/")

        # Subsequent login attempt fails with locked message
        relogin_resp = target_client.post(
            "/accounts/login/",
            {"username_or_email": "victim_session", "password": "TargetPass123!"},
        )
        assert relogin_resp.status_code == 403
        assert (
            b"This account is locked. Please contact the system administrator."
            in relogin_resp.content
        )

        # Admin unlocks user -> target user can log in again
        unlock_resp = admin_client.post(f"/admin-panel/users/{target_user.pk}/unlock/", {})
        assert unlock_resp.status_code == 302

        restored_login = target_client.post(
            "/accounts/login/",
            {"username_or_email": "victim_session", "password": "TargetPass123!"},
        )
        assert restored_login.status_code == 302
        assert restored_login.url == "/contacts/"
        assert target_client.get("/contacts/").status_code == 200

    def test_credential_masking_and_admin_privacy_isolation_in_admin_views(self, user_factory):
        from apps.contacts.models import Contact, PhoneNumber

        admin_user = user_factory(
            username="privacy_admin",
            email="privacyadmin@example.com",
            role="Admin",
            is_staff=True,
        )
        target_user = user_factory(
            username="private_owner",
            email="privateowner@example.com",
            password="SuperSecretPassword123!",
        )
        c1 = Contact.objects.create(
            book=target_user.contact_book,
            full_name="Confidential Contact Alpha",
            email="alpha.secret@private.org",
            notes="Top secret personal note",
        )
        PhoneNumber.objects.create(
            contact=c1,
            phone_number="0909876543",
            phone_type="Mobile",
            is_primary=True,
        )
        c2 = Contact.objects.create(
            book=target_user.contact_book,
            full_name="Confidential Contact Beta",
            email="beta.secret@private.org",
        )
        PhoneNumber.objects.create(
            contact=c2,
            phone_number="0901122334",
            phone_type="Work",
            is_primary=True,
        )

        # Target user also holds an active session
        target_client = Client()
        target_client.post(
            "/accounts/login/",
            {"username_or_email": "private_owner", "password": "SuperSecretPassword123!"},
        )
        target_session_key = target_client.session.session_key
        assert target_session_key

        admin_client = Client()
        admin_client.force_login(admin_user)

        list_resp = admin_client.get("/admin-panel/users/")
        assert list_resp.status_code == 200
        list_html = list_resp.content.decode("utf-8")
        assert target_user.password not in list_html
        assert target_session_key not in list_html
        assert "argon2" not in list_html
        assert "pbkdf2" not in list_html

        detail_resp = admin_client.get(f"/admin-panel/users/{target_user.pk}/")
        assert detail_resp.status_code == 200
        detail_html = detail_resp.content.decode("utf-8")

        # Aggregate count exposed, zero personal contact details or credentials
        assert detail_resp.context["target_user"].contact_count == 2
        assert target_user.password not in detail_html
        assert target_session_key not in detail_html
        assert "argon2" not in detail_html
        assert "pbkdf2" not in detail_html
        assert "Confidential Contact Alpha" not in detail_html
        assert "Confidential Contact Beta" not in detail_html
        assert "0909876543" not in detail_html
        assert "0901122334" not in detail_html
        assert "alpha.secret@private.org" not in detail_html
        assert "Top secret personal note" not in detail_html

    def test_admin_crud_lifecycle_and_session_eviction_on_delete_and_lock(self, user_factory):
        from apps.accounts.models import CustomUser
        from apps.contacts.models import Contact

        admin_user = user_factory(
            username="lifecycle_admin",
            email="lifecycleadmin@example.com",
            role="Admin",
            is_staff=True,
        )
        admin_client = Client()
        admin_client.force_login(admin_user)

        # 1. Admin creates user
        create_resp = admin_client.post(
            "/admin-panel/users/create/",
            {
                "username": "managed_user",
                "email": "managed@example.com",
                "full_name": "Managed User",
                "password": "InitialPass123!",
                "role": "User",
                "account_status": "Active",
            },
        )
        assert create_resp.status_code == 302
        user = CustomUser.objects.get(username="managed_user")

        # 2. User logs in and holds active session
        user_client = Client()
        u_login = user_client.post(
            "/accounts/login/",
            {"username_or_email": "managed_user", "password": "InitialPass123!"},
        )
        assert u_login.status_code == 302
        u_session = user_client.session.session_key
        assert u_session
        assert Session.objects.filter(session_key=u_session).exists()

        # User creates a contact
        Contact.objects.create(
            book=user.contact_book,
            full_name="Managed Friend",
            email="friend@example.com",
        )

        # 3. Admin edits user to Locked status -> session evicted
        edit_resp = admin_client.post(
            f"/admin-panel/users/{user.pk}/edit/",
            {
                "full_name": "Managed User Updated",
                "email": "managed@example.com",
                "role": "User",
                "account_status": "Locked",
            },
        )
        assert edit_resp.status_code == 302
        assert not Session.objects.filter(session_key=u_session).exists()

        # 4. Admin edits user to Active and rotates password
        reactivate_resp = admin_client.post(
            f"/admin-panel/users/{user.pk}/edit/",
            {
                "full_name": "Managed User Updated",
                "email": "managed@example.com",
                "role": "User",
                "account_status": "Active",
                "new_password": "RotatedPass123!",
            },
        )
        assert reactivate_resp.status_code == 302
        user.refresh_from_db()
        assert user.account_status == "Active"
        assert user.check_password("RotatedPass123!")

        # 5. User logs in with new password
        new_login = user_client.post(
            "/accounts/login/",
            {"username_or_email": "managed_user", "password": "RotatedPass123!"},
        )
        assert new_login.status_code == 302
        new_session = user_client.session.session_key
        assert Session.objects.filter(session_key=new_session).exists()

        # 6. Admin permanently deletes user with confirmation
        del_resp = admin_client.post(
            f"/admin-panel/users/{user.pk}/delete/",
            {"confirm": "true"},
        )
        assert del_resp.status_code == 302
        assert not CustomUser.objects.filter(pk=user.pk).exists()
        assert not Session.objects.filter(session_key=new_session).exists()
        assert not Contact.objects.filter(full_name="Managed Friend").exists()
