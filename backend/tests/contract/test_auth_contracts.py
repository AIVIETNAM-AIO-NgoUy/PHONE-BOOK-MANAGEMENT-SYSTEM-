"""Contract tests for authentication and account lifecycle endpoints (T017)."""

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import override_settings

VALID_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\x00\x00"
    b"\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.django_db
class TestRegisterContract:
    """Contract tests for GET/POST /accounts/register/ (auth-contracts.md 2.1)."""

    def test_get_register_anonymous_returns_200(self, client):
        response = client.get("/accounts/register/")
        assert response.status_code == 200
        assert b"username" in response.content

    def test_get_register_authenticated_redirects_to_dashboard(self, authenticated_client):
        client, _ = authenticated_client()
        response = client.get("/accounts/register/")
        assert response.status_code == 302
        assert response.url == "/contacts/"

    def test_post_register_success_creates_user_book_and_favoritelist(self, client):
        from apps.contacts.models import ContactBook
        from apps.favorites.models import FavoriteList

        payload = {
            "username": "john_doe",
            "email": "John.Doe@Example.COM",
            "full_name": "  John Doe  ",
            "password": "Password123!",
            "password_confirm": "Password123!",
        }
        response = client.post("/accounts/register/", payload)
        assert response.status_code == 302
        assert response.url == "/accounts/login/"

        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        assert "Registration successful. Please log in." in msgs

        user_model = get_user_model()
        user = user_model.objects.get(username="john_doe")
        assert user.email == "john.doe@example.com"
        assert user.full_name == "John Doe"
        assert user.password.startswith("argon2")
        assert user.role == "User"
        assert user.account_status == "Active"
        assert ContactBook.objects.filter(user=user).exists()
        assert FavoriteList.objects.filter(book=user.contact_book).exists()

    def test_post_register_duplicate_username_returns_400(self, client, user_factory):
        user_factory(username="john_doe", email="existing@example.com")
        response = client.post(
            "/accounts/register/",
            {
                "username": "John_Doe",
                "email": "new@example.com",
                "full_name": "Another John",
                "password": "Password123!",
                "password_confirm": "Password123!",
            },
        )
        assert response.status_code == 400
        assert b"This username is already taken. Please choose another." in response.content

    def test_post_register_duplicate_email_case_insensitive_returns_400(self, client, user_factory):
        user_factory(username="existing_user", email="john@example.com")
        response = client.post(
            "/accounts/register/",
            {
                "username": "new_user",
                "email": "John@Example.com",
                "full_name": "New User",
                "password": "Password123!",
                "password_confirm": "Password123!",
            },
        )
        assert response.status_code == 400
        assert b"An account with this email address already exists." in response.content

    def test_post_register_password_mismatch_returns_400(self, client):
        response = client.post(
            "/accounts/register/",
            {
                "username": "mismatch_user",
                "email": "mismatch@example.com",
                "full_name": "Mismatch User",
                "password": "Password123!",
                "password_confirm": "Different123!",
            },
        )
        assert response.status_code == 400
        assert b"Passwords do not match." in response.content

    def test_post_register_weak_password_returns_400(self, client):
        response = client.post(
            "/accounts/register/",
            {
                "username": "weak_user",
                "email": "weak@example.com",
                "full_name": "Weak User",
                "password": "onlyletters",
                "password_confirm": "onlyletters",
            },
        )
        assert response.status_code == 400
        assert (
            b"Password must be at least 8 characters long and contain letters and numbers."
            in response.content
        )

    def test_post_register_race_integrity_error_returns_400_not_500(self, client):
        with patch(
            "apps.accounts.views.services.register_user",
            side_effect=IntegrityError('duplicate key violates "uq_users_email_lower"'),
        ):
            resp_email = client.post(
                "/accounts/register/",
                {
                    "username": "race_user_1",
                    "email": "race@example.com",
                    "full_name": "Race User",
                    "password": "Password123!",
                    "password_confirm": "Password123!",
                },
            )
        assert resp_email.status_code == 400
        assert b"An account with this email address already exists." in resp_email.content

        with patch(
            "apps.accounts.views.services.register_user",
            side_effect=IntegrityError('duplicate key violates "uq_users_username_lower"'),
        ):
            resp_user = client.post(
                "/accounts/register/",
                {
                    "username": "race_user_2",
                    "email": "race2@example.com",
                    "full_name": "Race User",
                    "password": "Password123!",
                    "password_confirm": "Password123!",
                },
            )
        assert resp_user.status_code == 400
        assert b"This username is already taken. Please choose another." in resp_user.content


