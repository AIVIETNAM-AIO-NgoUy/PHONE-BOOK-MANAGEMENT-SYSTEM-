"""Forms for administrative user provisioning and account governance."""

import re

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.accounts.models import CustomUser

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,50}$")
ERR_AUTH_USERNAME_TAKEN = "This username is already taken. Please choose another."
ERR_AUTH_EMAIL_TAKEN = "An account with this email address already exists."
ERR_AUTH_EMAIL_TAKEN_PROFILE = "This email address is already registered to another account."
ERR_AUTH_PASSWORD_WEAK = (
    "Password must be at least 8 characters long and contain letters and numbers."
)


def _validate_password_complexity(password: str, user: CustomUser | None = None) -> None:
    """Enforce >= 8 chars with letter + digit, plus Django's configured validators."""
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValidationError(ERR_AUTH_PASSWORD_WEAK, code="password_weak")
    validate_password(password, user=user)


class AdminUserCreateForm(forms.Form):
    """Form for administrators to provision new user accounts."""

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
                "placeholder": "user@example.com",
                "autocomplete": "email",
            }
        ),
    )
    full_name = forms.CharField(
        max_length=150,
        required=False,
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
    role = forms.ChoiceField(
        choices=CustomUser.Role.choices,
        initial=CustomUser.Role.USER,
        widget=forms.RadioSelect(attrs={"class": "radio-card-input"}),
    )
    account_status = forms.ChoiceField(
        choices=CustomUser.AccountStatus.choices,
        initial=CustomUser.AccountStatus.ACTIVE,
        widget=forms.RadioSelect(attrs={"class": "radio-card-input"}),
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
            raise ValidationError(ERR_AUTH_EMAIL_TAKEN, code="email_taken")
        return email

    def clean_password(self) -> str:
        password = self.cleaned_data["password"]
        _validate_password_complexity(password)
        return password


class AdminUserEditForm(forms.Form):
    """Form for administrators to edit account metadata, role, status, and reset password."""

    full_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Full Name",
                "autocomplete": "name",
            }
        ),
    )
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "user@example.com",
                "autocomplete": "email",
            }
        ),
    )
    role = forms.ChoiceField(
        choices=CustomUser.Role.choices,
        widget=forms.RadioSelect(attrs={"class": "radio-card-input"}),
    )
    account_status = forms.ChoiceField(
        choices=CustomUser.AccountStatus.choices,
        widget=forms.RadioSelect(attrs={"class": "radio-card-input"}),
    )
    new_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Leave blank to keep unchanged",
                "autocomplete": "new-password",
            }
        ),
    )

    def __init__(
        self,
        *args,
        actor: CustomUser | None = None,
        target_user: CustomUser | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.target_user = target_user

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        queryset = CustomUser.objects.filter(email__iexact=email)
        if self.target_user:
            queryset = queryset.exclude(pk=self.target_user.pk)
        if queryset.exists():
            raise ValidationError(ERR_AUTH_EMAIL_TAKEN_PROFILE, code="email_taken")
        return email

    def clean_new_password(self) -> str:
        new_password = self.cleaned_data.get("new_password", "").strip()
        if new_password:
            _validate_password_complexity(new_password, user=self.target_user)
        return new_password

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean()
        if self.actor and self.target_user and self.actor.pk == self.target_user.pk:
            role = cleaned_data.get("role")
            if role and role != CustomUser.Role.ADMIN:
                self.add_error(
                    "role",
                    ValidationError(
                        "You cannot remove your own administrative role.",
                        code="self_demote",
                    ),
                )
            account_status = cleaned_data.get("account_status")
            if account_status and account_status == CustomUser.AccountStatus.LOCKED:
                self.add_error(
                    "account_status",
                    ValidationError(
                        "You cannot lock your own administrative account.",
                        code="self_lock",
                    ),
                )
        return cleaned_data
