"""Forms and inline formsets for Contact and PhoneNumber management."""

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.http import QueryDict
from django.urls import reverse_lazy

from apps.contacts.models import Contact, PhoneNumber
from apps.contacts.services import DuplicateDetectionService
from apps.core import utils as core_utils
from apps.groups.models import Group

ERR_CONTACT_NAME_REQUIRED = "Full name is required."
ERR_CONTACT_NAME_DUPLICATE = "A contact with this full name already exists."
ERR_CONTACT_PHONE_REQUIRED = "At least one primary phone number is required."
ERR_CONTACT_PHONE_DUPLICATE = "This phone number already belongs to another contact."
ERR_CONTACT_PHONE_DUPLICATE_IN_CONTACT = (
    "Duplicate phone numbers are not allowed for the same contact."
)
ERR_CONTACT_PRIMARY_EXACT = "Exactly one phone number must be marked as primary."
ERR_CONTACT_NOTES_TOO_LONG = "Notes cannot exceed 1,000 characters."


class ContactForm(forms.ModelForm):
    """Form for creating and editing a Contact record."""

    full_name = forms.CharField(
        max_length=150,
        required=True,
        error_messages={"required": ERR_CONTACT_NAME_REQUIRED},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. Alice Smith",
                "autocomplete": "name",
                "hx-post": reverse_lazy("contacts:check_duplicate"),
                "hx-trigger": "blur",
                "hx-target": "#duplicate-warning-container",
                "hx-swap": "innerHTML",
                "hx-include": "#contact-lifecycle-form",
            }
        ),
    )
    email = forms.EmailField(
        max_length=254,
        required=False,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "alice@example.org",
                "autocomplete": "email",
            }
        ),
    )
    address = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Residential address",
            }
        ),
    )
    work_address = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Company or workplace address",
            }
        ),
    )
    birthday = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "form-control",
            }
        ),
    )
    notes = forms.CharField(
        max_length=1000,
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-textarea",
                "rows": 3,
                "maxlength": "1000",
                "placeholder": "Personal notes (up to 1,000 characters)...",
            }
        ),
    )
    avatar = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": ".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp",
            }
        ),
    )
    group_ids = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(),
        required=False,
        label="Groups",
        widget=forms.CheckboxSelectMultiple(attrs={"class": "group-checkbox-input"}),
    )

    class Meta:
        model = Contact
        fields = [
            "full_name",
            "email",
            "address",
            "work_address",
            "birthday",
            "notes",
        ]

    def __init__(self, *args, book=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.book = book
        if book is not None:
            self.fields["group_ids"].queryset = Group.objects.filter(book=book).order_by(
                "group_name", "id"
            )
        if self.instance is not None and self.instance.pk is not None:
            if "group_ids" not in self.initial:
                self.initial["group_ids"] = list(
                    self.instance.contact_groups.values_list("group_id", flat=True)
                )
            if self.instance.avatar and "avatar" not in self.initial:
                self.initial["avatar"] = core_utils.AvatarInitialRef(self.instance.avatar)

    def clean_full_name(self) -> str:
        cleaned = core_utils.sanitize_contact_text(
            self.cleaned_data.get("full_name"),
            collapse_newlines=True,
        )
        if not cleaned:
            raise ValidationError(ERR_CONTACT_NAME_REQUIRED, code="name_required")
        if self.book is not None:
            exclude_id = self.instance.pk if self.instance and self.instance.pk else None
            duplicates = DuplicateDetectionService.find_duplicates(
                book=self.book,
                full_name=cleaned,
                exclude_contact_id=exclude_id,
            )
            if any(candidate.has_name_match for candidate in duplicates):
                raise ValidationError(ERR_CONTACT_NAME_DUPLICATE, code="duplicate_name")
        return cleaned

    def clean_email(self) -> str | None:
        raw_email = self.cleaned_data.get("email")
        if not raw_email:
            return None
        cleaned = raw_email.strip().lower()
        return cleaned or None

    def clean_address(self) -> str | None:
        return core_utils.sanitize_contact_text(
            self.cleaned_data.get("address"), collapse_newlines=True
        )

    def clean_work_address(self) -> str | None:
        return core_utils.sanitize_contact_text(
            self.cleaned_data.get("work_address"),
            collapse_newlines=True,
        )

    def clean_notes(self) -> str | None:
        cleaned = core_utils.sanitize_contact_text(
            self.cleaned_data.get("notes"), collapse_newlines=False
        )
        if cleaned and len(cleaned) > 1000:
            raise ValidationError(ERR_CONTACT_NOTES_TOO_LONG, code="notes_too_long")
        return cleaned

    def clean_avatar(self):
        avatar_file = self.cleaned_data.get("avatar")
        if avatar_file is False:
            return False
        if not avatar_file or isinstance(avatar_file, core_utils.AvatarInitialRef):
            return None
        core_utils.validate_image_upload(avatar_file)
        return avatar_file


class PhoneNumberForm(forms.ModelForm):
    """Inline form for an individual PhoneNumber record."""

    phone_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. 0901234567 or +84901234567",
                "hx-post": reverse_lazy("contacts:check_duplicate"),
                "hx-trigger": "blur",
                "hx-target": "#duplicate-warning-container",
                "hx-swap": "innerHTML",
                "hx-include": "#contact-lifecycle-form",
            }
        ),
    )
    phone_type = forms.ChoiceField(
        choices=PhoneNumber.PhoneType.choices,
        initial=PhoneNumber.PhoneType.MOBILE,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    is_primary = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "phone-primary-checkbox"}),
    )

    class Meta:
        model = PhoneNumber
        fields = ["phone_number", "phone_type", "is_primary"]

    def clean_phone_type(self) -> str:
        value = self.cleaned_data.get("phone_type")
        return value or PhoneNumber.PhoneType.MOBILE

    def clean(self) -> dict:
        cleaned_data = super().clean()
        if cleaned_data.get("DELETE"):
            return cleaned_data

        raw_phone = cleaned_data.get("phone_number") or ""
        if not str(raw_phone).strip():
            if self.instance and self.instance.pk:
                self.add_error(
                    "phone_number",
                    ValidationError(ERR_CONTACT_PHONE_REQUIRED, code="phone_required"),
                )
            else:
                cleaned_data["phone_number"] = ""
            return cleaned_data

        try:
            cleaned_data["phone_number"] = core_utils.normalize_phone_number(raw_phone)
        except ValidationError as exc:
            self.add_error("phone_number", exc)

        return cleaned_data


