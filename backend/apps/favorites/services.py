"""Domain services for favorite list management and interaction frequency tracking (T070)."""

from collections.abc import Iterable

from django.db import IntegrityError, transaction
from django.db.models import F, QuerySet
from django.utils import timezone

from apps.contacts.models import Contact, ContactBook
from apps.favorites.models import FavoriteItem, FavoriteList

ERR_FAVORITE_ALREADY_EXISTS = "This contact is already in your favorites list."
ERR_FAVORITE_NOT_FOUND = "Favorite item not found."
ERR_CONTACT_NOT_FOUND = "Contact not found."


class FavoriteDuplicateError(ValueError):
    """Raised when attempting to add a contact already present in the FavoriteList."""


class FavoriteNotFoundError(LookupError):
    """Raised when a Contact or FavoriteItem does not exist in the user's scope."""


class FavoriteService:
    """Tenant-scoped favorite list operations: list/sort, add, remove, and priority update."""

    DEFAULT_SORT_KEY = "priority"
    SORT_OPTIONS = ("priority", "frequency", "name")
    PRIORITY_CHOICES = tuple(range(FavoriteItem.MIN_PRIORITY, FavoriteItem.MAX_PRIORITY + 1))

    @classmethod
    def get_or_create_favorite_list(cls, user) -> FavoriteList:
        """Resolve the authenticated user's isolated FavoriteList container."""
        book, _ = ContactBook.objects.get_or_create(user=user)
        favorite_list, _ = FavoriteList.objects.get_or_create(book=book)
        return favorite_list

    @classmethod
    def resolve_sort_key(cls, raw_sort: str | None) -> str:
        """Return a valid sort key, defaulting to 'priority' for missing/unknown values."""
        if raw_sort in cls.SORT_OPTIONS:
            return raw_sort
        return cls.DEFAULT_SORT_KEY

    @classmethod
    def get_order_by(cls, sort_key: str | None) -> tuple:
        """Return deterministic ORM order_by expressions for the resolved sort key."""
        resolved = cls.resolve_sort_key(sort_key)
        if resolved == "frequency":
            return (
                F("contact__interaction_count").desc(),
                F("contact__last_contacted_at").desc(nulls_last=True),
                "contact__full_name",
                "id",
            )
        if resolved == "name":
            return ("contact__full_name", "priority", "id")
        return ("priority", "contact__full_name", "id")

    @classmethod
    def list_favorites(
        cls,
        *,
        favorite_list: FavoriteList,
        sort_key: str | None = DEFAULT_SORT_KEY,
    ) -> QuerySet[FavoriteItem]:
        """Return favorite items for a FavoriteList with prefetched contact and phone numbers."""
        return (
            FavoriteItem.objects.filter(favorite_list=favorite_list)
            .select_related("contact")
            .prefetch_related("contact__phone_numbers")
            .order_by(*cls.get_order_by(sort_key))
        )

    @classmethod
    def get_favorite_contact_ids(
        cls,
        *,
        favorite_list: FavoriteList,
        contact_ids: Iterable[int] | None = None,
    ) -> set[int]:
        """Return the set of contact IDs currently bookmarked in the given FavoriteList."""
        qs = FavoriteItem.objects.filter(favorite_list=favorite_list)
        if contact_ids is not None:
            id_list = list(contact_ids)
            if not id_list:
                return set()
            qs = qs.filter(contact_id__in=id_list)
        return set(qs.values_list("contact_id", flat=True))

    @classmethod
    @transaction.atomic
    def add_favorite(
        cls,
        *,
        book: ContactBook,
        contact_id: int,
        priority: int = FavoriteItem.DEFAULT_PRIORITY,
    ) -> FavoriteItem:
        """Bookmark a contact in the user's FavoriteList while enforcing uniqueness."""
        contact = Contact.objects.select_for_update().filter(pk=contact_id, book=book).first()
        if contact is None:
            raise FavoriteNotFoundError(ERR_CONTACT_NOT_FOUND)

        favorite_list, _ = FavoriteList.objects.get_or_create(book=book)
        if FavoriteItem.objects.filter(favorite_list=favorite_list, contact=contact).exists():
            raise FavoriteDuplicateError(ERR_FAVORITE_ALREADY_EXISTS)

        try:
            with transaction.atomic():
                return FavoriteItem.objects.create(
                    favorite_list=favorite_list,
                    contact=contact,
                    priority=priority,
                )
        except IntegrityError as exc:
            sqlstate = getattr(getattr(exc, "__cause__", None), "sqlstate", None)
            if sqlstate == "23503" or not Contact.objects.filter(pk=contact_id, book=book).exists():
                raise FavoriteNotFoundError(ERR_CONTACT_NOT_FOUND) from exc
            raise FavoriteDuplicateError(ERR_FAVORITE_ALREADY_EXISTS) from exc

    @classmethod
    @transaction.atomic
    def remove_favorite(cls, *, book: ContactBook, contact_id: int) -> None:
        """Remove a FavoriteItem without ever deleting the underlying Contact."""
        favorite_list, _ = FavoriteList.objects.get_or_create(book=book)
        deleted_count, _ = FavoriteItem.objects.filter(
            favorite_list=favorite_list,
            contact_id=contact_id,
        ).delete()
        if deleted_count == 0:
            raise FavoriteNotFoundError(ERR_FAVORITE_NOT_FOUND)

    @classmethod
    @transaction.atomic
    def update_priority(cls, *, book: ContactBook, item_id: int, priority: int) -> FavoriteItem:
        """Update the priority rank [1..10] for a FavoriteItem owned by book."""
        favorite_list, _ = FavoriteList.objects.get_or_create(book=book)
        item = (
            FavoriteItem.objects.select_for_update()
            .select_related("contact")
            .filter(pk=item_id, favorite_list=favorite_list)
            .first()
        )
        if item is None:
            raise FavoriteNotFoundError(ERR_FAVORITE_NOT_FOUND)

        item.priority = priority
        item.save(update_fields=["priority"])
        return item


class FrequencyTrackingService:
    """Atomic tracking of user-initiated contact interactions for frequency sorting (FR-025)."""

    @classmethod
    @transaction.atomic
    def record_interaction(cls, *, book: ContactBook, contact_id: int) -> Contact:
        """Atomically increment interaction_count and stamp last_contacted_at."""
        now = timezone.now()
        updated = Contact.objects.filter(pk=contact_id, book=book).update(
            interaction_count=F("interaction_count") + 1,
            last_contacted_at=now,
        )
        if updated == 0:
            raise FavoriteNotFoundError(ERR_CONTACT_NOT_FOUND)

        return Contact.objects.get(pk=contact_id, book=book)
