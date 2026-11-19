"""Integration tests for User Story 1: Authentication & Account Lifecycle (T018)."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client


@pytest.mark.django_db
class TestAuthLifecycleIntegration:
    """End-to-end integration tests covering US1 Acceptance Scenarios 1-7."""

    def test_full_account_lifecycle_journey(self, client):
        from apps.contacts.models import ContactBook
        from apps.favorites.models import FavoriteList

        # 1. Register a new account (US1.1)
        reg_resp = client.post(
            "/accounts/register/",
            {
                "username": "jane_smith",
                "email": "Jane.Smith@Example.COM",
                "full_name": "Jane Smith",
                "password": "StrongPassword123!",
                "password_confirm": "StrongPassword123!",
            },
        )
        assert reg_resp.status_code == 302
        assert reg_resp.url == "/accounts/login/"

        user_model = get_user_model()
        user = user_model.objects.get(username="jane_smith")
        assert ContactBook.objects.filter(user=user).count() == 1
        assert FavoriteList.objects.filter(book__user=user).count() == 1

        # 2. Duplicate registration rejected without altering original record (US1.2, EC-009)
        dup_resp = client.post(
            "/accounts/register/",
            {
                "username": "other_jane",
                "email": "jane.smith@example.com",
                "full_name": "Impostor Jane",
                "password": "StrongPassword123!",
                "password_confirm": "StrongPassword123!",
            },
        )
        assert dup_resp.status_code == 400
        user.refresh_from_db()
        assert user.full_name == "Jane Smith"

        # 3. Login with email & password (US1.3)
        login_resp = client.post(
            "/accounts/login/",
            {"username_or_email": "jane.smith@example.com", "password": "StrongPassword123!"},
        )
        assert login_resp.status_code == 302
        assert login_resp.url == "/contacts/"

        # 4. View and update profile (US1.5)
        profile_get = client.get("/accounts/profile/")
        assert profile_get.status_code == 200
        assert b"jane_smith" in profile_get.content

        profile_post = client.post(
            "/accounts/profile/",
            {"full_name": "Jane M. Smith", "email": "jane.m.smith@example.com"},
        )
        assert profile_post.status_code == 302
        user.refresh_from_db()
        assert user.full_name == "Jane M. Smith"
        assert user.email == "jane.m.smith@example.com"

        # 5. Change password (US1.6)
        pw_resp = client.post(
            "/accounts/password/change/",
            {
                "current_password": "StrongPassword123!",
                "new_password": "RotatedPassword789!",
                "new_password_confirm": "RotatedPassword789!",
            },
        )
        assert pw_resp.status_code == 302
        assert pw_resp.url == "/accounts/profile/"

        # 6. Logout & verify session revoked (US1.7)
        logout_resp = client.post("/accounts/logout/")
        assert logout_resp.status_code == 302
        assert logout_resp.url == "/accounts/login/"

        protected_resp = client.get("/accounts/profile/")
        assert protected_resp.status_code == 302
        assert protected_resp.url.startswith("/accounts/login/")

        # 7. Old password fails, new password succeeds
        old_pw_login = client.post(
            "/accounts/login/",
            {"username_or_email": "jane_smith", "password": "StrongPassword123!"},
        )
        assert old_pw_login.status_code == 401

        new_pw_login = client.post(
            "/accounts/login/",
            {"username_or_email": "jane_smith", "password": "RotatedPassword789!"},
        )
        assert new_pw_login.status_code == 302
        assert new_pw_login.url == "/contacts/"

    def test_password_change_evicts_other_concurrent_sessions(self, user_factory):
        """US1.6: Changing password maintains current session and terminates other sessions."""
        user_factory(username="multi_dev", email="multi@example.com", password="Password123!")

        client_a = Client()
        client_b = Client()

        assert (
            client_a.post(
                "/accounts/login/",
                {"username_or_email": "multi_dev", "password": "Password123!"},
            ).status_code
            == 302
        )
        assert (
            client_b.post(
                "/accounts/login/",
                {"username_or_email": "multi_dev", "password": "Password123!"},
            ).status_code
            == 302
        )

        session_b_key = client_b.session.session_key
        assert Session.objects.filter(session_key=session_b_key).exists()

        pw_resp = client_a.post(
            "/accounts/password/change/",
            {
                "current_password": "Password123!",
                "new_password": "NewPassword456!",
                "new_password_confirm": "NewPassword456!",
            },
        )
        assert pw_resp.status_code == 302

        # Client A remains authenticated
        assert client_a.get("/accounts/profile/").status_code == 200
        # Client B's session was evicted and redirected to login
        assert not Session.objects.filter(session_key=session_b_key).exists()
        resp_b = client_b.get("/accounts/profile/")
        assert resp_b.status_code == 302
        assert resp_b.url.startswith("/accounts/login/")

    def test_locked_account_cannot_login_and_existing_session_evicted(self, user_factory):
        """US1.4 & EC-005: Active session is immediately evicted when account becomes Locked."""
        user = user_factory(
            username="lock_target", email="lock@example.com", password="Password123!"
        )
        client = Client()

        login_resp = client.post(
            "/accounts/login/",
            {"username_or_email": "lock_target", "password": "Password123!"},
        )
        assert login_resp.status_code == 302
        assert client.get("/accounts/profile/").status_code == 200

        # Admin locks account
        user.account_status = "Locked"
        user.save(update_fields=["account_status", "updated_at"])

        # AccountLockMiddleware immediately flushes session and redirects to login
        session_key = client.session.session_key
        assert Session.objects.filter(session_key=session_key).exists()
        evicted_resp = client.get("/accounts/profile/")
        assert evicted_resp.status_code == 302
        assert evicted_resp.url == "/accounts/login/"
        assert not Session.objects.filter(session_key=session_key).exists()

        # Redirect target renders locked flash message via real Session/MessageMiddleware
        login_page = client.get("/accounts/login/")
        assert login_page.status_code == 200
        assert (
            b"This account is locked. Please contact the system administrator."
            in login_page.content
        )

        # Subsequent login attempts fail with 403
        retry_resp = client.post(
            "/accounts/login/",
            {"username_or_email": "lock_target", "password": "Password123!"},
        )
        assert retry_resp.status_code == 403
        assert (
            b"This account is locked. Please contact the system administrator."
            in retry_resp.content
        )

    def test_inactive_user_and_htmx_session_eviction_render_locked_flash_via_real_session(
        self, user_factory
    ):
        """M3: Real SessionMiddleware eviction for is_active=False and HTMX HX-Redirect."""
        user = user_factory(
            username="inactive_target", email="inactive@example.com", password="Password123!"
        )
        client = Client()
        assert (
            client.post(
                "/accounts/login/",
                {"username_or_email": "inactive_target", "password": "Password123!"},
            ).status_code
            == 302
        )
        session_key = client.session.session_key
        assert Session.objects.filter(session_key=session_key).exists()

        user.is_active = False
        user.save(update_fields=["is_active", "updated_at"])

        htmx_evicted = client.get("/contacts/search/", HTTP_HX_REQUEST="true")
        assert htmx_evicted.status_code == 200
        assert htmx_evicted.headers.get("HX-Redirect") == "/accounts/login/"
        assert not Session.objects.filter(session_key=session_key).exists()

        login_after_htmx = client.get("/accounts/login/")
        assert login_after_htmx.status_code == 200
        assert (
            b"This account is locked. Please contact the system administrator."
            in login_after_htmx.content
        )

    def test_csrf_protection_enforced_on_auth_post_endpoints(self):
        """Constitution IV: POST requests without CSRF token are rejected with 403."""
        csrf_client = Client(enforce_csrf_checks=True)
        resp = csrf_client.post(
            "/accounts/login/",
            {"username_or_email": "any", "password": "Password123!"},
        )
        assert resp.status_code == 403
