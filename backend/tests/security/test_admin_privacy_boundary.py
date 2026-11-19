"""Security boundary tests verifying admin isolation from personal contacts (T100)."""

import pytest
from django.test import Client

from apps.contacts.models import Contact, PhoneNumber
from apps.favorites.models import FavoriteItem
from apps.groups.models import ContactGroup, Group


def _create_personal_contact(user, full_name: str, phone: str, email: str) -> Contact:
    contact = Contact.objects.create(
        book=user.contact_book,
        full_name=full_name,
        email=email,
        address="Secret Residential Address 42",
        work_address="Secret Workplace HQ",
        notes="Strictly private personal notes",
    )
    PhoneNumber.objects.create(
        contact=contact,
        phone_number=phone,
        phone_type="Mobile",
        is_primary=True,
    )
    return contact


@pytest.mark.django_db
class TestAdminPrivacyBoundary:
    """Verify FR-042: admins govern accounts only and cannot access others' personal data."""

    def test_admin_cannot_access_or_mutate_user_personal_contacts_favorites_or_groups(
        self, user_factory
    ):
        admin_user = user_factory(
            username="sec_admin",
            email="secadmin@example.com",
            role="Admin",
            is_staff=True,
            is_superuser=True,
        )
        alice = user_factory(username="sec_alice", email="secalice@example.com")

        alice_contact = _create_personal_contact(
            alice,
            full_name="Alice Private Friend",
            phone="0901239876",
            email="alice.friend@private.example",
        )
        alice_fav = FavoriteItem.objects.create(
            favorite_list=alice.contact_book.favorite_list,
            contact=alice_contact,
            priority=1,
        )
        alice_group = Group.objects.create(
            book=alice.contact_book,
            group_name="Alice Secret Circle",
            description="Private circle description",
        )
        ContactGroup.objects.create(group=alice_group, contact=alice_contact)

        # Admin also has their own isolated personal contact book
        admin_contact = _create_personal_contact(
            admin_user,
            full_name="Admin Personal Contact",
            phone="0905551111",
            email="admin.personal@example.com",
        )
        admin_group = Group.objects.create(
            book=admin_user.contact_book,
            group_name="Admin Personal Group",
        )

        admin_client = Client()
        admin_client.force_login(admin_user)

        # 1. Admin's personal endpoints see ONLY admin's own contacts/favorites/groups
        contacts_resp = admin_client.get("/contacts/")
        assert contacts_resp.status_code == 200
        assert b"Admin Personal Contact" in contacts_resp.content
        assert b"Alice Private Friend" not in contacts_resp.content
        assert b"0901239876" not in contacts_resp.content
        assert b"Dashboard" in contacts_resp.content
        assert b"User Management" in contacts_resp.content

        fav_resp = admin_client.get("/favorites/")
        assert fav_resp.status_code == 200
        assert b"Alice Private Friend" not in fav_resp.content

        groups_resp = admin_client.get("/groups/")
        assert groups_resp.status_code == 200
        assert b"Admin Personal Group" in groups_resp.content
        assert b"Alice Secret Circle" not in groups_resp.content

        # 2. Direct access to Alice's contacts, favorites, or groups returns 404
        assert admin_client.get(f"/contacts/{alice_contact.pk}/").status_code == 404
        assert admin_client.get(f"/contacts/{alice_contact.pk}/edit/").status_code == 404
        assert (
            admin_client.post(
                f"/contacts/{alice_contact.pk}/edit/",
                {"full_name": "Tampered", "primary_phone": "0900000000"},
            ).status_code
            == 404
        )
        assert (
            admin_client.post(
                f"/contacts/{alice_contact.pk}/delete/",
                {"confirm": "true"},
            ).status_code
            == 404
        )
        assert admin_client.post(f"/favorites/add/{alice_contact.pk}/").status_code == 404
        assert (
            admin_client.post(
                f"/favorites/{alice_fav.pk}/priority/",
                {"priority": "10"},
            ).status_code
            == 404
        )
        assert admin_client.get(f"/groups/{alice_group.pk}/").status_code == 404
        assert (
            admin_client.post(
                f"/groups/{alice_group.pk}/delete/",
                {"confirm": "true"},
            ).status_code
            == 404
        )
        assert (
            admin_client.post(
                f"/groups/{admin_group.pk}/members/add/",
                {"contact_id": str(alice_contact.pk)},
            ).status_code
            == 404
        )

        # 3. Admin panel endpoints show only aggregate count (1), never personal contact data
        admin_detail_resp = admin_client.get(f"/admin-panel/users/{alice.pk}/")
        assert admin_detail_resp.status_code == 200
        assert admin_detail_resp.context["target_user"].contact_count == 1
        detail_html = admin_detail_resp.content.decode("utf-8")
        assert "Alice Private Friend" not in detail_html
        assert "0901239876" not in detail_html
        assert "alice.friend@private.example" not in detail_html
        assert "Secret Residential Address 42" not in detail_html
        assert "Strictly private personal notes" not in detail_html
        assert "Alice Secret Circle" not in detail_html

        # 4. Standard user navbar never exposes Admin Panel link
        alice_client = Client()
        alice_client.force_login(alice)
        alice_contacts = alice_client.get("/contacts/")
        assert alice_contacts.status_code == 200
        assert b"Admin Panel" not in alice_contacts.content
        assert b"/admin-panel/" not in alice_contacts.content

        # Verify Alice's records remain completely untouched
        alice_contact.refresh_from_db()
        assert alice_contact.full_name == "Alice Private Friend"
        assert Contact.objects.filter(pk=admin_contact.pk).exists()
