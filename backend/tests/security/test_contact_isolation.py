"""Multi-tenant isolation security tests for contact endpoints (T044)."""

import pytest
from django.test import Client

from apps.contacts.models import Contact, PhoneNumber


def _seed_contact(user, full_name: str, phone: str) -> Contact:
    contact = Contact.objects.create(
        book=user.contact_book,
        full_name=full_name,
        email=f"{full_name.lower().replace(' ', '.')}@private.test",
    )
    PhoneNumber.objects.create(
        contact=contact,
        phone_number=phone,
        phone_type="Mobile",
        is_primary=True,
    )
    return contact


@pytest.mark.django_db
class TestContactMultiTenantIsolation:
    """Verify strict FR-042 & NFR-007 multi-tenant contact book isolation."""

    def test_anonymous_requests_to_all_contact_endpoints_redirect_to_login(self, user_factory):
        owner = user_factory(username="iso_owner", email="isoowner@example.com")
        contact = _seed_contact(owner, "Hidden Entry", "0901234567")

        anon = Client()
        for method, path in [
            ("get", "/contacts/"),
            ("get", "/contacts/create/"),
            ("post", "/contacts/create/"),
            ("get", f"/contacts/{contact.pk}/"),
            ("get", f"/contacts/{contact.pk}/edit/"),
            ("post", f"/contacts/{contact.pk}/edit/"),
            ("post", f"/contacts/{contact.pk}/delete/"),
            ("post", "/contacts/batch-delete/"),
        ]:
            resp = getattr(anon, method)(path, {})
            assert resp.status_code == 302, f"Expected 302 for {method.upper()} {path}"
            assert resp.url.startswith("/accounts/login/")

    def test_standard_user_cannot_view_edit_or_delete_another_users_contacts(self, user_factory):
        alice = user_factory(username="alice_iso", email="aliceiso@example.com")
        bob = user_factory(username="bob_iso", email="bobiso@example.com")

        alice_contact = _seed_contact(alice, "Alice Secret Contact", "0901112222")
        bob_contact = _seed_contact(bob, "Bob Own Contact", "0903334444")

        bob_client = Client()
        bob_client.force_login(bob)

        # Listing never leaks Alice's contact
        list_resp = bob_client.get("/contacts/")
        assert list_resp.status_code == 200
        assert b"Bob Own Contact" in list_resp.content
        assert b"Alice Secret Contact" not in list_resp.content
        assert b"0901112222" not in list_resp.content

        # Direct detail/edit/delete/batch-delete return 404 and leave Alice's record intact
        assert bob_client.get(f"/contacts/{alice_contact.pk}/").status_code == 404
        assert bob_client.get(f"/contacts/{alice_contact.pk}/edit/").status_code == 404

        edit_resp = bob_client.post(
            f"/contacts/{alice_contact.pk}/edit/",
            {
                "full_name": "Hacked Name",
                "primary_phone": "0999999999",
            },
        )
        assert edit_resp.status_code == 404

        delete_resp = bob_client.post(
            f"/contacts/{alice_contact.pk}/delete/",
            {"confirm": "true"},
        )
        assert delete_resp.status_code == 404

        batch_resp = bob_client.post(
            "/contacts/batch-delete/",
            {"contact_ids": [str(alice_contact.pk)], "confirm": "true"},
        )
        assert batch_resp.status_code == 404

        alice_contact.refresh_from_db()
        assert alice_contact.full_name == "Alice Secret Contact"
        assert Contact.objects.filter(pk=bob_contact.pk).exists()

    def test_admin_user_is_equally_isolated_from_other_users_contacts(self, user_factory):
        """FR-042: Administrators cannot browse, inspect, or mutate other users' contacts."""
        from apps.favorites.models import FavoriteItem
        from apps.groups.models import ContactGroup, Group

        victim = user_factory(username="victim_u", email="victim@example.com")
        admin_user = user_factory(
            username="admin_iso",
            email="adminiso@example.com",
            role="Admin",
            is_staff=True,
            is_superuser=True,
        )

        victim_contact = _seed_contact(victim, "Victim Private Contact", "0905556666")
        admin_own = _seed_contact(admin_user, "Admin Own Contact", "0907778888")

        victim_fav = FavoriteItem.objects.create(
            favorite_list=victim.contact_book.favorite_list,
            contact=victim_contact,
            priority=2,
        )
        victim_group = Group.objects.create(
            book=victim.contact_book,
            group_name="Victim Private Group",
        )
        ContactGroup.objects.create(group=victim_group, contact=victim_contact)
        admin_group = Group.objects.create(
            book=admin_user.contact_book,
            group_name="Admin Own Group",
        )

        admin_client = Client()
        admin_client.force_login(admin_user)

        list_resp = admin_client.get("/contacts/")
        assert list_resp.status_code == 200
        assert b"Admin Own Contact" in list_resp.content
        assert b"Victim Private Contact" not in list_resp.content

        # Search, group-filter, and duplicate detection must never surface victim's data
        search_resp = admin_client.get("/contacts/search/?q=Victim")
        assert search_resp.status_code == 200
        assert b"Victim Private Contact" not in search_resp.content

        group_filter_resp = admin_client.get(f"/contacts/?group={victim_group.pk}")
        assert group_filter_resp.status_code == 200
        assert b"Victim Private Contact" not in group_filter_resp.content

        dup_resp = admin_client.post(
            "/contacts/check-duplicate/",
            {"full_name": "Victim Private Contact", "phone_number": "0905556666"},
        )
        assert dup_resp.status_code == 200
        assert dup_resp.content == b""

        # Direct contact endpoints -> 404
        assert admin_client.get(f"/contacts/{victim_contact.pk}/").status_code == 404
        assert admin_client.get(f"/contacts/{victim_contact.pk}/edit/").status_code == 404
        assert (
            admin_client.post(
                f"/contacts/{victim_contact.pk}/edit/",
                {"full_name": "Admin Override", "primary_phone": "0900000000"},
            ).status_code
            == 404
        )
        assert (
            admin_client.post(
                f"/contacts/{victim_contact.pk}/delete/",
                {"confirm": "true"},
            ).status_code
            == 404
        )
        assert (
            admin_client.post(
                "/contacts/batch-delete/",
                {"contact_ids": [str(victim_contact.pk)], "confirm": "true"},
            ).status_code
            == 404
        )

        # Merge & interaction endpoints -> 404
        merge_url = (
            f"/contacts/merge/?target_contact_id={admin_own.pk}"
            f"&source_contact_id={victim_contact.pk}"
        )
        assert admin_client.get(merge_url).status_code == 404
        assert (
            admin_client.post(
                "/contacts/merge/",
                {
                    "target_contact_id": str(admin_own.pk),
                    "source_contact_id": str(victim_contact.pk),
                },
            ).status_code
            == 404
        )
        assert admin_client.post(f"/contacts/{victim_contact.pk}/interact/").status_code == 404

        # Favorites endpoints -> scoped list & 404 on victim's contacts/items
        fav_list_resp = admin_client.get("/favorites/")
        assert fav_list_resp.status_code == 200
        assert b"Victim Private Contact" not in fav_list_resp.content
        assert admin_client.post(f"/favorites/add/{victim_contact.pk}/").status_code == 404
        assert admin_client.post(f"/favorites/remove/{victim_contact.pk}/").status_code == 404
        assert (
            admin_client.post(
                f"/favorites/{victim_fav.pk}/priority/", {"priority": "9"}
            ).status_code
            == 404
        )

        # Groups endpoints -> scoped list & 404 on victim's groups/members
        grp_list_resp = admin_client.get("/groups/")
        assert grp_list_resp.status_code == 200
        assert b"Victim Private Group" not in grp_list_resp.content
        assert admin_client.get(f"/groups/{victim_group.pk}/").status_code == 404
        assert admin_client.get(f"/groups/{victim_group.pk}/edit/").status_code == 404
        assert (
            admin_client.post(
                f"/groups/{victim_group.pk}/edit/", {"group_name": "Hijacked"}
            ).status_code
            == 404
        )
        assert (
            admin_client.post(f"/groups/{victim_group.pk}/delete/", {"confirm": "true"}).status_code
            == 404
        )
        assert (
            admin_client.post(
                f"/groups/{admin_group.pk}/members/add/",
                {"contact_id": str(victim_contact.pk)},
            ).status_code
            == 404
        )
        assert (
            admin_client.post(
                f"/groups/{victim_group.pk}/members/{victim_contact.pk}/remove/"
            ).status_code
            == 404
        )

        victim_contact.refresh_from_db()
        assert victim_contact.full_name == "Victim Private Contact"
        assert victim_contact.interaction_count == 0
        victim_fav.refresh_from_db()
        assert victim_fav.priority == 2
        assert Group.objects.filter(pk=victim_group.pk).exists()
        assert ContactGroup.objects.filter(group=victim_group, contact=victim_contact).exists()
        assert Contact.objects.filter(pk=admin_own.pk).exists()
