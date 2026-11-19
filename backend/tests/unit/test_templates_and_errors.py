"""Unit tests for base template, error templates, and Django error handlers (T014)."""

from django.template.loader import render_to_string
from django.test import override_settings

import config.urls as root_urls


def test_base_template_renders_without_phase3_routes(rf):
    """base.html renders cleanly in Phase 2 with CSRF meta, HTMX, CSS, JS, and modal wrapper."""
    request = rf.get("/")
    html = render_to_string("base.html", request=request)

    assert "<!DOCTYPE html>" in html
    assert '<meta name="csrf-token"' in html
    assert "htmx.min.js" in html
    assert "styles.css" in html
    assert "app.js" in html
    assert 'id="confirm-modal-backdrop"' in html

    # Toast container renders in guest shell when messages are present
    html_with_messages = render_to_string(
        "base.html",
        {"messages": [{"tags": "info", "message": "Notification"}]},
        request=request,
    )
    assert 'id="toast-container"' in html_with_messages


def test_error_templates_render_with_base_layout(rf):
    """403.html, 404.html, and 500.html extend base.html and render user-friendly content."""
    request = rf.get("/missing-page")

    html_403 = render_to_string("403.html", request=request)
    html_404 = render_to_string("404.html", request=request)
    html_500 = render_to_string("500.html", request=request)

    assert "403" in html_403
    assert "<!DOCTYPE html>" in html_403
    assert "404" in html_404
    assert "<!DOCTYPE html>" in html_404
    assert "500" in html_500
    assert "<!DOCTYPE html>" in html_500


def test_root_urls_exposes_custom_error_handlers():
    """config.urls wires handler403, handler404, and handler500."""
    assert hasattr(root_urls, "handler403")
    assert hasattr(root_urls, "handler404")
    assert hasattr(root_urls, "handler500")


def test_custom_error_views_return_expected_status_codes(rf):
    """Custom error handler views return HTTP 403, 404, and 500 with rendered templates."""
    from apps.core.views import custom_403_view, custom_404_view, custom_500_view

    request = rf.get("/")

    resp_403 = custom_403_view(request, exception=PermissionError("Forbidden"))
    resp_404 = custom_404_view(request, exception=Exception("Not Found"))
    resp_500 = custom_500_view(request)

    assert resp_403.status_code == 403
    assert b"403" in resp_403.content

    assert resp_404.status_code == 404
    assert b"404" in resp_404.content

    assert resp_500.status_code == 500
    assert b"500" in resp_500.content


@override_settings(DEBUG=False)
def test_unknown_route_uses_custom_404_template(client):
    """Requesting an unknown URL when DEBUG=False renders templates/404.html with 404 status."""
    response = client.get("/nonexistent-route-phase2/")
    assert response.status_code == 404
    assert b"404" in response.content
