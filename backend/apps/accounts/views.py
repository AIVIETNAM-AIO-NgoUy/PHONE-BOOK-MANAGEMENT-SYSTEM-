"""Views for user registration, login, logout, profile, and password rotation."""

import os
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.storage import FileSystemStorage
from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_POST

from apps.accounts import forms as account_forms, services
from apps.accounts.models import CustomUser
from apps.core.utils import delete_media_file, resolve_media_path, schedule_media_delete_on_commit

REMEMBER_ME_AGE_SECONDS = 1209600  # 14 days


class RegisterView(View):
    """Handle public user registration for anonymous visitors."""

    template_name = "accounts/register.html"

    def _render_register(
        self,
        request: HttpRequest,
        form: account_forms.RegisterForm,
        *,
        status: int = 200,
    ) -> HttpResponse:
        context = {
            "form": form,
            "register_form": form,
            "login_form": account_forms.LoginForm(auto_id="id_login_%s"),
            "next": request.GET.get("next", "").strip(),
        }
        return render(request, self.template_name, context, status=status)

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if request.user.is_authenticated:
            return redirect(settings.LOGIN_REDIRECT_URL)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: HttpRequest) -> HttpResponse:
        return self._render_register(
            request,
            account_forms.RegisterForm(auto_id="id_register_%s"),
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        form = account_forms.RegisterForm(request.POST, auto_id="id_register_%s")
        if not form.is_valid():
            return self._render_register(request, form, status=400)

        try:
            with transaction.atomic():
                services.register_user(
                    username=form.cleaned_data["username"],
                    email=form.cleaned_data["email"],
                    full_name=form.cleaned_data["full_name"],
                    password=form.cleaned_data["password"],
                )
        except IntegrityError as exc:
            err_msg = str(exc).lower()
            if (
                "username" in err_msg
                or CustomUser.objects.filter(
                    username__iexact=form.cleaned_data["username"]
                ).exists()
            ):
                form.add_error("username", account_forms.ERR_AUTH_USERNAME_TAKEN)
            if (
                "email" in err_msg
                or CustomUser.objects.filter(email__iexact=form.cleaned_data["email"]).exists()
            ):
                form.add_error("email", account_forms.ERR_AUTH_EMAIL_TAKEN_REGISTER)
            if not form.errors:
                form.add_error(None, "An account with these details already exists.")
            return self._render_register(request, form, status=400)

        messages.success(request, "Registration successful. Please log in.")
        return redirect("accounts:login")


class LoginView(View):
    """Handle user authentication with remember-me and lock status enforcement."""

    template_name = "accounts/login.html"

    def _render_login(
        self,
        request: HttpRequest,
        form: account_forms.LoginForm,
        *,
        next_url: str = "",
        status: int = 200,
    ) -> HttpResponse:
        context = {
            "form": form,
            "login_form": form,
            "register_form": account_forms.RegisterForm(auto_id="id_register_%s"),
            "next": next_url,
        }
        return render(request, self.template_name, context, status=status)

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if request.user.is_authenticated:
            return redirect(settings.LOGIN_REDIRECT_URL)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: HttpRequest) -> HttpResponse:
        return self._render_login(
            request,
            account_forms.LoginForm(auto_id="id_login_%s"),
            next_url=request.GET.get("next", "").strip(),
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        form = account_forms.LoginForm(request.POST, auto_id="id_login_%s")
        next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()

        if not form.is_valid():
            return self._render_login(request, form, next_url=next_url, status=400)

        try:
            user = services.authenticate_account(
                form.cleaned_data["username_or_email"],
                form.cleaned_data["password"],
            )
        except services.InvalidCredentialsError as exc:
            form.add_error(None, exc.message)
            return self._render_login(
                request,
                form,
                next_url=next_url,
                status=exc.status_code,
            )
        except services.AccountLockedError as exc:
            form.add_error(None, exc.message)
            return self._render_login(
                request,
                form,
                next_url=next_url,
                status=exc.status_code,
            )

        login(request, user)
        if form.cleaned_data.get("remember_me"):
            request.session.set_expiry(REMEMBER_ME_AGE_SECONDS)
        else:
            request.session.set_expiry(0)

        if next_url and url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)

        return redirect(settings.LOGIN_REDIRECT_URL)


@method_decorator(login_required, name="dispatch")
@method_decorator(require_POST, name="dispatch")
class LogoutView(View):
    """Terminate authenticated user session via POST request."""

    def post(self, request: HttpRequest) -> HttpResponse:
        logout(request)
        messages.success(request, "You have been safely logged out.")
        return redirect("accounts:login")


class ProfileView(LoginRequiredMixin, View):
    """Display and update the authenticated user's profile."""

    template_name = "accounts/profile.html"
    partial_template_name = "accounts/partials/profile_card.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        form = account_forms.ProfileUpdateForm(user=request.user)
        return render(request, self.template_name, {"form": form})

    def post(self, request: HttpRequest) -> HttpResponse:
        form = account_forms.ProfileUpdateForm(request.POST, request.FILES, user=request.user)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form}, status=400)

        user = request.user
        old_avatar_url = user.avatar_url
        user.full_name = form.cleaned_data["full_name"]
        user.email = form.cleaned_data["email"]

        avatar_file = form.cleaned_data.get("avatar")
        new_avatar_path = None
        if avatar_file is False:
            user.avatar_url = None
        elif avatar_file is not None:
            avatars_dir = Path(settings.MEDIA_ROOT) / "avatars"
            avatars_dir.mkdir(parents=True, exist_ok=True)
            storage = FileSystemStorage(
                location=str(avatars_dir),
                base_url=f"{settings.MEDIA_URL}avatars/",
            )
            ext = os.path.splitext(avatar_file.name)[1].lower()
            filename = f"user_{user.pk}_{uuid.uuid4().hex[:8]}{ext}"
            saved_name = storage.save(filename, avatar_file)
            user.avatar_url = storage.url(saved_name)
            new_avatar_path = resolve_media_path(user.avatar_url)

        try:
            with transaction.atomic():
                user.save()
                if old_avatar_url and old_avatar_url != user.avatar_url:
                    schedule_media_delete_on_commit(old_avatar_url)
        except IntegrityError:
            delete_media_file(new_avatar_path)
            user.avatar_url = old_avatar_url
            form.add_error("email", account_forms.ERR_AUTH_EMAIL_TAKEN_PROFILE)
            return render(request, self.template_name, {"form": form}, status=400)
        except Exception:
            delete_media_file(new_avatar_path)
            raise

        if request.headers.get("HX-Request") == "true":
            return render(
                request,
                self.partial_template_name,
                {"user": user, "profile_updated": True},
                status=200,
            )

        messages.success(request, "Profile updated successfully.")
        return redirect("accounts:profile")


class PasswordChangeView(LoginRequiredMixin, View):
    """Allow authenticated users to rotate their password securely."""

    template_name = "accounts/password_change.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        form = account_forms.PasswordChangeForm(user=request.user)
        return render(request, self.template_name, {"form": form})

    def post(self, request: HttpRequest) -> HttpResponse:
        form = account_forms.PasswordChangeForm(request.POST, user=request.user)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form}, status=400)

        request.user.set_password(form.cleaned_data["new_password"])
        request.user.save(update_fields=["password", "updated_at"])
        update_session_auth_hash(request, request.user)
        services.flush_user_sessions(request.user, exclude_session_key=request.session.session_key)

        messages.success(request, "Your password has been changed successfully.")
        return redirect("accounts:profile")
