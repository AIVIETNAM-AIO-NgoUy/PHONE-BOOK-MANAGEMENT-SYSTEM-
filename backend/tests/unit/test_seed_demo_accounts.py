"""Unit and integration tests for the seed_demo_accounts management command."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.db.models import Count, Q

from apps.accounts.models import CustomUser
from apps.accounts.services import authenticate_account
from apps.contacts.models import Contact, ContactBook, PhoneNumber
from apps.favorites.models import FavoriteItem, FavoriteList
from apps.groups.models import ContactGroup, Group


@pytest.mark.django_db
class TestSeedDemoAccountsCommand:
    """Verify demo/admin creation, sample data invariants, idempotency, and --reset."""

    def test_seed_demo_accounts_creates_users_and_sample_data(self, http_client):
        stdout = StringIO()
        call_command("seed_demo_accounts", stdout=stdout)

        demo = CustomUser.objects.get(username="demo")
        admin = CustomUser.objects.get(username="admin")

        assert demo.email == "demo@phonebook.local"
        assert demo.full_name == "Demo User"
        assert demo.role == CustomUser.Role.USER
        assert demo.account_status == CustomUser.AccountStatus.ACTIVE
        assert demo.is_active is True
        assert demo.is_admin is False
        assert demo.check_password("A@123")

        assert admin.email == "admin@phonebook.local"
        assert admin.full_name == "System Administrator"
        assert admin.role == CustomUser.Role.ADMIN
        assert admin.is_admin is True
        assert admin.is_staff is True
        assert admin.is_superuser is True
        assert admin.account_status == CustomUser.AccountStatus.ACTIVE
        assert admin.is_active is True
        assert admin.check_password("A@123")

        # Verify both authenticate_account and HTTP login succeed for demo and admin.
        assert authenticate_account("demo", "A@123").pk == demo.pk
        assert authenticate_account("admin", "A@123").pk == admin.pk

        for username in ("demo", "admin"):
            http_client.logout()
            response = http_client.post(
                "/accounts/login/",
                {"username_or_email": username, "password": "A@123"},
            )
            assert response.status_code == 302
            assert "_auth_user_id" in http_client.session

        # Verify ContactBook and FavoriteList containers exist for both accounts.
        demo_book = ContactBook.objects.get(user=demo)
        demo_fav_list = FavoriteList.objects.get(book=demo_book)
        admin_book = ContactBook.objects.get(user=admin)
        assert FavoriteList.objects.filter(book=admin_book).exists()

        # Verify 25 contacts, 1-3 phones each, and strict single-primary-phone invariant.
        contacts = Contact.objects.filter(book=demo_book)
        assert contacts.count() == 25

        primary_counts = contacts.annotate(
            primary_count=Count("phone_numbers", filter=Q(phone_numbers__is_primary=True)),
            total_count=Count("phone_numbers"),
        )
        valid_types = {choice for choice, _ in PhoneNumber.PhoneType.choices}
        for contact in primary_counts:
            assert contact.primary_count == 1
            assert 1 <= contact.total_count <= 3
            assert contact.full_name.strip()
            assert contact.notes is None or len(contact.notes) <= 1000

        phones = PhoneNumber.objects.filter(contact__book=demo_book)
        for phone in phones:
            assert 8 <= len(phone.phone_number.strip()) <= 20
            assert phone.phone_type in valid_types

        assert contacts.filter(birthday__isnull=False).exists()
        assert contacts.filter(email__isnull=False).exists()
        assert contacts.filter(work_address__isnull=False).exists()
        assert contacts.filter(interaction_count__gt=0).exists()

        # Verify 4 groups and memberships.
        group_names = set(Group.objects.filter(book=demo_book).values_list("group_name", flat=True))
        assert group_names == {"Work Colleagues", "Family", "VIP Clients", "Emergency"}
        assert ContactGroup.objects.filter(group__book=demo_book).count() > 0

        # Verify 6 favorites with priorities in 1..5.
        favorites = FavoriteItem.objects.filter(favorite_list=demo_fav_list)
        assert favorites.count() == 6
        priorities = list(favorites.values_list("priority", flat=True))
        assert all(1 <= p <= 5 for p in priorities)
        assert len(set(priorities)) >= 4

    def test_seed_demo_accounts_is_idempotent_and_preserves_other_users(self, user_factory):
        benchmark_user = user_factory(
            username="demo_user",
            email="demo_user@example.com",
            password="DemoUser2026!",
        )
        benchmark_contact = Contact.objects.create(
            book=benchmark_user.contact_book,
            full_name="Benchmark Contact",
        )
        PhoneNumber.objects.create(
            contact=benchmark_contact,
            phone_number="0901112233",
            phone_type=PhoneNumber.PhoneType.MOBILE,
            is_primary=True,
        )

        call_command("seed_demo_accounts", stdout=StringIO())

        demo = CustomUser.objects.get(username="demo")
        first_counts = (
            Contact.objects.filter(book=demo.contact_book).count(),
            PhoneNumber.objects.filter(contact__book=demo.contact_book).count(),
            Group.objects.filter(book=demo.contact_book).count(),
            ContactGroup.objects.filter(group__book=demo.contact_book).count(),
            FavoriteItem.objects.filter(favorite_list__book=demo.contact_book).count(),
        )

        # Second invocation without --reset must keep exact counts and preserve demo_user.
        second_stdout = StringIO()
        call_command("seed_demo_accounts", stdout=second_stdout)

        second_counts = (
            Contact.objects.filter(book=demo.contact_book).count(),
            PhoneNumber.objects.filter(contact__book=demo.contact_book).count(),
            Group.objects.filter(book=demo.contact_book).count(),
            ContactGroup.objects.filter(group__book=demo.contact_book).count(),
            FavoriteItem.objects.filter(favorite_list__book=demo.contact_book).count(),
        )
        assert second_counts == first_counts
        assert "Skipped sample data seeding" in second_stdout.getvalue()

        assert CustomUser.objects.filter(username="demo_user").count() == 1
        assert Contact.objects.filter(book=benchmark_user.contact_book).count() == 1
        assert PhoneNumber.objects.filter(contact__book=benchmark_user.contact_book).count() == 1

    def test_seed_demo_accounts_reset_restores_defaults_without_touching_others(self, user_factory):
        other_user = user_factory(username="demo_user", email="demo_user@example.com")
        other_contact = Contact.objects.create(
            book=other_user.contact_book,
            full_name="Preserved Benchmark Entry",
        )
        PhoneNumber.objects.create(
            contact=other_contact,
            phone_number="0909998877",
            phone_type=PhoneNumber.PhoneType.MOBILE,
            is_primary=True,
        )

        call_command("seed_demo_accounts", stdout=StringIO())

        demo = CustomUser.objects.get(username="demo")
        admin = CustomUser.objects.get(username="admin")

        # Mutate demo data and corrupt passwords/statuses to simulate drift.
        demo.set_password("ChangedPass99!")
        demo.save()
        admin.set_password("ChangedAdmin99!")
        admin.is_staff = False
        admin.account_status = CustomUser.AccountStatus.LOCKED
        admin.save()

        extra_contact = Contact.objects.create(
            book=demo.contact_book,
            full_name="Temporary Extra Contact",
        )
        PhoneNumber.objects.create(
            contact=extra_contact,
            phone_number="0911223344",
            phone_type=PhoneNumber.PhoneType.MOBILE,
            is_primary=True,
        )
        Group.objects.create(book=demo.contact_book, group_name="Temporary Group")
        assert Contact.objects.filter(book=demo.contact_book).count() == 26
        assert Group.objects.filter(book=demo.contact_book).count() == 5

        call_command("seed_demo_accounts", reset=True, stdout=StringIO())

        demo.refresh_from_db()
        admin.refresh_from_db()
        assert demo.check_password("A@123")
        assert demo.account_status == CustomUser.AccountStatus.ACTIVE
        assert admin.check_password("A@123")
        assert admin.is_admin is True
        assert admin.is_staff is True
        assert admin.is_superuser is True
        assert admin.role == CustomUser.Role.ADMIN
        assert admin.account_status == CustomUser.AccountStatus.ACTIVE
        assert admin.is_active is True

        assert Contact.objects.filter(book=demo.contact_book).count() == 25
        assert Group.objects.filter(book=demo.contact_book).count() == 4
        assert FavoriteItem.objects.filter(favorite_list__book=demo.contact_book).count() == 6
        assert not Contact.objects.filter(
            book=demo.contact_book, full_name="Temporary Extra Contact"
        ).exists()

        # Other user's data remains untouched.
        assert Contact.objects.filter(book=other_user.contact_book).count() == 1