@pytest.mark.django_db
class TestLoginLogoutContract:
    """Contract tests for /accounts/login/ and /accounts/logout/ (auth-contracts.md 2.2 & 2.3)."""

    def test_login_with_username_and_email_succeeds(self, client, user_factory):
        user_factory(username="alice_dev", email="alice@example.com", password="Password123!")

        resp_username = client.post(
            "/accounts/login/",
            {"username_or_email": "ALICE_DEV", "password": "Password123!"},
        )
        assert resp_username.status_code == 302
        assert resp_username.url == "/contacts/"
        assert client.session.get_expire_at_browser_close() is True

        client.logout()

        resp_email = client.post(
            "/accounts/login/",
            {
                "username_or_email": "Alice@Example.com",
                "password": "Password123!",
                "remember_me": "on",
            },
        )
        assert resp_email.status_code == 302
        assert resp_email.url == "/contacts/"
        assert client.session.get_expiry_age() == 1209600

    def test_login_respects_safe_next_and_ignores_unsafe_next(self, client, user_factory):
        user_factory(username="next_user", email="next@example.com", password="Password123!")

        resp_safe = client.post(
            "/accounts/login/?next=%20/accounts/profile/%20",
            {"username_or_email": "next_user", "password": "Password123!"},
        )
        assert resp_safe.status_code == 302
        assert resp_safe.url == "/accounts/profile/"

        client.logout()

        resp_unsafe = client.post(
            "/accounts/login/?next=https://evil.example.com/phish",
            {"username_or_email": "next_user", "password": "Password123!"},
        )
        assert resp_unsafe.status_code == 302
        assert resp_unsafe.url == "/contacts/"

    def test_login_invalid_credentials_returns_401(self, client, user_factory):
        user_factory(username="bob_dev", email="bob@example.com", password="Password123!")
        response = client.post(
            "/accounts/login/",
            {"username_or_email": "bob_dev", "password": "WrongPassword123!"},
        )
        assert response.status_code == 401
        assert b"Invalid username/email or password." in response.content
        assert "_auth_user_id" not in client.session

    def test_login_locked_account_returns_403(self, client, user_factory):
        user_factory(
            username="locked_user",
            email="locked@example.com",
            password="Password123!",
            account_status="Locked",
        )
        response = client.post(
            "/accounts/login/",
            {"username_or_email": "locked_user", "password": "Password123!"},
        )
        assert response.status_code == 403
        assert (
            b"This account is locked. Please contact the system administrator." in response.content
        )
        assert "_auth_user_id" not in client.session

    def test_logout_requires_post_and_invalidates_session(self, authenticated_client):
        client, _ = authenticated_client()
        get_resp = client.get("/accounts/logout/")
        assert get_resp.status_code == 405

        post_resp = client.post("/accounts/logout/")
        assert post_resp.status_code == 302
        assert post_resp.url == "/accounts/login/"
        msgs = [str(m) for m in get_messages(post_resp.wsgi_request)]
        assert "You have been safely logged out." in msgs
        assert "_auth_user_id" not in client.session


