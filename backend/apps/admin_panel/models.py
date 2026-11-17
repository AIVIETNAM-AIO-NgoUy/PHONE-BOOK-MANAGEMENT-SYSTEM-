"""AuditLog model for persistent administrative governance and security trails."""

from django.conf import settings
from django.db import models
from django.db.models.functions import Now


class AuditLog(models.Model):
    """Immutable audit log recording administrative account governance actions."""

    class Action(models.TextChoices):
        ACCOUNT_LOCKED = "ACCOUNT_LOCKED", "Account Locked"
        ACCOUNT_UNLOCKED = "ACCOUNT_UNLOCKED", "Account Unlocked"
        USER_CREATED = "USER_CREATED", "User Created"
        USER_UPDATED = "USER_UPDATED", "User Updated"
        USER_DELETED = "USER_DELETED", "User Deleted"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admin_actions_performed",
    )
    actor_username_snapshot = models.CharField(max_length=150)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admin_actions_received",
    )
    target_username_snapshot = models.CharField(max_length=150)
    action = models.CharField(max_length=50, choices=Action.choices)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.CharField(max_length=45, null=True, blank=True, default=None)
    user_agent = models.CharField(max_length=255, null=True, blank=True, default=None)
    timestamp = models.DateTimeField(auto_now_add=True, db_default=Now())

    class Meta:
        db_table = "admin_panel_auditlog"
        ordering = ["-timestamp", "-id"]
        indexes = [
            models.Index(fields=["-timestamp"], name="idx_auditlog_timestamp"),
            models.Index(fields=["target_user"], name="idx_auditlog_target_user"),
            models.Index(fields=["actor"], name="idx_auditlog_actor"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.action} target={self.target_username_snapshot} "
            f"by={self.actor_username_snapshot}"
        )
