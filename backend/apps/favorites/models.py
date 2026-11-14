"""FavoriteList and FavoriteItem models for prioritized favorite contacts."""

from django.db import models
from django.db.models.functions import Now


class FavoriteList(models.Model):
    """Dedicated favorites list belonging to a single ContactBook."""

    book = models.OneToOneField(
        "contacts.ContactBook",
        on_delete=models.CASCADE,
        related_name="favorite_list",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "favorites_favoritelist"

    def __str__(self) -> str:
        return f"FavoriteList(book={self.book_id})"


class FavoriteItem(models.Model):
    """Individual contact entry bookmarked as favorite with priority rank (1-10)."""

    MIN_PRIORITY = 1
    MAX_PRIORITY = 10
    DEFAULT_PRIORITY = 5

    favorite_list = models.ForeignKey(
        FavoriteList,
        on_delete=models.CASCADE,
        related_name="items",
    )
    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.CASCADE,
        related_name="favorite_items",
    )
    priority = models.IntegerField(default=DEFAULT_PRIORITY)
    added_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "favorites_favoriteitem"
        ordering = ["priority", "contact__full_name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(priority__gte=1, priority__lte=10),
                name="chk_favorite_priority_range",
            ),
            models.UniqueConstraint(
                fields=["favorite_list", "contact"],
                name="uq_favoriteitem_list_contact",
            ),
        ]
        indexes = [
            models.Index(fields=["favorite_list"], name="idx_favoriteitem_list_id"),
            models.Index(fields=["contact"], name="idx_favoriteitem_contact_id"),
            models.Index(fields=["favorite_list", "priority"], name="idx_favoriteitem_priority"),
        ]

    def __str__(self) -> str:
        return (
            f"FavoriteItem(list={self.favorite_list_id}, "
            f"contact={self.contact_id}, priority={self.priority})"
        )
