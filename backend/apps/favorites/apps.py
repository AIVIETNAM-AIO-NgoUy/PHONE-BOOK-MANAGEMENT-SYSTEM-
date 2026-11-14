"""Django application configuration for favorites domain."""

from django.apps import AppConfig


class FavoritesConfig(AppConfig):
    """AppConfig for favorite contact lists and priority ranking."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.favorites"
    verbose_name = "Favorites"
