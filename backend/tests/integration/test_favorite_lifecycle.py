"""Integration tests for User Story 5: Favorite List & Priority Management (T066)."""

import pytest
from django.test import Client


def _seed_contact(user, *, full_name, phones=None, **kwargs):
    from apps.contacts.models import Contact, PhoneNumber

    contact = Contact.objects.create(book=user.contact_book, full_name=full_name, **kwargs)
    for number, ptype, is_primary in phones or [("0901234567", "Mobile", True)]:
        PhoneNumber.objects.create(
            contact=contact,
            phone_number=number,
            phone_type=ptype,
            is_primary=is_primary,
        )
    return contact


@pytest.mark.django_db
class TestFavoriteLifecycleIntegration:
    """End-to-end tests for US5 Scenarios 1-4, FR-019..025, EC-002, EC-004, SC-006."""

    def test_us5_full_favorite_bookmark_priority_frequency_and_safe_removal(self, user_factory):
        from apps.contacts.models import Contact, PhoneNumber
        from apps.favorites.models import FavoriteItem

        owner = user_factory(username="us5_owner", email="us5owner@example.com")
        alice = _seed_contact(
            owner,
            full_name="Alice Priority",
            phones=[("0901111111", "Mobile", True)],
        )
        bob = _seed_contact(
            owner,
            full_name="Bob Frequency",
            phones=[("0902222222", "Mobile", True), ("02838222222", "Work", False)],
        )
        charlie = _seed_contact(
            owner,
            full_name="Charlie Baseline",
            phones=[("0903333333", "Mobile", True)],
        )

        client = Client(enforce_csrf_checks=True)
        client.force_login(owner)

        # 1. Directory renders navbar Favorites link and star toggle buttons
        directory_resp = client.get("/contacts/")
        assert directory_resp.status_code == 200
        assert b"/favorites/" in directory_resp.content
        assert f"/favorites/add/{alice.pk}/".encode() in directory_resp.content
        csrf_token = client.cookies["csrftoken"].value

        # 2. Bookmark contacts to favorites
        add_alice = client.post(
            f"/favorites/add/{alice.pk}/",
            {"priority": "3", "csrfmiddlewaretoken": csrf_token},
        )
        assert add_alice.status_code == 302
        add_bob = client.post(
            f"/favorites/add/{bob.pk}/",
            {"priority": "8", "csrfmiddlewaretoken": csrf_token},
        )
        assert add_bob.status_code == 302
        add_charlie = client.post(
            f"/favorites/add/{charlie.pk}/",
            {"csrfmiddlewaretoken": csrf_token},
        )
        assert add_charlie.status_code == 302

        # 3. Duplicate addition rejected without creating extra FavoriteItem (FR-021)
        dup_resp = client.post(
            f"/favorites/add/{alice.pk}/",
            {"csrfmiddlewaretoken": csrf_token},
        )
        assert dup_resp.status_code == 400
        assert (
            FavoriteItem.objects.filter(
                favorite_list=owner.contact_book.favorite_list,
                contact=alice,
            ).count()
            == 1
        )

        # 4. Update Bob's priority from 8 -> 1 and verify priority sorting (FR-023, FR-024)
        bob_fav = FavoriteItem.objects.get(
            favorite_list=owner.contact_book.favorite_list,
            contact=bob,
        )
        prio_resp = client.post(
            f"/favorites/{bob_fav.pk}/priority/",
            {"priority": "1", "csrfmiddlewaretoken": csrf_token},
        )
        assert prio_resp.status_code == 302

        fav_prio_page = client.get("/favorites/?sort=priority")
        assert fav_prio_page.status_code == 200
        assert [i.contact.full_name for i in fav_prio_page.context["favorite_items"]] == [
            "Bob Frequency",
            "Alice Priority",
            "Charlie Baseline",
        ]

        # 5. Record interactions and verify frequency sorting (FR-025)
        for _ in range(3):
            resp = client.post(
                f"/contacts/{charlie.pk}/interact/",
                {"csrfmiddlewaretoken": csrf_token},
            )
            assert resp.status_code == 200
        resp_alice = client.post(
            f"/contacts/{alice.pk}/interact/",
            {"csrfmiddlewaretoken": csrf_token},
        )
        assert resp_alice.status_code == 200

        fav_freq_page = client.get("/favorites/?sort=frequency")
        assert fav_freq_page.status_code == 200
        assert [i.contact.full_name for i in fav_freq_page.context["favorite_items"]] == [
            "Charlie Baseline",
            "Alice Priority",
            "Bob Frequency",
        ]

        # 6. Remove Bob from favorites -> base contact & phones stay intact (FR-022, EC-004, SC-006)
        rem_resp = client.post(
            f"/favorites/remove/{bob.pk}/",
            {"csrfmiddlewaretoken": csrf_token},
        )
        assert rem_resp.status_code == 302
        assert not FavoriteItem.objects.filter(contact=bob).exists()
        assert Contact.objects.filter(pk=bob.pk).exists()
        assert PhoneNumber.objects.filter(contact=bob).count() == 2

        detail_after_rem = client.get(f"/contacts/{bob.pk}/")
        assert detail_after_rem.status_code == 200
        assert detail_after_rem.context["is_favorite"] is False
        assert f"/favorites/add/{bob.pk}/".encode() in detail_after_rem.content

    def test_ec002_contact_deletion_cascades_favorite_item(self, authenticated_client):
        from apps.contacts.models import Contact
        from apps.favorites.models import FavoriteItem, FavoriteList

        client, owner = authenticated_client(username="ec002_fav", email="ec002fav@example.com")
        contact = _seed_contact(owner, full_name="Doomed Favorite")
        fav_list = owner.contact_book.favorite_list
        FavoriteItem.objects.create(favorite_list=fav_list, contact=contact, priority=2)

        del_resp = client.post(f"/contacts/{contact.pk}/delete/", {"confirm": "true"})
        assert del_resp.status_code == 302
        assert not Contact.objects.filter(pk=contact.pk).exists()
        assert not FavoriteItem.objects.filter(contact_id=contact.pk).exists()
        assert FavoriteList.objects.filter(pk=fav_list.pk).exists()

    def test_smart_merge_preserves_favorite_status_across_phases(self, authenticated_client):
        from apps.contacts.services import SmartMergeService
        from apps.favorites.models import FavoriteItem

        client, owner = authenticated_client(username="merge_fav", email="mergefav@example.com")
        fav_list = owner.contact_book.favorite_list

        # Case A: source is favorite, target is NOT favorite -> FavoriteItem transfers to target
        target_a = _seed_contact(
            owner,
            full_name="Target Not Fav",
            phones=[("0901111222", "Mobile", True)],
        )
        source_a = _seed_contact(
            owner,
            full_name="Source Is Fav",
            phones=[("0901111222", "Mobile", True), ("0909998888", "Work", False)],
        )
        FavoriteItem.objects.create(favorite_list=fav_list, contact=source_a, priority=2)

        preview_a = SmartMergeService.build_merge_preview(
            target_contact=target_a, source_contact=source_a
        )
        assert preview_a["will_transfer_favorite"] is True

        merge_resp = client.post(
            "/contacts/merge/",
            {"target_contact_id": str(target_a.pk), "source_contact_id": str(source_a.pk)},
        )
        assert merge_resp.status_code == 302
        transferred = FavoriteItem.objects.get(favorite_list=fav_list, contact=target_a)
        assert transferred.priority == 2

        # Case B: both target and source are favorites -> target FavoriteItem kept without error
        source_b = _seed_contact(
            owner,
            full_name="Second Fav Source",
            phones=[("0907776666", "Mobile", True)],
        )
        FavoriteItem.objects.create(favorite_list=fav_list, contact=source_b, priority=7)

        merged_b = SmartMergeService.merge_contacts(
            target_contact=target_a,
            source_contact=source_b,
        )
        assert FavoriteItem.objects.filter(favorite_list=fav_list, contact=merged_b).count() == 1
        assert FavoriteItem.objects.get(favorite_list=fav_list, contact=merged_b).priority == 2
