"""Forms for favorite priority assignment and updates (T069)."""

from django import forms

from apps.favorites.models import FavoriteItem

ERR_FAVORITE_INVALID_PRIORITY = "Priority must be an integer between 1 and 10."


class FavoritePriorityForm(forms.Form):
    """Validate favorite priority integer rank within [1, 10] (FR-023)."""

    priority = forms.IntegerField(
        min_value=FavoriteItem.MIN_PRIORITY,
        max_value=FavoriteItem.MAX_PRIORITY,
        required=True,
        error_messages={
            "required": ERR_FAVORITE_INVALID_PRIORITY,
            "invalid": ERR_FAVORITE_INVALID_PRIORITY,
            "min_value": ERR_FAVORITE_INVALID_PRIORITY,
            "max_value": ERR_FAVORITE_INVALID_PRIORITY,
        },
        widget=forms.NumberInput(
            attrs={
                "min": FavoriteItem.MIN_PRIORITY,
                "max": FavoriteItem.MAX_PRIORITY,
                "class": "form-control",
            }
        ),
    )
