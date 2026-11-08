"""Shared sanitization, phone normalization, and upload validation utilities."""

import os
import re
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

ERR_CONTACT_PHONE_INVALID = "Phone number must contain between 8 and 20 digits."
ERR_AVATAR_INVALID = "Avatar file must be an image (PNG, JPG, WEBP) under 2MB."

MAX_AVATAR_BYTES = 2 * 1024 * 1024
ALLOWED_AVATAR_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PHONE_SEPARATORS_RE = re.compile(r"[\s\-().]+")


def normalize_phone_number(raw_phone: str | None) -> str:
    """Normalize and validate Vietnamese and E.164 phone numbers (8–20 digits)."""
    if raw_phone is None:
        raise ValidationError(ERR_CONTACT_PHONE_INVALID, code="invalid_phone")

    cleaned = _PHONE_SEPARATORS_RE.sub("", str(raw_phone).strip())
    if not cleaned:
        raise ValidationError(ERR_CONTACT_PHONE_INVALID, code="invalid_phone")

    if cleaned.startswith("+"):
        digits = cleaned[1:]
        if not digits.isdigit() or digits.startswith("0"):
            raise ValidationError(ERR_CONTACT_PHONE_INVALID, code="invalid_phone")
    else:
        digits = cleaned
        if not digits.isdigit():
            raise ValidationError(ERR_CONTACT_PHONE_INVALID, code="invalid_phone")

    if not (8 <= len(digits) <= 20) or len(cleaned) > 20:
        raise ValidationError(ERR_CONTACT_PHONE_INVALID, code="invalid_phone")

    return cleaned


def sanitize_contact_text(value: str | None, *, collapse_newlines: bool = False) -> str | None:
    """Trim whitespace and strip unsafe control characters from contact text inputs."""
    if value is None:
        return None

    text = _CONTROL_CHARS_RE.sub("", str(value))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if collapse_newlines:
        text = text.replace("\n", " ").replace("\t", " ")

    text = text.strip()
    return text if text else None


def _has_valid_image_magic_bytes(header: bytes, ext: str) -> bool:
    """Inspect magic header bytes for PNG, JPEG, and WEBP without external libraries."""
    if ext == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    return (
        ext == ".webp" and len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    )


def validate_image_upload(uploaded_file, *, max_bytes: int = MAX_AVATAR_BYTES) -> None:
    """Validate uploaded avatar file size, extension, and image magic bytes."""
    if uploaded_file is None:
        return

    if uploaded_file.size > max_bytes:
        raise ValidationError(ERR_AVATAR_INVALID, code="avatar_too_large")

    ext = os.path.splitext(uploaded_file.name or "")[1].lower()
    if ext not in ALLOWED_AVATAR_EXTENSIONS:
        raise ValidationError(ERR_AVATAR_INVALID, code="avatar_invalid_ext")

    current_pos = uploaded_file.tell()
    uploaded_file.seek(0)
    header = uploaded_file.read(16)
    uploaded_file.seek(current_pos)

    if not _has_valid_image_magic_bytes(header, ext):
        raise ValidationError(ERR_AVATAR_INVALID, code="avatar_invalid_signature")


def resolve_media_path(media_url: str | None) -> Path | None:
    """Resolve a stored MEDIA_URL-relative file URL safely to a Path inside MEDIA_ROOT."""
    if not media_url or not isinstance(media_url, str):
        return None
    media_prefix = settings.MEDIA_URL or "/media/"
    if not media_prefix.endswith("/"):
        media_prefix += "/"
    if not media_url.startswith(media_prefix):
        return None
    rel_path = media_url[len(media_prefix) :].lstrip("/")
    if not rel_path:
        return None
    media_root = Path(settings.MEDIA_ROOT).resolve()
    candidate = (media_root / rel_path).resolve()
    try:
        candidate.relative_to(media_root)
    except ValueError:
        return None
    return candidate


def delete_media_file(media_path: Path | None) -> None:
    """Safely unlink an existing media file path if present."""
    if media_path is None:
        return
    try:
        if media_path.is_file():
            media_path.unlink()
    except OSError:
        pass


class AvatarInitialRef:
    """Lightweight URL wrapper enabling Django ClearableFileInput clear controls."""

    def __init__(self, url: str) -> None:
        self.url = url

    def __str__(self) -> str:
        return self.url.rsplit("/", 1)[-1] or self.url


def schedule_media_delete_on_commit(media_url: str | None) -> None:
    """Resolve media_url immediately and delete the file after the transaction commits."""
    target_path = resolve_media_path(media_url)
    if target_path is not None:
        transaction.on_commit(lambda path=target_path: delete_media_file(path))
