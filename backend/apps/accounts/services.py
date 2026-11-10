"""Domain services for account registration, authentication, and session eviction."""

from django.contrib.sessions.models import Session
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.contacts.models import ContactBook
from apps.favorites.models import FavoriteList


class AuthenticationError(Exception):
    """Base authentication failure carrying contract error code and HTTP status."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class InvalidCredentialsError(AuthenticationError):
    """Raised when username/email or password fails verification."""

    def __init__(self) -> None:
        super().__init__(
            code="ERR_AUTH_INVALID_CREDENTIALS",
            message="Invalid username/email or password.",
            status_code=401,
        )


class AccountLockedError(AuthenticationError):
    """Raised when an authenticated user's account is locked."""

    def __init__(self) -> None:
        super().__init__(
            code="ERR_AUTH_ACCOUNT_LOCKED",
            message="This account is locked. Please contact the system administrator.",
            status_code=403,
        )


@transaction.atomic
def register_user(
    *,
    username: str,
    email: str,
    full_name: str,
    password: str,
) -> CustomUser:
    """Create a CustomUser alongside its isolated ContactBook and FavoriteList."""
    user = CustomUser.objects.create_user(
        username=username.strip(),
        email=email.strip().lower(),
        full_name=full_name.strip(),
        password=password,
    )
    contact_book, _ = ContactBook.objects.get_or_create(user=user)
    FavoriteList.objects.get_or_create(book=contact_book)
    return user


def authenticate_account(username_or_email: str, password: str) -> CustomUser:
    """Authenticate a user by case-insensitive username/email and verify lock status."""
    identifier = (username_or_email or "").strip()
    if not identifier or not password:
        raise InvalidCredentialsError()

    user = CustomUser.objects.filter(
        Q(username__iexact=identifier) | Q(email__iexact=identifier.lower())
    ).first()

    if user is None or not user.check_password(password):
        raise InvalidCredentialsError()

    if user.account_status == CustomUser.AccountStatus.LOCKED or not user.is_active:
        raise AccountLockedError()

    return user


def flush_user_sessions(
    user: CustomUser,
    *,
    exclude_session_key: str | None = None,
) -> int:
    """Evict all active Django sessions belonging to the given user."""
    active_sessions = Session.objects.filter(expire_date__gte=timezone.now())
    keys_to_delete: list[str] = []

    for session in active_sessions:
        if exclude_session_key and session.session_key == exclude_session_key:
            continue
        try:
            data = session.get_decoded()
        except Exception:
            continue
        if str(data.get("_auth_user_id")) == str(user.pk):
            keys_to_delete.append(session.session_key)

    if not keys_to_delete:
        return 0

    deleted_count, _ = Session.objects.filter(session_key__in=keys_to_delete).delete()
    return deleted_count
