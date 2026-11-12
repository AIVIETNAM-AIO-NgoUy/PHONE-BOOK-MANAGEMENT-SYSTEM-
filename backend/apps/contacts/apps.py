"""Django application configuration for contacts domain."""

from django.apps import AppConfig


class ContactsConfig(AppConfig):
    """AppConfig for personal contact books and contact records."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.contacts"
    verbose_name = "Contacts"
