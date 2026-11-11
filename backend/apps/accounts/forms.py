"""Forms and input validators for authentication and account management."""

import re

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.accounts.models import CustomUser
from apps.core.utils import AvatarInitialRef, validate_image_upload

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,50}$")

ERR_AUTH_USERNAME_TAKEN = "This username is already taken. Please choose another."
ERR_AUTH_EMAIL_TAKEN_REGISTER = "An account with this email address already exists."
ERR_AUTH_EMAIL_TAKEN_PROFILE = "This email address is already registered to another account."
ERR_AUTH_PASSWORD_MISMATCH = "Passwords do not match."
ERR_AUTH_PASSWORD_WEAK = (
    "Password must be at least 8 characters long and contain letters and numbers."
)
ERR_AUTH_AVATAR_INVALID = "Avatar file must be an image (PNG, JPG, WEBP) under 2MB."
ERR_AUTH_CURRENT_PASSWORD_INCORRECT = "The current password entered is incorrect."
ERR_AUTH_NEW_PASSWORD_MISMATCH = "New passwords do not match."
ERR_AUTH_PASSWORD_SIMILAR = "New password cannot be identical to current password."


def _validate_password_complexity(password: str, user: CustomUser | None = None) -> None:
    """Enforce >= 8 chars with letter + digit, plus Django's configured validators."""
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValidationError(ERR_AUTH_PASSWORD_WEAK, code="password_weak")
    validate_password(password, user=user)


class RegisterForm(forms.Form):
    """Visitor registration form with case-insensitive uniqueness and password validation."""

    username = forms.CharField(
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. john_doe",
                "autocomplete": "username",
            }
        ),
    )
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "john@example.com",
                "autocomplete": "email",
            }
        ),
    )
    full_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "John Doe",
                "autocomplete": "name",
            }
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Minimum 8 characters",
                "autocomplete": "new-password",
            }
        ),
    )
    password_confirm = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Re-enter password",
                "autocomplete": "new-password",
            }
        ),
    )

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if not USERNAME_PATTERN.match(username):
            raise ValidationError(
                "Username must be 3-50 characters and contain only letters, numbers, "
                "and underscores."
            )
        if CustomUser.objects.filter(username__iexact=username).exists():
            raise ValidationError(ERR_AUTH_USERNAME_TAKEN, code="username_taken")
        return username

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise ValidationError(ERR_AUTH_EMAIL_TAKEN_REGISTER, code="email_taken")
        return email

    def clean_full_name(self) -> str:
        full_name = self.cleaned_data["full_name"].strip()
        if not full_name:
            raise ValidationError("Full name is required.")
        return full_name

    def clean_password(self) -> str:
        password = self.cleaned_data["password"]
        if (
            len(password) < 8
            or not re.search(r"[A-Za-z]", password)
            or not re.search(r"\d", password)
        ):
            raise ValidationError(ERR_AUTH_PASSWORD_WEAK, code="password_weak")
        return password

    def clean(self) -> dict:
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            self.add_error(
                "password_confirm",
                ValidationError(ERR_AUTH_PASSWORD_MISMATCH, code="password_mismatch"),
            )

        if password and "password" not in self.errors:
            candidate_user = CustomUser(
                username=cleaned_data.get("username", ""),
                email=cleaned_data.get("email", ""),
                full_name=cleaned_data.get("full_name", ""),
            )
            try:
                _validate_password_complexity(password, user=candidate_user)
            except ValidationError as exc:
                self.add_error("password", exc)

        return cleaned_data


class LoginForm(forms.Form):
    """Authentication form accepting username or email and optional remember-me flag."""

    username_or_email = forms.CharField(
        max_length=254,
        label="Username or Email",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Username or email",
                "autocomplete": "username",
            }
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your password",
                "autocomplete": "current-password",
            }
        ),
    )
    remember_me = forms.BooleanField(
        required=False,
        label="Remember me for 14 days",
    )

    def clean_username_or_email(self) -> str:
        value = self.cleaned_data["username_or_email"].strip()
        if not value:
            raise ValidationError("Username or email is required.")
        return value


class ProfileUpdateForm(forms.Form):
    """Authenticated user profile update form with email uniqueness and avatar checks."""

    full_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "name"}),
    )
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}),
    )
    avatar = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": ".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp",
            }
        ),
    )

    def __init__(self, *args, user: CustomUser, **kwargs) -> None:
        self.user = user
        if "initial" not in kwargs:
            initial_data: dict[str, object] = {
                "full_name": user.full_name,
                "email": user.email,
            }
            if user.avatar_url:
                initial_data["avatar"] = AvatarInitialRef(user.avatar_url)
            kwargs["initial"] = initial_data
        super().__init__(*args, **kwargs)

    def clean_full_name(self) -> str:
        full_name = self.cleaned_data["full_name"].strip()
        if not full_name:
            raise ValidationError("Full name is required.")
        return full_name

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if CustomUser.objects.exclude(pk=self.user.pk).filter(email__iexact=email).exists():
            raise ValidationError(ERR_AUTH_EMAIL_TAKEN_PROFILE, code="email_taken")
        return email

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if avatar is False:
            return False
        if not avatar or isinstance(avatar, AvatarInitialRef):
            return None
        validate_image_upload(avatar)
        return avatar


class PasswordChangeForm(forms.Form):
    """Password rotation form verifying current password and new password complexity."""

    current_password = forms.CharField(
        label="Current Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "autocomplete": "current-password",
            }
        ),
    )
    new_password = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "autocomplete": "new-password",
            }
        ),
    )
    new_password_confirm = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "autocomplete": "new-password",
            }
        ),
    )

    def __init__(self, *args, user: CustomUser, **kwargs) -> None:
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self) -> str:
        current_password = self.cleaned_data["current_password"]
        if not self.user.check_password(current_password):
            raise ValidationError(
                ERR_AUTH_CURRENT_PASSWORD_INCORRECT,
                code="current_password_incorrect",
            )
        return current_password

    def clean_new_password(self) -> str:
        new_password = self.cleaned_data["new_password"]
        _validate_password_complexity(new_password, user=self.user)
        return new_password

    def clean(self) -> dict:
        cleaned_data = super().clean()
        current_password = cleaned_data.get("current_password")
        new_password = cleaned_data.get("new_password")
        new_password_confirm = cleaned_data.get("new_password_confirm")

        if new_password and new_password_confirm and new_password != new_password_confirm:
            self.add_error(
                "new_password_confirm",
                ValidationError(ERR_AUTH_NEW_PASSWORD_MISMATCH, code="password_mismatch"),
            )

        if current_password and new_password and new_password == current_password:
            self.add_error(
                "new_password",
                ValidationError(ERR_AUTH_PASSWORD_SIMILAR, code="password_similar"),
            )

        return cleaned_data
