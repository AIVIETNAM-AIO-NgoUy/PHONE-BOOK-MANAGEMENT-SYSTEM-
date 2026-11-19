"""Unit tests for the /healthz system health check endpoint (T009)."""

from unittest.mock import MagicMock, patch

import pytest
from django.db import OperationalError


@pytest.mark.django_db
def test_healthcheck_returns_200_and_ok_json(client):
    """GET /healthz executes SELECT 1 and returns HTTP 200 with healthy JSON payload."""
    response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "connected"


def test_healthcheck_returns_503_when_database_unavailable(client):
    """GET /healthz returns HTTP 503 when PostgreSQL connection fails."""
    mock_cursor = MagicMock()
    mock_cursor.__enter__.side_effect = OperationalError("connection refused")

    with patch("apps.core.views.connection.cursor", return_value=mock_cursor):
        response = client.get("/healthz")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["database"] == "disconnected"


def test_healthcheck_rejects_post_requests(client):
    """POST /healthz returns HTTP 405 Method Not Allowed."""
    response = client.post("/healthz")
    assert response.status_code == 405