class BasePhoneNumberInlineFormSet(BaseInlineFormSet):
    """Inline formset enforcing >= 1 phone number, uniqueness, and exactly one primary flag."""

    def __init__(self, *args, book=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if book is None and self.instance is not None and getattr(self.instance, "book_id", None):
            book = self.instance.book
        self.book = book

    def clean(self) -> None:
        super().clean()

        active_valid_forms = []
        active_error_forms = []

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if self.can_delete and self._should_delete_form(form):
                continue

            has_phone_error = "phone_number" in form.errors
            phone_val = form.cleaned_data.get("phone_number") or ""

            if not phone_val and not has_phone_error:
                if not form.instance.pk:
                    form.cleaned_data["DELETE"] = True
                continue

            if has_phone_error:
                active_error_forms.append(form)
            else:
                active_valid_forms.append(form)

        total_active = len(active_valid_forms) + len(active_error_forms)
        if total_active == 0:
            raise ValidationError(ERR_CONTACT_PHONE_REQUIRED, code="phone_required")

        if any(self.errors):
            return

        seen_keys: set[str] = set()
        active_phone_numbers: list[str] = []
        for form in active_valid_forms:
            phone_val = form.cleaned_data.get("phone_number") or ""
            keys = DuplicateDetectionService.canonical_phone_keys(phone_val) or {
                phone_val.strip().casefold()
            }
            if keys & seen_keys:
                form.add_error(
                    "phone_number",
                    ValidationError(
                        ERR_CONTACT_PHONE_DUPLICATE_IN_CONTACT,
                        code="duplicate_phone_in_contact",
                    ),
                )
            else:
                seen_keys.update(keys)
                active_phone_numbers.append(phone_val)

        if self.book is not None and active_phone_numbers:
            exclude_id = self.instance.pk if self.instance and self.instance.pk else None
            duplicates = DuplicateDetectionService.find_duplicates(
                book=self.book,
                phone_numbers=active_phone_numbers,
                exclude_contact_id=exclude_id,
            )
            existing_keys: set[str] = set()
            for candidate in duplicates:
                for matched_phone in candidate.matched_phones:
                    existing_keys.update(
                        DuplicateDetectionService.canonical_phone_keys(matched_phone)
                        or {matched_phone.strip().casefold()}
                    )
            if existing_keys:
                for form in active_valid_forms:
                    phone_val = form.cleaned_data.get("phone_number") or ""
                    keys = DuplicateDetectionService.canonical_phone_keys(phone_val) or {
                        phone_val.strip().casefold()
                    }
                    if keys & existing_keys:
                        form.add_error(
                            "phone_number",
                            ValidationError(ERR_CONTACT_PHONE_DUPLICATE, code="duplicate_phone"),
                        )

        if any(self.errors):
            return

        primary_count = sum(1 for form in active_valid_forms if form.cleaned_data.get("is_primary"))
        if primary_count != 1:
            raise ValidationError(ERR_CONTACT_PRIMARY_EXACT, code="primary_phone_required")


PhoneNumberInlineFormSet = inlineformset_factory(
    Contact,
    PhoneNumber,
    form=PhoneNumberForm,
    formset=BasePhoneNumberInlineFormSet,
    extra=1,
    can_delete=True,
)

PhoneNumberEditInlineFormSet = inlineformset_factory(
    Contact,
    PhoneNumber,
    form=PhoneNumberForm,
    formset=BasePhoneNumberInlineFormSet,
    extra=0,
    can_delete=True,
)


def normalize_contact_post_data(
    post_data: QueryDict,
    *,
    prefix: str = "phone_numbers",
    instance: Contact | None = None,
) -> QueryDict:
    """Translate simplified contract payloads into Django inline formset POST data."""
    if f"{prefix}-TOTAL_FORMS" in post_data:
        return post_data

    normalized = post_data.copy()
    existing_phones = list(instance.phone_numbers.order_by("id")) if instance is not None else []
    rows: list[dict[str, str]] = []

    for phone in existing_phones:
        rows.append(
            {
                "id": str(phone.pk),
                "contact": str(instance.pk),
                "phone_number": phone.phone_number,
                "phone_type": phone.phone_type,
                "DELETE": "on",
            }
        )

    primary_phone = post_data.get("primary_phone")
    primary_phone_type = post_data.get("primary_phone_type") or PhoneNumber.PhoneType.MOBILE
    if primary_phone is not None and str(primary_phone).strip() != "":
        rows.append(
            {
                "phone_number": str(primary_phone),
                "phone_type": primary_phone_type,
                "is_primary": "on",
            }
        )

    secondary_phones = post_data.getlist("secondary_phones")
    secondary_types = post_data.getlist("secondary_phone_types")
    for idx, sec_phone in enumerate(secondary_phones):
        if str(sec_phone).strip() == "":
            continue
        sec_type = (
            secondary_types[idx]
            if idx < len(secondary_types) and secondary_types[idx]
            else PhoneNumber.PhoneType.MOBILE
        )
        rows.append(
            {
                "phone_number": str(sec_phone),
                "phone_type": sec_type,
            }
        )

    normalized[f"{prefix}-TOTAL_FORMS"] = str(len(rows))
    normalized[f"{prefix}-INITIAL_FORMS"] = str(len(existing_phones))
    normalized[f"{prefix}-MIN_NUM_FORMS"] = "0"
    normalized[f"{prefix}-MAX_NUM_FORMS"] = "1000"

    for idx, row in enumerate(rows):
        for key, val in row.items():
            normalized[f"{prefix}-{idx}-{key}"] = val

    return normalized
