"""Unit tests for Contact, PhoneNumber, utils, and contact forms/formsets (T043)."""

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.http import QueryDict

from apps.contacts import forms as contact_forms
from apps.contacts.models import Contact, ContactBook, PhoneNumber
from apps.core.utils import normalize_phone_number, sanitize_contact_text, validate_image_upload

VALID_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x00IEND\xaeB`\x82"
)
VALID_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
VALID_WEBP = b"RIFF\x18\x00\x00\x00WEBP" + b"\x00" * 16


@pytest.mark.django_db
class TestContactAndPhoneNumberModels:
    """Unit tests for Contact and PhoneNumber DB constraints, partial unique index, and cascade."""

    def test_contact_check_constraints_enforced_by_postgresql(self, user_factory):
        user = user_factory(username="db_const_u", email="dbconst@example.com")
        book = user.contact_book

        # Whitespace-only full_name fails chk_contact_full_name_non_empty
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Contact.objects.create(book=book, full_name="   ")

        # Notes > 1000 characters fails chk_contact_notes_max_length
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Contact.objects.create(book=book, full_name="Long Notes", notes="a" * 1001)

        # Negative interaction_count fails chk_contact_interaction_non_negative
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Contact.objects.create(book=book, full_name="Neg Count", interaction_count=-1)

        # Exactly 1000 chars and 0 interaction_count succeed
        valid_contact = Contact.objects.create(
            book=book, full_name="Valid Contact", notes="a" * 1000, interaction_count=0
        )
        assert str(valid_contact) == f"Valid Contact (book={book.pk})"
        assert valid_contact.primary_phone is None

    def test_phonenumber_check_constraints_and_partial_unique_index(self, user_factory):
        user = user_factory(username="phone_db_u", email="phonedb@example.com")
        contact = Contact.objects.create(book=user.contact_book, full_name="Phone Target")

        # Less than 8 trimmed characters fails chk_phonenumber_min_length
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                PhoneNumber.objects.create(
                    contact=contact, phone_number=" 1234567 ", phone_type="Mobile"
                )

        # Invalid phone_type fails chk_phonenumber_type_valid
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                PhoneNumber.objects.create(
                    contact=contact, phone_number="0901234567", phone_type="Pager"
                )

        # First primary phone succeeds; second primary phone on same contact fails
        p1 = PhoneNumber.objects.create(
            contact=contact, phone_number="0901234567", phone_type="Mobile", is_primary=True
        )
        assert str(p1) == "0901234567 (Mobile) [Primary]"
        assert contact.primary_phone == p1

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                PhoneNumber.objects.create(
                    contact=contact,
                    phone_number="0912345678",
                    phone_type="Work",
                    is_primary=True,
                )

        # Multiple secondary (is_primary=False) numbers on same contact succeed
        p2 = PhoneNumber.objects.create(
            contact=contact, phone_number="0912345678", phone_type="Work", is_primary=False
        )
        p3 = PhoneNumber.objects.create(
            contact=contact, phone_number="02838229999", phone_type="Home", is_primary=False
        )
        assert str(p2) == "0912345678 (Work)"
        assert str(p3) == "02838229999 (Home)"
        assert contact.phone_numbers.count() == 3

    def test_contact_deletion_cascades_to_phonenumbers_preserving_contactbook(self, user_factory):
        user = user_factory(username="casc_u", email="casc@example.com")
        book = user.contact_book
        contact = Contact.objects.create(book=book, full_name="Cascade Target")
        PhoneNumber.objects.create(
            contact=contact, phone_number="0901111222", phone_type="Mobile", is_primary=True
        )
        PhoneNumber.objects.create(
            contact=contact, phone_number="0903333444", phone_type="Work", is_primary=False
        )

        contact_id = contact.pk
        contact.delete()

        assert not PhoneNumber.objects.filter(contact_id=contact_id).exists()
        assert ContactBook.objects.filter(pk=book.pk).exists()


class TestCoreUtils:
    """Unit tests for phone normalization, text sanitization, and avatar validation."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0901234567", "0901234567"),
            ("  090 123-4567 ", "0901234567"),
            ("1900 1234", "19001234"),
            ("+84 (90) 123.4567", "+84901234567"),
            ("+1-555-123-4567", "+15551234567"),
            ("12345678901234567890", "12345678901234567890"),
        ],
    )
    def test_normalize_phone_number_valid_formats(self, raw, expected):
        assert normalize_phone_number(raw) == expected

    @pytest.mark.parametrize(
        "bad_raw",
        [
            None,
            "",
            "   ",
            "1234567",
            "+123456",
            "+084901234567",
            "090-abc-4567",
            "0901234567*1",
            "123456789012345678901",
            "+12345678901234567890",
        ],
    )
    def test_normalize_phone_number_invalid_formats_raise(self, bad_raw):
        with pytest.raises(ValidationError, match="between 8 and 20 digits"):
            normalize_phone_number(bad_raw)

    def test_sanitize_contact_text_trims_and_strips_control_chars(self):
        assert sanitize_contact_text(None) is None
        assert sanitize_contact_text("   \t\n  ") is None
        assert (
            sanitize_contact_text("  Nguyễn\x00 Văn A\r\n ", collapse_newlines=True)
            == "Nguyễn Văn A"
        )
        assert sanitize_contact_text("Line 1\r\nLine 2\x07", collapse_newlines=False) == (
            "Line 1\nLine 2"
        )

    def test_validate_image_upload_accepts_valid_and_rejects_bad_files(self):
        validate_image_upload(None)
        validate_image_upload(SimpleUploadedFile("ok.png", VALID_PNG, content_type="image/png"))
        validate_image_upload(SimpleUploadedFile("ok.jpg", VALID_JPEG, content_type="image/jpeg"))
        validate_image_upload(SimpleUploadedFile("ok.webp", VALID_WEBP, content_type="image/webp"))

        with pytest.raises(ValidationError, match="under 2MB"):
            validate_image_upload(
                SimpleUploadedFile(
                    "huge.png",
                    VALID_PNG + b"\x00" * (2 * 1024 * 1024 + 1),
                    content_type="image/png",
                )
            )

        with pytest.raises(ValidationError, match="PNG, JPG, WEBP"):
            validate_image_upload(
                SimpleUploadedFile("bad.svg", b"<svg></svg>", content_type="image/svg+xml")
            )

        with pytest.raises(ValidationError, match="PNG, JPG, WEBP"):
            validate_image_upload(
                SimpleUploadedFile("fake.webp", b"NOTWEBP", content_type="image/webp")
            )


@pytest.mark.django_db
class TestContactFormsAndFormsets:
    """Unit tests for ContactForm, PhoneNumberInlineFormSet, and payload normalization."""

    def test_contact_form_rejects_whitespace_name_and_oversized_notes(self):
        form = contact_forms.ContactForm(data={"full_name": "   ", "notes": "x" * 1001})
        assert not form.is_valid()
        assert "full_name" in form.errors
        assert "notes" in form.errors

    def test_contact_form_normalizes_email_and_validates_avatar(self):
        bad_avatar = SimpleUploadedFile("bad.png", b"not-a-png", content_type="image/png")
        bad_form = contact_forms.ContactForm(
            data={"full_name": "  Jane Doe  ", "email": " JANE@Example.COM "},
            files={"avatar": bad_avatar},
        )
        assert not bad_form.is_valid()
        assert "avatar" in bad_form.errors

        good_avatar = SimpleUploadedFile("ok.png", VALID_PNG, content_type="image/png")
        good_form = contact_forms.ContactForm(
            data={"full_name": "  Jane Doe  ", "email": " JANE@Example.COM "},
            files={"avatar": good_avatar},
        )
        assert good_form.is_valid()
        assert good_form.cleaned_data["full_name"] == "Jane Doe"
        assert good_form.cleaned_data["email"] == "jane@example.com"

    def test_formset_requires_at_least_one_phone_and_exactly_one_primary(self):
        # 0 phones
        zero_formset = contact_forms.PhoneNumberInlineFormSet(
            data={
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "0",
                "phone_numbers-0-phone_number": "",
                "phone_numbers-0-phone_type": "Mobile",
            },
            prefix="phone_numbers",
        )
        assert not zero_formset.is_valid()
        assert "At least one primary phone number is required." in zero_formset.non_form_errors()

        # 2 primary phones
        two_primary = contact_forms.PhoneNumberInlineFormSet(
            data={
                "phone_numbers-TOTAL_FORMS": "2",
                "phone_numbers-INITIAL_FORMS": "0",
                "phone_numbers-0-phone_number": "0901234567",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
                "phone_numbers-1-phone_number": "0912345678",
                "phone_numbers-1-phone_type": "Work",
                "phone_numbers-1-is_primary": "on",
            },
            prefix="phone_numbers",
        )
        assert not two_primary.is_valid()
        assert "Exactly one phone number must be marked as primary." in (
            two_primary.non_form_errors()
        )

        # 0 primary phones when 1 number exists
        no_primary = contact_forms.PhoneNumberInlineFormSet(
            data={
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "0",
                "phone_numbers-0-phone_number": "0901234567",
                "phone_numbers-0-phone_type": "Mobile",
            },
            prefix="phone_numbers",
        )
        assert not no_primary.is_valid()
        assert "Exactly one phone number must be marked as primary." in (
            no_primary.non_form_errors()
        )

        # Valid 1 primary + 1 blank extra row succeeds
        with_blank_extra = contact_forms.PhoneNumberInlineFormSet(
            data={
                "phone_numbers-TOTAL_FORMS": "2",
                "phone_numbers-INITIAL_FORMS": "0",
                "phone_numbers-0-phone_number": "0901234567",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
                "phone_numbers-1-phone_number": "",
                "phone_numbers-1-phone_type": "Work",
            },
            prefix="phone_numbers",
        )
        assert with_blank_extra.is_valid()

    def test_edit_formset_rejects_deleting_all_phones(self, user_factory):
        user = user_factory(username="edit_fs_u", email="editfsu@example.com")
        contact = Contact.objects.create(book=user.contact_book, full_name="Edit Target")
        p1 = PhoneNumber.objects.create(
            contact=contact, phone_number="0901234567", phone_type="Mobile", is_primary=True
        )

        formset = contact_forms.PhoneNumberEditInlineFormSet(
            data={
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "1",
                "phone_numbers-0-id": str(p1.pk),
                "phone_numbers-0-contact": str(contact.pk),
                "phone_numbers-0-phone_number": "0901234567",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
                "phone_numbers-0-DELETE": "on",
            },
            instance=contact,
            prefix="phone_numbers",
        )
        assert not formset.is_valid()
        assert "At least one primary phone number is required." in formset.non_form_errors()

    def test_normalize_contact_post_data_and_root_redirect(self, authenticated_client, client):
        raw = QueryDict("full_name=Test&primary_phone=0901234567&secondary_phones=0912345678")
        normalized = contact_forms.normalize_contact_post_data(raw)
        assert normalized["phone_numbers-TOTAL_FORMS"] == "2"
        assert normalized["phone_numbers-0-is_primary"] == "on"
        assert normalized["phone_numbers-1-phone_number"] == "0912345678"

        anon_root = client.get("/")
        assert anon_root.status_code == 302
        assert anon_root.url == "/accounts/login/"

        auth_client, _ = authenticated_client(username="root_u", email="rootu@example.com")
        auth_root = auth_client.get("/")
        assert auth_root.status_code == 302
        assert auth_root.url == "/contacts/"
