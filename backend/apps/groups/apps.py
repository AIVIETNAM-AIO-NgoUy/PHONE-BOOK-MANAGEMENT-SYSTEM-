"""Django application configuration for groups domain."""

from django.apps import AppConfig


class GroupsConfig(AppConfig):
    """AppConfig for custom contact groups and many-to-many memberships."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.groups"
    verbose_name = "Groups"