@pytest.mark.django_db
class TestProfileContract:
    """Contract tests for GET/POST /accounts/profile/ (auth-contracts.md 2.4 & 2.5)."""

    def test_profile_requires_authentication(self, client):
        response = client.get("/accounts/profile/")
        assert response.status_code == 302
        assert response.url.startswith("/accounts/login/")

    def test_get_profile_renders_user_details(self, authenticated_client):
        client, user = authenticated_client(
            username="profile_viewer",
            email="viewer@example.com",
            full_name="Profile Viewer",
        )
        response = client.get("/accounts/profile/")
        assert response.status_code == 200
        assert b"profile_viewer" in response.content
        assert b"viewer@example.com" in response.content
        assert b"Profile Viewer" in response.content
        assert b"Active" in response.content

    def test_post_profile_updates_fields_and_redirects(self, authenticated_client):
        client, user = authenticated_client(
            username="updater",
            email="old@example.com",
            full_name="Old Name",
        )
        response = client.post(
            "/accounts/profile/",
            {"full_name": "New Name", "email": "NEW@Example.com"},
        )
        assert response.status_code == 302
        assert response.url == "/accounts/profile/"
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        assert "Profile updated successfully." in msgs

        user.refresh_from_db()
        assert user.full_name == "New Name"
        assert user.email == "new@example.com"

    def test_post_profile_htmx_returns_200_partial(self, authenticated_client):
        client, user = authenticated_client(
            username="htmx_user",
            email="htmx@example.com",
            full_name="Before HTMX",
        )
        response = client.post(
            "/accounts/profile/",
            {"full_name": "After HTMX", "email": "htmx@example.com"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        assert b"After HTMX" in response.content
        assert b"<!DOCTYPE html>" not in response.content

    def test_post_profile_duplicate_email_returns_400(self, authenticated_client, user_factory):
        user_factory(username="other_user", email="taken@example.com")
        client, user = authenticated_client(username="self_user", email="self@example.com")

        response = client.post(
            "/accounts/profile/",
            {"full_name": "Self User", "email": "TAKEN@example.com"},
        )
        assert response.status_code == 400
        assert b"This email address is already registered to another account." in response.content
        user.refresh_from_db()
        assert user.email == "self@example.com"

    def test_post_profile_valid_and_invalid_avatar(self, authenticated_client, tmp_path):
        client, user = authenticated_client(username="avatar_user", email="avatar@example.com")

        with override_settings(MEDIA_ROOT=tmp_path):
            bad_file = SimpleUploadedFile(
                "evil.png",
                b"not-actually-an-image",
                content_type="image/png",
            )
            bad_resp = client.post(
                "/accounts/profile/",
                {"full_name": "Avatar User", "email": "avatar@example.com", "avatar": bad_file},
            )
            assert bad_resp.status_code == 400
            assert b"Avatar file must be an image (PNG, JPG, WEBP) under 2MB." in bad_resp.content

            good_file = SimpleUploadedFile(
                "avatar.png",
                BytesIO(VALID_PNG_BYTES).getvalue(),
                content_type="image/png",
            )
            good_resp = client.post(
                "/accounts/profile/",
                {"full_name": "Avatar User", "email": "avatar@example.com", "avatar": good_file},
            )
            assert good_resp.status_code == 302
            user.refresh_from_db()
            assert user.avatar_url is not None
            assert user.avatar_url.startswith("/media/avatars/")

    def test_post_profile_avatar_replace_clear_and_integrity_error_cleanup(
        self, authenticated_client, tmp_path, django_capture_on_commit_callbacks
    ):
        client, user = authenticated_client(username="av_prof_u", email="avprof@example.com")

        with override_settings(MEDIA_ROOT=tmp_path):
            f1 = SimpleUploadedFile("one.png", VALID_PNG_BYTES, content_type="image/png")
            with django_capture_on_commit_callbacks(execute=True):
                r1 = client.post(
                    "/accounts/profile/",
                    {"full_name": "Avatar Prof", "email": "avprof@example.com", "avatar": f1},
                )
            assert r1.status_code == 302
            user.refresh_from_db()
            path1 = Path(tmp_path) / user.avatar_url.replace("/media/", "")
            assert path1.exists()

            # Concurrent IntegrityError on email cleans up newly uploaded file & returns 400
            f_race = SimpleUploadedFile("race.png", VALID_PNG_BYTES, content_type="image/png")
            with patch.object(
                type(user),
                "save",
                side_effect=IntegrityError('duplicate key violates "uq_users_email_lower"'),
            ):
                r_race = client.post(
                    "/accounts/profile/",
                    {"full_name": "Avatar Prof", "email": "avprof@example.com", "avatar": f_race},
                )
            assert r_race.status_code == 400
            assert b"This email address is already registered to another account." in r_race.content
            assert path1.exists()
            assert len(list((Path(tmp_path) / "avatars").iterdir())) == 1

            # Replace deletes path1 on commit
            f2 = SimpleUploadedFile("two.png", VALID_PNG_BYTES, content_type="image/png")
            with django_capture_on_commit_callbacks(execute=True):
                r2 = client.post(
                    "/accounts/profile/",
                    {"full_name": "Avatar Prof", "email": "avprof@example.com", "avatar": f2},
                )
            assert r2.status_code == 302
            user.refresh_from_db()
            path2 = Path(tmp_path) / user.avatar_url.replace("/media/", "")
            assert path2.exists()
            assert not path1.exists()

            # Clear via avatar-clear deletes path2 on commit
            with django_capture_on_commit_callbacks(execute=True):
                r_clear = client.post(
                    "/accounts/profile/",
                    {
                        "full_name": "Avatar Prof",
                        "email": "avprof@example.com",
                        "avatar-clear": "on",
                    },
                )
            assert r_clear.status_code == 302
            user.refresh_from_db()
            assert user.avatar_url is None
            assert not path2.exists()


@pytest.mark.django_db
class TestPasswordChangeContract:
    """Contract tests for GET/POST /accounts/password/change/ (auth-contracts.md 2.6)."""

    def test_password_change_success_rotates_hash_and_keeps_session(self, authenticated_client):
        client, user = authenticated_client(
            username="pw_user",
            email="pw@example.com",
            password="OldPassword123!",
        )
        response = client.post(
            "/accounts/password/change/",
            {
                "current_password": "OldPassword123!",
                "new_password": "NewPassword456!",
                "new_password_confirm": "NewPassword456!",
            },
        )
        assert response.status_code == 302
        assert response.url == "/accounts/profile/"
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        assert "Your password has been changed successfully." in msgs

        user.refresh_from_db()
        assert user.check_password("NewPassword456!")
        assert not user.check_password("OldPassword123!")

        profile_resp = client.get("/accounts/profile/")
        assert profile_resp.status_code == 200

    def test_password_change_wrong_current_password_returns_400(self, authenticated_client):
        client, user = authenticated_client(
            username="pw_wrong",
            email="pwwrong@example.com",
            password="OldPassword123!",
        )
        response = client.post(
            "/accounts/password/change/",
            {
                "current_password": "WrongOldPassword123!",
                "new_password": "NewPassword456!",
                "new_password_confirm": "NewPassword456!",
            },
        )
        assert response.status_code == 400
        assert b"The current password entered is incorrect." in response.content
        user.refresh_from_db()
        assert user.check_password("OldPassword123!")

    def test_password_change_mismatch_returns_400(self, authenticated_client):
        client, _ = authenticated_client(
            username="pw_mismatch",
            email="pwmismatch@example.com",
            password="OldPassword123!",
        )
        response = client.post(
            "/accounts/password/change/",
            {
                "current_password": "OldPassword123!",
                "new_password": "NewPassword456!",
                "new_password_confirm": "Mismatch789!",
            },
        )
        assert response.status_code == 400
        assert b"New passwords do not match." in response.content

    def test_password_change_same_as_current_returns_400(self, authenticated_client):
        client, _ = authenticated_client(
            username="pw_same",
            email="pwsame@example.com",
            password="OldPassword123!",
        )
        response = client.post(
            "/accounts/password/change/",
            {
                "current_password": "OldPassword123!",
                "new_password": "OldPassword123!",
                "new_password_confirm": "OldPassword123!",
            },
        )
        assert response.status_code == 400
        assert b"New password cannot be identical to current password." in response.content
