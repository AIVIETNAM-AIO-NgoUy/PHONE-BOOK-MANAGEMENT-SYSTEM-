"""Unit tests for core abstract models (T006)."""

from django.db import models
from django.db.models.functions import Now

from apps.core.models import TimeStampedModel


def test_timestamped_model_is_abstract():
    """TimeStampedModel must be abstract with created_at and updated_at TIMESTAMPTZ fields."""
    assert TimeStampedModel._meta.abstract is True

    created_at = TimeStampedModel._meta.get_field("created_at")
    updated_at = TimeStampedModel._meta.get_field("updated_at")

    assert isinstance(created_at, models.DateTimeField)
    assert isinstance(updated_at, models.DateTimeField)
    assert created_at.auto_now_add is True
    assert updated_at.auto_now is True
    assert isinstance(created_at.db_default, Now)
    assert isinstance(updated_at.db_default, Now)
