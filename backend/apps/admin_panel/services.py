"""Domain service layer for administrative user account governance (T093)."""

from typing import Any

from django.db import transaction

from apps.accounts.models import CustomUser
from apps.accounts.services import flush_user_sessions
from apps.admin_panel.models import AuditLog
from apps.contacts.models import ContactBook
from apps.favorites.models import FavoriteList


class GovernanceError(Exception):
    """Base domain error for administrative account governance actions."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class SelfLockError(GovernanceError):
    """Raised when an administrator attempts to lock their own account."""

    def __init__(self) -> None:
        super().__init__(
            code="ERR_ADMIN_SELF_LOCK",
            message="You cannot lock your own administrative account.",
            status_code=400,
        )


class SelfDemoteError(GovernanceError):
    """Raised when an administrator attempts to remove their own administrative role."""

    def __init__(self) -> None:
        super().__init__(
            code="ERR_ADMIN_SELF_DEMOTE",
            message="You cannot remove your own administrative role.",
            status_code=400,
        )


class SelfDeleteError(GovernanceError):
    """Raised when an administrator attempts to delete their own account."""

    def __init__(self) -> None:
        super().__init__(
            code="ERR_ADMIN_SELF_DELETE",
            message="You cannot delete your own administrative account.",
            status_code=400,
        )


class ConfirmationRequiredError(GovernanceError):
    """Raised when a destructive deletion lacks explicit confirmation."""

    def __init__(self) -> None:
        super().__init__(
            code="ERR_CONFIRMATION_REQUIRED",
            message="Deletion confirmation is required.",
            status_code=400,
        )


class InvalidAccountStateError(GovernanceError):
    """Raised when a lock/unlock transition violates the account's current status."""


