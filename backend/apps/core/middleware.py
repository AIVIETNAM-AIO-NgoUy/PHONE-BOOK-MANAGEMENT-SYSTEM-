"""Cross-cutting middleware for the Phone Book Management System."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import SESSION_KEY, get_user_model
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


class AccountLockMiddleware:
    """Immediately evict sessions and redirect requests belonging to locked accounts."""

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _is_locked_or_inactive_session_user(request: HttpRequest) -> bool:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return getattr(user, "account_status", None) == "Locked" or not getattr(
                user, "is_active", True
            )

        session = getattr(request, "session", None)
        if session is None:
            return False
        raw_user_id = session.get(SESSION_KEY)
        if not isinstance(raw_user_id, (int, str)):
            return False

        user_model = get_user_model()
        try:
            row = (
                user_model._default_manager.filter(pk=raw_user_id)
                .values("account_status", "is_active")
                .first()
            )
        except (ValueError, TypeError):
            return False
        if not row:
            return False
        return row["account_status"] == "Locked" or not row["is_active"]

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if self._is_locked_or_inactive_session_user(request):
            request.session.flush()
            messages.error(
                request,
                "This account is locked. Please contact the system administrator.",
            )
            login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")
            if request.headers.get("HX-Request") == "true":
                response = HttpResponse(status=200)
                response["HX-Redirect"] = login_url
                return response
            return redirect(login_url)

        return self.get_response(request)
