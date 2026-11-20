"""Django application configuration for core shared utilities."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """AppConfig for the shared core application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"
