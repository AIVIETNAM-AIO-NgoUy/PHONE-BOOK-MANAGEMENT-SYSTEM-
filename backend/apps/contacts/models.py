"""ContactBook, Contact, and PhoneNumber models for multi-tenant contact storage."""

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models.functions import Length, Now, Trim
from django.db.models.lookups import GreaterThan, GreaterThanOrEqual, LessThanOrEqual

from apps.core.models import TimeStampedModel


class ContactBook(models.Model):
    """Isolated personal contact directory owned by exactly one CustomUser."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="contact_book",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "contacts_contactbook"

    def __str__(self) -> str:
        return f"ContactBook(user={self.user_id})"


class Contact(TimeStampedModel):
    """Individual contact entry strictly scoped to a user's ContactBook."""

    book = models.ForeignKey(
        ContactBook,
        on_delete=models.CASCADE,
        related_name="contacts",
    )
    full_name = models.CharField(max_length=150)
    email = models.EmailField(max_length=254, null=True, blank=True, default=None)
    address = models.CharField(max_length=255, null=True, blank=True, default=None)
    work_address = models.CharField(max_length=255, null=True, blank=True, default=None)
    avatar = models.CharField(max_length=255, null=True, blank=True, default=None)
    birthday = models.DateField(null=True, blank=True, default=None)
    notes = models.TextField(null=True, blank=True, default=None)
    interaction_count = models.IntegerField(default=0)
    last_contacted_at = models.DateTimeField(null=True, blank=True, default=None)

    class Meta:
        db_table = "contacts_contact"
        ordering = ["full_name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("full_name")), 0),
                name="chk_contact_full_name_non_empty",
            ),
            models.CheckConstraint(
                condition=models.Q(notes__isnull=True) | LessThanOrEqual(Length("notes"), 1000),
                name="chk_contact_notes_max_length",
            ),
            models.CheckConstraint(
                condition=models.Q(interaction_count__gte=0),
                name="chk_contact_interaction_non_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["book"], name="idx_contacts_book_id"),
            models.Index(fields=["book", "full_name"], name="idx_contacts_book_fullname"),
            models.Index(
                models.F("book"),
                models.OrderBy(models.F("interaction_count"), descending=True),
                models.OrderBy(models.F("last_contacted_at"), descending=True, nulls_last=True),
                name="idx_contacts_frequency",
            ),
            GinIndex(
                fields=["full_name"],
                opclasses=["gin_trgm_ops"],
                name="idx_contacts_fullname_trgm",
            ),
            GinIndex(
                fields=["email"],
                opclasses=["gin_trgm_ops"],
                name="idx_contacts_email_trgm",
            ),
        ]

    @property
    def primary_phone(self):
        """Return the primary PhoneNumber instance if available."""
        for phone in self.phone_numbers.all():
            if phone.is_primary:
                return phone
        return None

    def __str__(self) -> str:
        return f"{self.full_name} (book={self.book_id})"


class PhoneNumber(models.Model):
    """Labeled telephone number belonging to a Contact with one-primary invariant."""

    class PhoneType(models.TextChoices):
        MOBILE = "Mobile", "Mobile"
        HOME = "Home", "Home"
        WORK = "Work", "Work"
        MAIN = "Main", "Main"
        OTHER = "Other", "Other"

    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name="phone_numbers",
    )
    phone_number = models.CharField(max_length=20)
    phone_type = models.CharField(
        max_length=20,
        choices=PhoneType.choices,
        default=PhoneType.MOBILE,
    )
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = "contacts_phonenumber"
        ordering = ["-is_primary", "id"]
        constraints = [
            models.CheckConstraint(
                condition=GreaterThanOrEqual(Length(Trim("phone_number")), 8),
                name="chk_phonenumber_min_length",
            ),
            models.CheckConstraint(
                condition=models.Q(phone_type__in=["Mobile", "Home", "Work", "Main", "Other"]),
                name="chk_phonenumber_type_valid",
            ),
            models.UniqueConstraint(
                fields=["contact"],
                condition=models.Q(is_primary=True),
                name="idx_unique_primary_phone_per_contact",
            ),
        ]
        indexes = [
            models.Index(fields=["contact"], name="idx_phonenumber_contact_id"),
            GinIndex(
                fields=["phone_number"],
                opclasses=["gin_trgm_ops"],
                name="idx_phonenumber_digits_trgm",
            ),
        ]

    def __str__(self) -> str:
        primary_label = " [Primary]" if self.is_primary else ""
        return f"{self.phone_number} ({self.phone_type}){primary_label}"
