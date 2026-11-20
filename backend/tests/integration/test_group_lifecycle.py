"""Integration tests for User Story 6: Contact Grouping & Organizational Management (T077)."""

import pytest
from django.test import Client


def _seed_contact(user, *, full_name, phones=None, email=None):
    from apps.contacts.models import Contact, PhoneNumber

    contact = Contact.objects.create(book=user.contact_book, full_name=full_name, email=email)
    for number, ptype, is_primary in phones or [("0901234567", "Mobile", True)]:
        PhoneNumber.objects.create(
            contact=contact,
            phone_number=number,
            phone_type=ptype,
            is_primary=is_primary,
        )
    return contact


@pytest.mark.django_db
class TestGroupLifecycleIntegration:
    """End-to-end tests for US6, FR-026..033, FR-042, EC-002, EC-003, SC-006."""

    def test_us6_full_group_crud_member_management_search_and_contact_retention(self, user_factory):
        from apps.contacts.models import Contact, PhoneNumber
        from apps.groups.models import ContactGroup, Group

        owner = user_factory(username="us6_owner", email="us6owner@example.com")
        alice = _seed_contact(
            owner,
            full_name="Alice Coworker",
            phones=[("0901111111", "Mobile", True)],
            email="alice@work.org",
        )
        bob = _seed_contact(
            owner,
            full_name="Bob Friend",
            phones=[("0902222222", "Mobile", True), ("02838222222", "Work", False)],
            email="bob@friends.org",
        )
        charlie = _seed_contact(
            owner,
            full_name="Charlie VIP",
            phones=[("0903333333", "Mobile", True)],
        )

        client = Client(enforce_csrf_checks=True)
        client.force_login(owner)

        # 1. Navbar includes Groups link and /groups/ loads cleanly
        contacts_page = client.get("/contacts/")
        assert contacts_page.status_code == 200
        assert b"/groups/" in contacts_page.content
        csrf_token = contacts_page.cookies["csrftoken"].value

        # 2. Create groups (Scenario 1) and reject duplicate name (Scenario 2)
        create_resp = client.post(
            "/groups/create/",
            {
                "group_name": "Coworkers",
                "description": "Project team members",
                "csrfmiddlewaretoken": csrf_token,
            },
        )
        assert create_resp.status_code == 302
        coworkers = Group.objects.get(book=owner.contact_book, group_name="Coworkers")

        create_friends = client.post(
            "/groups/create/",
            {
                "group_name": "Friends",
                "description": "Close friends",
                "csrfmiddlewaretoken": csrf_token,
            },
        )
        assert create_friends.status_code == 302
        friends = Group.objects.get(book=owner.contact_book, group_name="Friends")

        dup_group_resp = client.post(
            "/groups/create/",
            {
                "group_name": "coworkers",
                "csrfmiddlewaretoken": csrf_token,
            },
        )
        assert dup_group_resp.status_code == 400
        assert Group.objects.filter(book=owner.contact_book).count() == 2

        # 3. Assign contacts to multiple groups (N:M) & prevent duplicates (FR-030, FR-031)
        for target_group, target_contact in (
            (coworkers, alice),
            (coworkers, bob),
            (friends, bob),
            (friends, charlie),
        ):
            add_resp = client.post(
                f"/groups/{target_group.pk}/members/add/",
                {"contact_id": str(target_contact.pk), "csrfmiddlewaretoken": csrf_token},
            )
            assert add_resp.status_code == 302

        dup_member_resp = client.post(
            f"/groups/{coworkers.pk}/members/add/",
            {"contact_id": str(alice.pk), "csrfmiddlewaretoken": csrf_token},
        )
        assert dup_member_resp.status_code == 400
        assert ContactGroup.objects.filter(group=coworkers, contact=alice).count() == 1

        # 4. In-group search on group detail page
        search_resp = client.get(f"/groups/{coworkers.pk}/?q=Bob")
        assert search_resp.status_code == 200
        assert [c.full_name for c in search_resp.context["member_contacts"]] == ["Bob Friend"]

        # 5. Contact directory ?group=<id> filter & ContactDetailView groups display
        filtered_contacts = client.get(f"/contacts/?group={coworkers.pk}")
        assert filtered_contacts.status_code == 200
        assert [c.full_name for c in filtered_contacts.context["contacts"]] == [
            "Alice Coworker",
            "Bob Friend",
        ]
        assert [g.group_name for g in filtered_contacts.context["groups"]] == [
            "Coworkers",
            "Friends",
        ]

        bob_detail = client.get(f"/contacts/{bob.pk}/")
        assert bob_detail.status_code == 200
        assert [g.group_name for g in bob_detail.context["groups"]] == ["Coworkers", "Friends"]
        assert b"Coworkers" in bob_detail.content
        assert b"Friends" in bob_detail.content

        # 6. Remove Bob from Coworkers -> stays in directory and in Friends (FR-032)
        rem_resp = client.post(
            f"/groups/{coworkers.pk}/members/{bob.pk}/remove/",
            {"csrfmiddlewaretoken": csrf_token},
        )
        assert rem_resp.status_code == 302
        assert not ContactGroup.objects.filter(group=coworkers, contact=bob).exists()
        assert ContactGroup.objects.filter(group=friends, contact=bob).exists()
        assert Contact.objects.filter(pk=bob.pk).exists()

        # 7. Edit group name & description (FR-028)
        edit_resp = client.post(
            f"/groups/{friends.pk}/edit/",
            {
                "group_name": "Close Friends",
                "description": "Updated description",
                "csrfmiddlewaretoken": csrf_token,
            },
        )
        assert edit_resp.status_code == 302
        friends.refresh_from_db()
        assert friends.group_name == "Close Friends"

        # 8. Delete group -> all member contacts & phones remain intact (FR-029, EC-003, SC-006)
        del_resp = client.post(
            f"/groups/{friends.pk}/delete/",
            {"confirm": "true", "csrfmiddlewaretoken": csrf_token},
        )
        assert del_resp.status_code == 302
        assert not Group.objects.filter(pk=friends.pk).exists()
        assert not ContactGroup.objects.filter(group_id=friends.pk).exists()
        assert Contact.objects.filter(pk=bob.pk).exists()
        assert Contact.objects.filter(pk=charlie.pk).exists()
        assert PhoneNumber.objects.filter(contact=bob).count() == 2

    def test_ec002_contact_deletion_cascades_contactgroup_while_retaining_group(
        self, authenticated_client
    ):
        from apps.contacts.models import Contact
        from apps.groups.models import ContactGroup, Group

        client, owner = authenticated_client(username="ec002_grp", email="ec002grp@example.com")
        group = Group.objects.create(book=owner.contact_book, group_name="Gym Buddies")
        contact = _seed_contact(owner, full_name="Doomed Member")
        ContactGroup.objects.create(group=group, contact=contact)

        resp = client.post(f"/contacts/{contact.pk}/delete/", {"confirm": "true"})
        assert resp.status_code == 302
        assert not Contact.objects.filter(pk=contact.pk).exists()
        assert not ContactGroup.objects.filter(contact_id=contact.pk).exists()
        assert Group.objects.filter(pk=group.pk).exists()

    def test_smart_merge_migrates_contact_group_memberships_without_duplicates(
        self, authenticated_client
    ):
        from apps.contacts.services import SmartMergeService
        from apps.groups.models import ContactGroup, Group

        client, owner = authenticated_client(username="merge_grp", email="mergegrp@example.com")
        shared_group = Group.objects.create(book=owner.contact_book, group_name="Shared")
        source_only_group = Group.objects.create(book=owner.contact_book, group_name="SourceOnly")
        target_only_group = Group.objects.create(book=owner.contact_book, group_name="TargetOnly")

        target = _seed_contact(
            owner,
            full_name="Target Contact",
            phones=[("0901112222", "Mobile", True)],
        )
        source = _seed_contact(
            owner,
            full_name="Source Contact",
            phones=[("0901112222", "Mobile", True), ("0908889999", "Work", False)],
        )

        ContactGroup.objects.create(group=shared_group, contact=target)
        ContactGroup.objects.create(group=target_only_group, contact=target)
        ContactGroup.objects.create(group=shared_group, contact=source)
        ContactGroup.objects.create(group=source_only_group, contact=source)

        preview = SmartMergeService.build_merge_preview(
            target_contact=target,
            source_contact=source,
        )
        assert preview["groups_to_migrate"] == ["SourceOnly"]

        merge_resp = client.post(
            "/contacts/merge/",
            {"target_contact_id": str(target.pk), "source_contact_id": str(source.pk)},
        )
        assert merge_resp.status_code == 302

        migrated_group_names = list(
            ContactGroup.objects.filter(contact=target)
            .select_related("group")
            .order_by("group__group_name")
            .values_list("group__group_name", flat=True)
        )
        assert migrated_group_names == ["Shared", "SourceOnly", "TargetOnly"]
        assert ContactGroup.objects.filter(contact_id=source.pk).count() == 0

    def test_multi_tenant_isolation_across_users(self, authenticated_client, user_factory):
        from apps.groups.models import ContactGroup, Group

        client_a, user_a = authenticated_client(username="grp_iso_a", email="grpisoa@example.com")
        user_b = user_factory(username="grp_iso_b", email="grpisob@example.com")

        group_b = Group.objects.create(book=user_b.contact_book, group_name="Private B")
        contact_b = _seed_contact(user_b, full_name="Private Contact B")
        ContactGroup.objects.create(group=group_b, contact=contact_b)

        group_a = Group.objects.create(book=user_a.contact_book, group_name="Public A")

        # User A cannot inspect, edit, delete, or mutate memberships of User B's group
        assert client_a.get(f"/groups/{group_b.pk}/").status_code == 404
        assert (
            client_a.post(f"/groups/{group_b.pk}/edit/", {"group_name": "Hacked"}).status_code
            == 404
        )
        assert (
            client_a.post(f"/groups/{group_b.pk}/delete/", {"confirm": "true"}).status_code == 404
        )
        assert (
            client_a.post(
                f"/groups/{group_a.pk}/members/add/", {"contact_id": str(contact_b.pk)}
            ).status_code
            == 404
        )
        assert (
            client_a.post(f"/groups/{group_b.pk}/members/{contact_b.pk}/remove/").status_code == 404
        )

        # User A filtering /contacts/?group=<group_b.pk> sees zero contacts & no foreign name
        filtered = client_a.get(f"/contacts/?group={group_b.pk}")
        assert filtered.status_code == 200
        assert list(filtered.context["contacts"]) == []
        assert b"Private B" not in filtered.content
        assert Group.objects.filter(pk=group_b.pk).exists()
        assert ContactGroup.objects.filter(group=group_b, contact=contact_b).exists()
