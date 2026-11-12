"""Forms for custom group management and member assignment (T080)."""

from django import forms
from django.core.exceptions import ValidationError

from apps.contacts.models import Contact
from apps.core.utils import sanitize_contact_text
from apps.groups.models import Group

ERR_GROUP_NAME_REQUIRED = "Group name cannot be empty."
ERR_GROUP_NAME_TOO_LONG = f"Group name cannot exceed {Group.MAX_NAME_LENGTH} characters."
ERR_GROUP_NAME_DUPLICATE = "You already have a group with this name. Please choose a distinct name."
ERR_GROUP_DESCRIPTION_TOO_LONG = (
    f"Description cannot exceed {Group.MAX_DESCRIPTION_LENGTH} characters."
)
ERR_GROUP_CONTACT_REQUIRED = "Please select a valid contact."
ERR_GROUP_CONTACT_NOT_FOUND = "Contact not found in your contact book."


class GroupForm(forms.ModelForm):
    """Form for creating and editing a Group scoped to a user's ContactBook."""

    group_name = forms.CharField(
        max_length=Group.MAX_NAME_LENGTH,
        required=True,
        error_messages={
            "required": ERR_GROUP_NAME_REQUIRED,
            "max_length": ERR_GROUP_NAME_TOO_LONG,
        },
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. Coworkers, Family, Gym Buddies",
                "maxlength": str(Group.MAX_NAME_LENGTH),
                "autocomplete": "off",
            }
        ),
    )
    description = forms.CharField(
        max_length=Group.MAX_DESCRIPTION_LENGTH,
        required=False,
        error_messages={
            "max_length": ERR_GROUP_DESCRIPTION_TOO_LONG,
        },
        widget=forms.Textarea(
            attrs={
                "class": "form-textarea",
                "rows": 3,
                "maxlength": str(Group.MAX_DESCRIPTION_LENGTH),
                "placeholder": "Optional group description (up to 500 characters)...",
            }
        ),
    )

    class Meta:
        model = Group
        fields = ["group_name", "description"]

    def __init__(self, *args, book=None, exclude_group_id: int | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.book = book
        if exclude_group_id is not None:
            self.exclude_group_id = exclude_group_id
        elif self.instance is not None and self.instance.pk is not None:
            self.exclude_group_id = self.instance.pk
        else:
            self.exclude_group_id = None

    def clean_group_name(self) -> str:
        cleaned = sanitize_contact_text(
            self.cleaned_data.get("group_name"),
            collapse_newlines=True,
        )
        if not cleaned:
            raise ValidationError(ERR_GROUP_NAME_REQUIRED, code="ERR_GROUP_NAME_REQUIRED")
        if len(cleaned) > Group.MAX_NAME_LENGTH:
            raise ValidationError(ERR_GROUP_NAME_TOO_LONG, code="group_name_too_long")

        if self.book is not None:
            qs = Group.objects.filter(book=self.book, group_name__iexact=cleaned)
            if self.exclude_group_id is not None:
                qs = qs.exclude(pk=self.exclude_group_id)
            if qs.exists():
                raise ValidationError(ERR_GROUP_NAME_DUPLICATE, code="ERR_GROUP_NAME_DUPLICATE")

        return cleaned

    def clean_description(self) -> str | None:
        cleaned = sanitize_contact_text(
            self.cleaned_data.get("description"),
            collapse_newlines=False,
        )
        if cleaned and len(cleaned) > Group.MAX_DESCRIPTION_LENGTH:
            raise ValidationError(ERR_GROUP_DESCRIPTION_TOO_LONG, code="description_too_long")
        return cleaned


class GroupMemberAddForm(forms.Form):
    """Validate contact_id and scope ownership to the authenticated user's ContactBook."""

    contact_id = forms.IntegerField(
        min_value=1,
        required=True,
        error_messages={
            "required": ERR_GROUP_CONTACT_REQUIRED,
            "invalid": ERR_GROUP_CONTACT_REQUIRED,
            "min_value": ERR_GROUP_CONTACT_REQUIRED,
        },
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, book=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.book = book
        self.resolved_contact: Contact | None = None

    def clean_contact_id(self) -> int:
        contact_id = self.cleaned_data["contact_id"]
        if self.book is not None:
            contact = Contact.objects.filter(pk=contact_id, book=self.book).first()
            if contact is None:
                raise ValidationError(ERR_GROUP_CONTACT_NOT_FOUND, code="contact_not_found")
            self.resolved_contact = contact
        return contact_id
