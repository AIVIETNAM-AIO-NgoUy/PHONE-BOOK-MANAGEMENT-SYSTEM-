"""Development settings for Phone Book Management System."""

from decouple import config

from .base import *  # noqa: F401, F403

DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = [
    "https://*.ngrok-free.app",
    "https://*.ngrok.io",
    "https://*.trycloudflare.com",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
]
