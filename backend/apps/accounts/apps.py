"""Django application configuration for accounts domain."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """AppConfig for identity, authentication, and account lifecycle."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Accounts"
