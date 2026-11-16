"""Django application configuration for administrative governance domain."""

from django.apps import AppConfig


class AdminPanelConfig(AppConfig):
    """AppConfig for administrative user governance and audit logging."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.admin_panel"
    verbose_name = "Admin Panel"
