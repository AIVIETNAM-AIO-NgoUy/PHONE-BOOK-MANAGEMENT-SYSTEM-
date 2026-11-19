"""Unit tests for AccountLockMiddleware using mock users (T016)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from django.conf import settings
from django.contrib.messages import get_messages
from django.contrib.messages.constants import ERROR
from django.http import HttpResponse


def test_anonymous_user_passes_through(rf, attach_session_and_messages, mock_user_factory):
    """Unauthenticated visitors pass through without session flush or redirect."""
    from apps.core.middleware import AccountLockMiddleware

    expected_response = HttpResponse("OK", status=200)
    get_response = MagicMock(return_value=expected_response)
    middleware = AccountLockMiddleware(get_response)

    request = attach_session_and_messages(rf.get("/contacts/"))
    request.user = mock_user_factory(is_authenticated=False, account_status="Locked")

    response = middleware(request)

    assert response is expected_response
    get_response.assert_called_once_with(request)
    request.session.flush.assert_not_called()


def test_active_user_passes_through(rf, attach_session_and_messages, mock_user_factory):
    """Authenticated user with account_status='Active' proceeds normally."""
    from apps.core.middleware import AccountLockMiddleware

    expected_response = HttpResponse("OK", status=200)
    get_response = MagicMock(return_value=expected_response)
    middleware = AccountLockMiddleware(get_response)

    request = attach_session_and_messages(rf.get("/contacts/"))
    request.user = mock_user_factory(is_authenticated=True, account_status="Active")

    response = middleware(request)

    assert response is expected_response
    get_response.assert_called_once_with(request)
    request.session.flush.assert_not_called()


def test_user_without_account_status_passes_through(rf, attach_session_and_messages):
    """Authenticated user lacking account_status attribute does not raise AttributeError."""
    from apps.core.middleware import AccountLockMiddleware

    expected_response = HttpResponse("OK", status=200)
    get_response = MagicMock(return_value=expected_response)
    middleware = AccountLockMiddleware(get_response)

    request = attach_session_and_messages(rf.get("/"))
    request.user = SimpleNamespace(is_authenticated=True, username="builtin_user")

    response = middleware(request)

    assert response is expected_response
    get_response.assert_called_once_with(request)
    request.session.flush.assert_not_called()


def test_locked_user_flushes_session_sets_error_and_redirects(
    rf, attach_session_and_messages, mock_user_factory
):
    """Locked user triggers session.flush(), error flash message, and 302 redirect to login."""
    from apps.core.middleware import AccountLockMiddleware

    get_response = MagicMock(return_value=HttpResponse("Should not reach view"))
    middleware = AccountLockMiddleware(get_response)

    request = attach_session_and_messages(rf.get("/contacts/"))
    request.user = mock_user_factory(is_authenticated=True, account_status="Locked")

    response = middleware(request)

    get_response.assert_not_called()
    request.session.flush.assert_called_once()
    assert response.status_code == 302
    assert response["Location"] == settings.LOGIN_URL

    stored_messages = list(get_messages(request))
    assert len(stored_messages) == 1
    assert stored_messages[0].level == ERROR
    assert "locked" in stored_messages[0].message.lower()


def test_inactive_user_flushes_session_sets_error_and_redirects(
    rf, attach_session_and_messages, mock_user_factory
):
    """User with is_active=False is also evicted even if account_status is Active."""
    from apps.core.middleware import AccountLockMiddleware

    get_response = MagicMock(return_value=HttpResponse("Should not reach view"))
    middleware = AccountLockMiddleware(get_response)

    request = attach_session_and_messages(rf.get("/contacts/"))
    request.user = mock_user_factory(
        is_authenticated=True, account_status="Active", is_active=False
    )

    response = middleware(request)

    get_response.assert_not_called()
    request.session.flush.assert_called_once()
    assert response.status_code == 302
    assert response["Location"] == settings.LOGIN_URL

    stored_messages = list(get_messages(request))
    assert len(stored_messages) == 1
    assert stored_messages[0].level == ERROR


def test_locked_user_htmx_request_returns_hx_redirect_header(
    rf, attach_session_and_messages, mock_user_factory
):
    """Locked user making an HTMX request receives HX-Redirect header to login URL."""
    from apps.core.middleware import AccountLockMiddleware

    get_response = MagicMock(return_value=HttpResponse("Should not reach view"))
    middleware = AccountLockMiddleware(get_response)

    request = attach_session_and_messages(rf.get("/contacts/search/", HTTP_HX_REQUEST="true"))
    request.user = mock_user_factory(is_authenticated=True, account_status="Locked")

    response = middleware(request)

    get_response.assert_not_called()
    request.session.flush.assert_called_once()
    assert response.headers.get("HX-Redirect") == settings.LOGIN_URL

    stored_messages = list(get_messages(request))
    assert len(stored_messages) == 1
    assert stored_messages[0].level == ERROR


def test_middleware_registered_after_message_middleware_and_login_url_set():
    """AccountLockMiddleware is placed after MessageMiddleware and LOGIN_URL is configured."""
    middleware_list = list(settings.MIDDLEWARE)
    msg_idx = middleware_list.index("django.contrib.messages.middleware.MessageMiddleware")
    lock_idx = middleware_list.index("apps.core.middleware.AccountLockMiddleware")

    assert lock_idx > msg_idx
    assert settings.LOGIN_URL == "/accounts/login/"