class AccountGovernanceService:
    """Atomic governance operations with row locking, session eviction, and audit logging."""

    @staticmethod
    @transaction.atomic
    def lock_user_account(
        actor: CustomUser,
        target_user_id: int,
        reason: str = "",
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CustomUser:
        """Lock a target user account, evict active sessions, and write an audit log."""
        target_user = CustomUser.objects.select_for_update().get(pk=target_user_id)

        if actor.pk == target_user.pk:
            raise SelfLockError()

        if target_user.account_status == CustomUser.AccountStatus.LOCKED:
            raise InvalidAccountStateError(
                code="ERR_ACCOUNT_ALREADY_LOCKED",
                message="This account is already in Locked status.",
                status_code=400,
            )

        target_user.account_status = CustomUser.AccountStatus.LOCKED
        target_user.save(update_fields=["account_status", "updated_at"])

        flush_user_sessions(target_user)

        clean_reason = (reason or "").strip()
        details = {"reason": clean_reason} if clean_reason else {}

        AuditLog.objects.create(
            actor=actor,
            actor_username_snapshot=actor.username,
            target_user=target_user,
            target_username_snapshot=target_user.username,
            action=AuditLog.Action.ACCOUNT_LOCKED,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent[:255] if user_agent else None,
        )
        return target_user

    @staticmethod
    @transaction.atomic
    def unlock_user_account(
        actor: CustomUser,
        target_user_id: int,
        reason: str = "",
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CustomUser:
        """Restore a locked user account to Active status and write an audit log."""
        target_user = CustomUser.objects.select_for_update().get(pk=target_user_id)

        if target_user.account_status == CustomUser.AccountStatus.ACTIVE:
            raise InvalidAccountStateError(
                code="ERR_ACCOUNT_ALREADY_ACTIVE",
                message="Account is already active.",
                status_code=400,
            )

        target_user.account_status = CustomUser.AccountStatus.ACTIVE
        target_user.save(update_fields=["account_status", "updated_at"])

        clean_reason = (reason or "").strip()
        details = {"reason": clean_reason} if clean_reason else {}

        AuditLog.objects.create(
            actor=actor,
            actor_username_snapshot=actor.username,
            target_user=target_user,
            target_username_snapshot=target_user.username,
            action=AuditLog.Action.ACCOUNT_UNLOCKED,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent[:255] if user_agent else None,
        )
        return target_user

    @staticmethod
    @transaction.atomic
    def create_user_account(
        actor: CustomUser,
        *,
        username: str,
        email: str,
        full_name: str,
        password: str,
        role: str = CustomUser.Role.USER,
        account_status: str = CustomUser.AccountStatus.ACTIVE,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CustomUser:
        """Create a new user account, ensure isolated ContactBook, and log audit event."""
        is_staff = role == CustomUser.Role.ADMIN
        user = CustomUser.objects.create_user(
            username=username.strip(),
            email=email.strip().lower(),
            full_name=full_name.strip(),
            password=password,
            role=role,
            account_status=account_status,
            is_staff=is_staff,
        )

        contact_book, _ = ContactBook.objects.get_or_create(user=user)
        FavoriteList.objects.get_or_create(book=contact_book)

        AuditLog.objects.create(
            actor=actor,
            actor_username_snapshot=actor.username,
            target_user=user,
            target_username_snapshot=user.username,
            action=AuditLog.Action.USER_CREATED,
            details={
                "role": user.role,
                "account_status": user.account_status,
                "email": user.email,
            },
            ip_address=ip_address,
            user_agent=user_agent[:255] if user_agent else None,
        )
        return user

    @staticmethod
    @transaction.atomic
    def update_user_account(
        actor: CustomUser,
        target_user_id: int,
        *,
        full_name: str | None = None,
        email: str | None = None,
        role: str | None = None,
        account_status: str | None = None,
        new_password: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CustomUser:
        """Update user metadata, enforce invariants, and flush sessions if locked."""
        target_user = CustomUser.objects.select_for_update().get(pk=target_user_id)

        if actor.pk == target_user.pk:
            if role is not None and role != CustomUser.Role.ADMIN:
                raise SelfDemoteError()
            if account_status is not None and account_status == CustomUser.AccountStatus.LOCKED:
                raise SelfLockError()

        changes: dict[str, Any] = {}
        update_fields: list[str] = ["updated_at"]

        if full_name is not None and full_name.strip() != target_user.full_name:
            changes["full_name"] = {"old": target_user.full_name, "new": full_name.strip()}
            target_user.full_name = full_name.strip()
            update_fields.append("full_name")

        if email is not None and email.strip().lower() != target_user.email:
            changes["email"] = {"old": target_user.email, "new": email.strip().lower()}
            target_user.email = email.strip().lower()
            update_fields.append("email")

        if role is not None and role != target_user.role:
            changes["role"] = {"old": target_user.role, "new": role}
            target_user.role = role
            target_user.is_staff = role == CustomUser.Role.ADMIN
            update_fields.extend(["role", "is_staff"])

        status_changed_to_locked = False
        if account_status is not None and account_status != target_user.account_status:
            changes["account_status"] = {"old": target_user.account_status, "new": account_status}
            target_user.account_status = account_status
            update_fields.append("account_status")
            if account_status == CustomUser.AccountStatus.LOCKED:
                status_changed_to_locked = True

        if new_password:
            target_user.set_password(new_password)
            changes["password"] = "changed"
            update_fields.append("password")

        target_user.save(update_fields=list(set(update_fields)))

        if status_changed_to_locked:
            flush_user_sessions(target_user)

        AuditLog.objects.create(
            actor=actor,
            actor_username_snapshot=actor.username,
            target_user=target_user,
            target_username_snapshot=target_user.username,
            action=AuditLog.Action.USER_UPDATED,
            details=changes,
            ip_address=ip_address,
            user_agent=user_agent[:255] if user_agent else None,
        )
        return target_user

    @staticmethod
    @transaction.atomic
    def delete_user_account(
        actor: CustomUser,
        target_user_id: int,
        *,
        confirm: bool = False,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Evict sessions, delete user with cascading data removal, and record audit log."""
        if not confirm:
            raise ConfirmationRequiredError()

        target_user = CustomUser.objects.select_for_update().get(pk=target_user_id)

        if actor.pk == target_user.pk:
            raise SelfDeleteError()

        target_username = target_user.username
        details = {
            "deleted_user_id": target_user.pk,
            "email": target_user.email,
            "role": target_user.role,
        }

        flush_user_sessions(target_user)
        target_user.delete()

        AuditLog.objects.create(
            actor=actor,
            actor_username_snapshot=actor.username,
            target_user=None,
            target_username_snapshot=target_username,
            action=AuditLog.Action.USER_DELETED,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent[:255] if user_agent else None,
        )
