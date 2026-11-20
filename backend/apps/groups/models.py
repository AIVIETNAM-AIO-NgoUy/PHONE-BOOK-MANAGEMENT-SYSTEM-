"""Group and ContactGroup models for organizational contact categorization."""

from django.db import models
from django.db.models.functions import Length, Lower, Now, Trim
from django.db.models.lookups import GreaterThan, LessThanOrEqual


class Group(models.Model):
    """Organizational tag or category defined within a user's ContactBook."""

    MAX_NAME_LENGTH = 100
    MAX_DESCRIPTION_LENGTH = 500

    book = models.ForeignKey(
        "contacts.ContactBook",
        on_delete=models.CASCADE,
        related_name="groups",
    )
    group_name = models.CharField(max_length=MAX_NAME_LENGTH)
    description = models.TextField(null=True, blank=True, default=None)
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "groups_group"
        ordering = ["group_name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("group_name")), 0),
                name="chk_group_name_non_empty",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(description__isnull=True) | LessThanOrEqual(Length("description"), 500)
                ),
                name="chk_group_description_max_length",
            ),
            models.UniqueConstraint(
                fields=["book", "group_name"],
                name="uq_groups_book_name",
            ),
            models.UniqueConstraint(
                "book",
                Lower("group_name"),
                name="uq_groups_book_name_ci",
            ),
        ]
        indexes = [
            models.Index(fields=["book"], name="idx_groups_book_id"),
        ]

    def __str__(self) -> str:
        return f"{self.group_name} (book={self.book_id})"


class ContactGroup(models.Model):
    """Junction entity associating Contacts to Groups (many-to-many)."""

    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.CASCADE,
        related_name="contact_groups",
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="contact_groups",
    )
    assigned_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "groups_contactgroup"
        ordering = ["assigned_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["contact", "group"],
                name="uq_contactgroup_contact_group",
            ),
        ]
        indexes = [
            models.Index(fields=["contact"], name="idx_contactgroup_contact_id"),
            models.Index(fields=["group"], name="idx_contactgroup_group_id"),
        ]

    def __str__(self) -> str:
        return f"ContactGroup(contact={self.contact_id}, group={self.group_id})"
