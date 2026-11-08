"""RBAC and access control decorators for protected application routes."""

import logging
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)


def _is_admin_user(user) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return bool(
        getattr(user, "is_admin", False)
        or getattr(user, "role", None) == "Admin"
        or getattr(user, "is_staff", False)
    )


def admin_required(view_func):
    """Reject unauthenticated or non-admin users with 403 Forbidden and log a warning."""

    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        user = getattr(request, "user", None)
        if not _is_admin_user(user):
            username = (
                getattr(user, "username", "anonymous")
                if user is not None and getattr(user, "is_authenticated", False)
                else "anonymous"
            )
            logger.warning(
                "Unauthorized admin access blocked: path=%s method=%s user=%s",
                request.path,
                request.method,
                username,
            )
            raise PermissionDenied("Administrator privileges required.")
        return view_func(request, *args, **kwargs)

    return _wrapped_view
