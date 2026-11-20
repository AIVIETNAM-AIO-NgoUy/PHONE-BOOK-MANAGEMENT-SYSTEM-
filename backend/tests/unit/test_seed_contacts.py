"""Unit tests for the seed_contacts management command (T101)."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.db.models import Count, Q

from apps.accounts.models import CustomUser
from apps.contacts.models import Contact, PhoneNumber
from apps.contacts.services import SearchOptimizationService
from apps.favorites.models import FavoriteList


@pytest.mark.django_db
class TestSeedContactsCommand:
    """Verify batched synthetic seeding invariants, 2.5x phones, and --reset behavior."""

    def test_seed_contacts_creates_20_contacts_50_phones_and_primary_invariant(self):
        stdout = StringIO()
        call_command(
            "seed_contacts",
            user="seed_test_user",
            password="SeedUser2026!",
            count=20,
            batch_size=7,
            stdout=stdout,
        )

        user = CustomUser.objects.get(username="seed_test_user")
        assert hasattr(user, "contact_book")
        assert FavoriteList.objects.filter(book=user.contact_book).exists()

        contacts = Contact.objects.filter(book=user.contact_book)
        phones = PhoneNumber.objects.filter(contact__book=user.contact_book)

        assert contacts.count() == 20
        assert phones.count() == 50

        primary_counts = contacts.annotate(
            primary_count=Count("phone_numbers", filter=Q(phone_numbers__is_primary=True))
        ).values_list("primary_count", flat=True)
        assert list(primary_counts) == [1] * 20

        valid_types = {choice for choice, _ in PhoneNumber.PhoneType.choices}
        for phone in phones:
            assert 8 <= len(phone.phone_number.strip()) <= 20
            assert phone.phone_type in valid_types

        for contact in contacts:
            assert contact.full_name.strip()
            assert contact.notes is None or len(contact.notes) <= 1000

        smith_hits = SearchOptimizationService.search_contacts(
            book=user.contact_book,
            query="Smith",
        )
        assert smith_hits.count() >= 1
        output_text = stdout.getvalue()
        assert "Seeded 20 contacts and 50 phone numbers" in output_text
        assert "Verification query 'Smith':" in output_text

    def test_seed_contacts_reset_replaces_only_target_user_contacts(self, user_factory):
        other_user = user_factory(username="other_seed_user", email="other_seed@example.com")
        other_contact = Contact.objects.create(
            book=other_user.contact_book,
            full_name="Preserved Contact",
        )
        PhoneNumber.objects.create(
            contact=other_contact,
            phone_number="0901234567",
            phone_type=PhoneNumber.PhoneType.MOBILE,
            is_primary=True,
        )

        call_command(
            "seed_contacts",
            user="reset_target_user",
            count=20,
            batch_size=10,
            stdout=StringIO(),
        )
        target_user = CustomUser.objects.get(username="reset_target_user")
        assert Contact.objects.filter(book=target_user.contact_book).count() == 20
        assert PhoneNumber.objects.filter(contact__book=target_user.contact_book).count() == 50

        call_command(
            "seed_contacts",
            user="reset_target_user",
            count=10,
            batch_size=5,
            reset=True,
            stdout=StringIO(),
        )

        assert Contact.objects.filter(book=target_user.contact_book).count() == 10
        assert PhoneNumber.objects.filter(contact__book=target_user.contact_book).count() == 25
        assert Contact.objects.filter(book=other_user.contact_book).count() == 1
