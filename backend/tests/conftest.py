"""Shared pytest fixtures for the Phone Book Management System test suite."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import Client, RequestFactory


@pytest.fixture
def rf() -> RequestFactory:
    """Return a Django RequestFactory instance."""
    return RequestFactory()


@pytest.fixture
def http_client() -> Client:
    """Return a fresh Django test Client instance."""
    return Client()


@pytest.fixture
def attach_session_and_messages():
    """Attach mock session and Django fallback message storage to a RequestFactory request."""

    def _attach(request):
        session = MagicMock()
        session.session_key = "test-session-key"
        request.session = session
        request._messages = FallbackStorage(request)
        return request

    return _attach


@pytest.fixture
def mock_user_factory():
    """Factory producing lightweight mock user objects for Phase 2 unit tests."""

    def _create_mock_user(
        *,
        user_id: int = 1,
        username: str = "testuser",
        email: str = "testuser@example.com",
        full_name: str = "Test User",
        role: str = "User",
        account_status: str = "Active",
        is_authenticated: bool = True,
        is_active: bool = True,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            id=user_id,
            pk=user_id,
            username=username,
            email=email,
            full_name=full_name,
            role=role,
            account_status=account_status,
            is_authenticated=is_authenticated,
            is_active=is_active,
        )

    return _create_mock_user


@pytest.fixture
def user_factory(db):
    """Database-backed user factory for Phase 3+ integration and contract tests."""
    counter = {"value": 0}

    def _create_user(**kwargs: Any):
        counter["value"] += 1
        idx = counter["value"]
        user_model = get_user_model()
        password = kwargs.pop("password", "SecurePass123!")
        defaults: dict[str, Any] = {
            "username": f"user_{idx}",
            "email": f"user_{idx}@example.com",
        }
        if hasattr(user_model, "full_name"):
            defaults["full_name"] = f"Test User {idx}"
        if hasattr(user_model, "role"):
            defaults["role"] = "User"
        if hasattr(user_model, "account_status"):
            defaults["account_status"] = "Active"
        defaults.update(kwargs)
        user = user_model.objects.create_user(password=password, **defaults)

        from apps.contacts.models import ContactBook
        from apps.favorites.models import FavoriteList

        contact_book, _ = ContactBook.objects.get_or_create(user=user)
        FavoriteList.objects.get_or_create(book=contact_book)
        return user

    return _create_user


@pytest.fixture
def authenticated_client(http_client: Client, user_factory):
    """Return a tuple of (authenticated Client, user) ready for Phase 3+ tests."""

    def _make_authenticated_client(**user_kwargs: Any):
        user = user_factory(**user_kwargs)
        http_client.force_login(user)
        return http_client, user

    return _make_authenticated_client
