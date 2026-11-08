"""Core cross-cutting views including health check and error handlers."""

from django.db import DatabaseError, connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET


def root_redirect_view(request: HttpRequest) -> HttpResponse:
    """Redirect root URL to contacts directory when signed in, else login page."""
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        return redirect("contacts:list")
    return redirect("accounts:login")


@require_GET
def healthz(request: HttpRequest) -> HttpResponse:
    """Verify application and PostgreSQL database connectivity."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse(
            {"status": "error", "database": "disconnected"},
            status=503,
        )

    return JsonResponse(
        {"status": "ok", "database": "connected"},
        status=200,
    )


def custom_403_view(request: HttpRequest, exception=None) -> HttpResponse:
    """Render user-friendly 403 Forbidden page."""
    return render(request, "403.html", status=403)


def custom_404_view(request: HttpRequest, exception=None) -> HttpResponse:
    """Render user-friendly 404 Not Found page."""
    return render(request, "404.html", status=404)


def custom_500_view(request: HttpRequest) -> HttpResponse:
    """Render user-friendly 500 Internal Server Error page."""
    return render(request, "500.html", status=500)
