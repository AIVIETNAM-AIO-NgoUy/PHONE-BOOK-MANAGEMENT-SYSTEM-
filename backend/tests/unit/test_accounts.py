"""Unit tests for CustomUser, ContactBook, FavoriteList, forms, and auth services (T030)."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction

from apps.accounts import services
from apps.accounts.forms import LoginForm, PasswordChangeForm, ProfileUpdateForm, RegisterForm
from apps.accounts.models import CustomUser
from apps.contacts.models import ContactBook
from apps.favorites.models import FavoriteList

VALID_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x00IEND\xaeB`\x82"
)
VALID_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
VALID_WEBP = b"RIFF\x18\x00\x00\x00WEBP" + b"\x00" * 16


@pytest.mark.django_db
class TestCustomUserModel:
    """Unit tests for CustomUser manager, constraints, and Argon2 hashing."""

    def test_create_user_hashes_password_with_argon2_and_normalizes_email(self):
        user = CustomUser.objects.create_user(
            username="  dev_user ",
            email="Dev.User@Example.COM ",
            password="StrongPassword123!",
            full_name="Dev User",
        )
        assert user.username == "dev_user"
        assert user.email == "dev.user@example.com"
        assert user.password.startswith("argon2")
        assert user.check_password("StrongPassword123!")
        assert user.role == CustomUser.Role.USER
        assert user.account_status == CustomUser.AccountStatus.ACTIVE
        assert not user.is_admin
        assert not user.is_staff
        assert not user.is_superuser
        assert str(user) == "dev_user (User)"

    def test_create_user_requires_username_and_email(self):
        with pytest.raises(ValueError, match="username"):
            CustomUser.objects.create_user(username="  ", email="a@b.com", password="Password123!")
        with pytest.raises(ValueError, match="email"):
            CustomUser.objects.create_user(username="valid_u", email="", password="Password123!")

    def test_create_superuser_sets_admin_role_and_flags(self):
        admin = CustomUser.objects.create_superuser(
            username="sysadmin",
            email="Admin@Example.COM",
            password="AdminPassword123!",
            full_name="System Admin",
        )
        assert admin.role == CustomUser.Role.ADMIN
        assert admin.is_admin is True
        assert admin.is_staff is True
        assert admin.is_superuser is True
        assert admin.email == "admin@example.com"

        with pytest.raises(ValueError, match="is_staff"):
            CustomUser.objects.create_superuser(
                username="bad1", email="bad1@example.com", password="x", is_staff=False
            )
        with pytest.raises(ValueError, match="is_superuser"):
            CustomUser.objects.create_superuser(
                username="bad2", email="bad2@example.com", password="x", is_superuser=False
            )
        with pytest.raises(ValueError, match="role='Admin'"):
            CustomUser.objects.create_superuser(
                username="bad3", email="bad3@example.com", password="x", role="User"
            )

    def test_create_user_and_superuser_bootstrap_contactbook_and_favoritelist(self):
        standard_user = CustomUser.objects.create_user(
            username="boot_std",
            email="bootstd@example.com",
            password="Password123!",
        )
        admin_user = CustomUser.objects.create_superuser(
            username="boot_adm",
            email="bootadm@example.com",
            password="Password123!",
        )
        for account in (standard_user, admin_user):
            book = ContactBook.objects.get(user=account)
            assert FavoriteList.objects.filter(book=book).exists()

    def test_case_insensitive_uniqueness_and_check_constraints(self):
        CustomUser.objects.create_user(
            username="CaseUser",
            email="case@example.com",
            password="Password123!",
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                CustomUser.objects.create_user(
                    username="caseuser",
                    email="other@example.com",
                    password="Password123!",
                )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                CustomUser.objects.create_user(
                    username="other_user",
                    email="CASE@EXAMPLE.COM",
                    password="Password123!",
                )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                CustomUser.objects.create(
                    username="bad_role",
                    email="badrole@example.com",
                    password="hash",
                    role="SuperAdmin",
                )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                CustomUser.objects.create(
                    username="bad_status",
                    email="badstatus@example.com",
                    password="hash",
                    account_status="Suspended",
                )

    def test_user_deletion_cascades_to_contactbook_and_favoritelist(self, user_factory):
        user = user_factory(username="cascade_u", email="cascade@example.com")
        assert ContactBook.objects.filter(user=user).exists()
        assert FavoriteList.objects.filter(book=user.contact_book).exists()
        assert str(user.contact_book) == f"ContactBook(user={user.pk})"
        assert str(user.contact_book.favorite_list) == f"FavoriteList(book={user.contact_book.pk})"

        user.delete()
        assert ContactBook.objects.count() == 0
        assert FavoriteList.objects.count() == 0


@pytest.mark.django_db
class TestAccountForms:
    """Unit tests for RegisterForm, LoginForm, ProfileUpdateForm, and PasswordChangeForm."""

    def test_register_form_validates_username_full_name_and_password_rules(self):
        invalid_username = RegisterForm(
            data={
                "username": "ab",
                "email": "u@example.com",
                "full_name": "Valid Name",
                "password": "StrongPassword123!",
                "password_confirm": "StrongPassword123!",
            }
        )
        assert not invalid_username.is_valid()
        assert "username" in invalid_username.errors

        blank_name = RegisterForm(
            data={
                "username": "valid_user",
                "email": "u@example.com",
                "full_name": "   ",
                "password": "StrongPassword123!",
                "password_confirm": "StrongPassword123!",
            }
        )
        assert not blank_name.is_valid()
        assert "full_name" in blank_name.errors

        numeric_pw = RegisterForm(
            data={
                "username": "valid_user",
                "email": "u@example.com",
                "full_name": "Valid Name",
                "password": "123456789",
                "password_confirm": "123456789",
            }
        )
        assert not numeric_pw.is_valid()
        assert "password" in numeric_pw.errors

        common_pw = RegisterForm(
            data={
                "username": "valid_user",
                "email": "u@example.com",
                "full_name": "Valid Name",
                "password": "password1",
                "password_confirm": "password1",
            }
        )
        assert not common_pw.is_valid()
        assert "password" in common_pw.errors

    def test_login_form_rejects_whitespace_identifier(self):
        form = LoginForm(data={"username_or_email": "   ", "password": "Password123!"})
        assert not form.is_valid()
        assert "username_or_email" in form.errors

    def test_profile_update_form_avatar_size_extension_and_magic_bytes(self, user_factory):
        user = user_factory(username="img_user", email="img@example.com", full_name="Img User")
        user_factory(username="other_img", email="taken@example.com")

        # Allows keeping own email regardless of casing
        keep_email_form = ProfileUpdateForm(
            user=user,
            data={"full_name": "Img User Updated", "email": "IMG@EXAMPLE.COM"},
        )
        assert keep_email_form.is_valid()
        assert keep_email_form.cleaned_data["email"] == "img@example.com"

        # Rejects blank full_name
        blank_name_form = ProfileUpdateForm(
            user=user,
            data={"full_name": "   ", "email": "img@example.com"},
        )
        assert not blank_name_form.is_valid()
        assert "full_name" in blank_name_form.errors

        # Rejects email owned by someone else
        dup_email_form = ProfileUpdateForm(
            user=user,
            data={"full_name": "Img User", "email": "TAKEN@example.com"},
        )
        assert not dup_email_form.is_valid()
        assert "email" in dup_email_form.errors

        # Rejects > 2MB file
        oversized = SimpleUploadedFile(
            "big.png",
            VALID_PNG + (b"\x00" * (2 * 1024 * 1024 + 10)),
            content_type="image/png",
        )
        oversized_form = ProfileUpdateForm(
            user=user,
            data={"full_name": "Img User", "email": "img@example.com"},
            files={"avatar": oversized},
        )
        assert not oversized_form.is_valid()
        assert "avatar" in oversized_form.errors

        # Rejects unsupported extension
        bad_ext = SimpleUploadedFile("anim.gif", b"GIF89a...", content_type="image/gif")
        bad_ext_form = ProfileUpdateForm(
            user=user,
            data={"full_name": "Img User", "email": "img@example.com"},
            files={"avatar": bad_ext},
        )
        assert not bad_ext_form.is_valid()
        assert "avatar" in bad_ext_form.errors

        # Rejects forged header bytes
        forged = SimpleUploadedFile("fake.jpg", b"NOTAJPEGFILE", content_type="image/jpeg")
        forged_form = ProfileUpdateForm(
            user=user,
            data={"full_name": "Img User", "email": "img@example.com"},
            files={"avatar": forged},
        )
        assert not forged_form.is_valid()
        assert "avatar" in forged_form.errors

        # Accepts valid PNG, JPEG, and WEBP
        for filename, content, ctype in [
            ("a.png", VALID_PNG, "image/png"),
            ("b.jpg", VALID_JPEG, "image/jpeg"),
            ("c.webp", VALID_WEBP, "image/webp"),
        ]:
            valid_upload = SimpleUploadedFile(filename, content, content_type=ctype)
            valid_form = ProfileUpdateForm(
                user=user,
                data={"full_name": "Img User", "email": "img@example.com"},
                files={"avatar": valid_upload},
            )
            assert valid_form.is_valid(), f"Expected {filename} to be valid: {valid_form.errors}"

        # Supports clearing existing avatar via avatar-clear
        user.avatar_url = "/media/avatars/existing.png"
        user.save(update_fields=["avatar_url"])
        clear_form = ProfileUpdateForm(
            user=user,
            data={"full_name": "Img User", "email": "img@example.com", "avatar-clear": "on"},
        )
        assert clear_form.is_valid()
        assert clear_form.cleaned_data["avatar"] is False

        # Keeping existing avatar when no new upload and clear unchecked returns None
        keep_avatar_form = ProfileUpdateForm(
            user=user,
            data={"full_name": "Img User", "email": "img@example.com"},
        )
        assert keep_avatar_form.is_valid()
        assert keep_avatar_form.cleaned_data["avatar"] is None

    def test_password_change_form_validations(self, user_factory):
        user = user_factory(username="pw_unit", email="pwunit@example.com", password="OldPass123!")

        weak_new = PasswordChangeForm(
            user=user,
            data={
                "current_password": "OldPass123!",
                "new_password": "short",
                "new_password_confirm": "short",
            },
        )
        assert not weak_new.is_valid()
        assert "new_password" in weak_new.errors


@pytest.mark.django_db
class TestAccountServices:
    """Unit tests for register_user atomicity, authenticate_account, and flush_user_sessions."""

    def test_register_user_rolls_back_on_partial_failure(self):
        user_model = get_user_model()
        with patch(
            "apps.accounts.services.FavoriteList.objects.create",
            side_effect=RuntimeError("Simulated DB failure"),
        ):
            with pytest.raises(RuntimeError, match="Simulated DB failure"):
                services.register_user(
                    username="atomic_fail",
                    email="atomic@example.com",
                    full_name="Atomic Fail",
                    password="StrongPassword123!",
                )

        assert not user_model.objects.filter(username="atomic_fail").exists()
        assert ContactBook.objects.count() == 0
        assert FavoriteList.objects.count() == 0

    def test_authenticate_account_distinguishes_invalid_creds_and_locked_status(self, user_factory):
        active_user = user_factory(
            username="svc_active", email="svcactive@example.com", password="Password123!"
        )
        locked_user = user_factory(
            username="svc_locked",
            email="svclocked@example.com",
            password="Password123!",
            account_status="Locked",
        )

        assert services.authenticate_account("SVC_ACTIVE", "Password123!") == active_user
        assert services.authenticate_account("SvcActive@Example.com", "Password123!") == active_user

        with pytest.raises(services.InvalidCredentialsError):
            services.authenticate_account("", "Password123!")
        with pytest.raises(services.InvalidCredentialsError):
            services.authenticate_account("nonexistent", "Password123!")
        with pytest.raises(services.InvalidCredentialsError):
            services.authenticate_account("svc_locked", "WrongPassword!")
        with pytest.raises(services.AccountLockedError):
            services.authenticate_account(locked_user.username, "Password123!")

    def test_flush_user_sessions_evicts_only_target_user_sessions(self, user_factory):
        user_a = user_factory(username="sess_a", email="sessa@example.com")
        user_b = user_factory(username="sess_b", email="sessb@example.com")

        s_a1 = SessionStore()
        s_a1["_auth_user_id"] = str(user_a.pk)
        s_a1.create()

        s_a2 = SessionStore()
        s_a2["_auth_user_id"] = str(user_a.pk)
        s_a2.create()

        s_b = SessionStore()
        s_b["_auth_user_id"] = str(user_b.pk)
        s_b.create()

        # Exclude s_a1 first
        deleted = services.flush_user_sessions(user_a, exclude_session_key=s_a1.session_key)
        assert deleted == 1
        assert Session.objects.filter(session_key=s_a1.session_key).exists()
        assert not Session.objects.filter(session_key=s_a2.session_key).exists()
        assert Session.objects.filter(session_key=s_b.session_key).exists()

        # Flush remaining session of user_a
        deleted_all = services.flush_user_sessions(user_a)
        assert deleted_all == 1
        assert not Session.objects.filter(session_key=s_a1.session_key).exists()
        assert Session.objects.filter(session_key=s_b.session_key).exists()

        # Calling again when none remain returns 0 cleanly
        assert services.flush_user_sessions(user_a) == 0
