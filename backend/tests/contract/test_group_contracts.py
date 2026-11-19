"""Contract tests for contact group management endpoints (T076)."""

import pytest
from django.contrib.messages import get_messages


def _create_contact(user, *, full_name="Alice Smith", phones=None, email=None):
    from apps.contacts.models import Contact, PhoneNumber

    contact = Contact.objects.create(book=user.contact_book, full_name=full_name, email=email)
    phone_specs = phones or [("0901234567", "Mobile", True)]
    for number, ptype, is_primary in phone_specs:
        PhoneNumber.objects.create(
            contact=contact,
            phone_number=number,
            phone_type=ptype,
            is_primary=is_primary,
        )
    return contact


def _create_group(user, *, group_name="Coworkers", description=None):
    from apps.groups.models import Group

    return Group.objects.create(
        book=user.contact_book,
        group_name=group_name,
        description=description,
    )


def _assign_member(group, contact):
    from apps.groups.models import ContactGroup

    return ContactGroup.objects.create(group=group, contact=contact)


@pytest.mark.django_db
class TestGroupListContract:
    """Contract tests for GET /groups/ (group-contracts.md 2.1)."""

    def test_anonymous_user_redirected_to_login(self, client):
        response = client.get("/groups/")
        assert response.status_code == 302
        assert response.url.startswith("/accounts/login/")

    def test_authenticated_list_annotated_with_member_count_and_scoped(
        self, authenticated_client, user_factory
    ):
        client, owner = authenticated_client(
            username="grp_list_own", email="grplistown@example.com"
        )
        other = user_factory(username="grp_list_oth", email="grplistoth@example.com")

        g_empty = _create_group(owner, group_name="Alumni", description="Old classmates")
        g_work = _create_group(owner, group_name="Coworkers", description="Engineering team")
        g_foreign = _create_group(other, group_name="Secret Foreign Group")

        c1 = _create_contact(owner, full_name="Alice Member")
        c2 = _create_contact(owner, full_name="Bob Member")
        c_foreign = _create_contact(other, full_name="Foreign Member")
        _assign_member(g_work, c1)
        _assign_member(g_work, c2)
        _assign_member(g_foreign, c_foreign)

        response = client.get("/groups/")
        assert response.status_code == 200
        template_names = [t.name for t in response.templates if t.name]
        assert "groups/group_list.html" in template_names
        assert response.context["total_groups_count"] == 2

        groups = list(response.context["groups"])
        assert [g.group_name for g in groups] == ["Alumni", "Coworkers"]
        counts_by_id = {g.pk: g.member_count for g in groups}
        assert counts_by_id[g_empty.pk] == 0
        assert counts_by_id[g_work.pk] == 2
        assert b"Secret Foreign Group" not in response.content


@pytest.mark.django_db
class TestGroupCreateContract:
    """Contract tests for POST /groups/create/ (group-contracts.md 2.2)."""

    def test_anonymous_user_redirected_to_login(self, client):
        response = client.post("/groups/create/", {"group_name": "Family"})
        assert response.status_code == 302
        assert response.url.startswith("/accounts/login/")

    def test_standard_and_htmx_create_trims_name_and_allows_cross_user_duplicates(
        self, authenticated_client, user_factory
    ):
        from apps.groups.models import Group

        client, owner = authenticated_client(username="grp_cr_own", email="grpchown@example.com")
        other = user_factory(username="grp_cr_oth", email="grpchoth@example.com")

        # Another user can already have a group named "Coworkers"
        _create_group(other, group_name="Coworkers")

        # GET /groups/create/ renders form cleanly
        resp_get = client.get("/groups/create/")
        assert resp_get.status_code == 200
        assert "groups/group_form.html" in [t.name for t in resp_get.templates if t.name]

        # Standard POST trims whitespace and redirects to /groups/
        resp_std = client.post(
            "/groups/create/",
            {"group_name": "  Coworkers  ", "description": "  Project team members  "},
        )
        assert resp_std.status_code == 302
        assert resp_std.url == "/groups/"
        msgs = [str(m) for m in get_messages(resp_std.wsgi_request)]
        assert "Group 'Coworkers' created successfully." in msgs

        created = Group.objects.get(book=owner.contact_book, group_name="Coworkers")
        assert created.description == "Project team members"

        # HTMX POST returns 200 with group_table_row.html partial
        resp_htmx = client.post(
            "/groups/create/",
            {"group_name": "Family", "description": "Close relatives"},
            HTTP_HX_REQUEST="true",
        )
        assert resp_htmx.status_code == 200
        template_names = [t.name for t in resp_htmx.templates if t.name]
        assert "groups/partials/group_table_row.html" in template_names
        assert b"Family" in resp_htmx.content
        assert Group.objects.filter(book=owner.contact_book, group_name="Family").exists()

    def test_create_validation_blank_and_case_insensitive_duplicate_errors(
        self, authenticated_client
    ):
        from apps.groups.models import Group

        client, owner = authenticated_client(username="grp_cr_val", email="grpcrval@example.com")
        _create_group(owner, group_name="Coworkers")

        # Blank or whitespace-only name -> 400 ERR_GROUP_NAME_REQUIRED
        for bad_name in ("", "   ", "\t\n"):
            resp_blank = client.post("/groups/create/", {"group_name": bad_name})
            assert resp_blank.status_code == 400
            assert b"Group name cannot be empty." in resp_blank.content

        # HTMX validation failure returns 400 with error text
        resp_htmx_err = client.post(
            "/groups/create/",
            {"group_name": "coworkers"},
            HTTP_HX_REQUEST="true",
        )
        assert resp_htmx_err.status_code == 400
        assert (
            b"You already have a group with this name. Please choose a distinct name."
            in resp_htmx_err.content
        )

        # Case-insensitive duplicate in same book -> 400 ERR_GROUP_NAME_DUPLICATE
        for dup_name in ("Coworkers", "coworkers", "  COWORKERS  "):
            resp_dup = client.post("/groups/create/", {"group_name": dup_name})
            assert resp_dup.status_code == 400
            assert (
                b"You already have a group with this name. Please choose a distinct name."
                in resp_dup.content
            )

        assert Group.objects.filter(book=owner.contact_book).count() == 1


@pytest.mark.django_db
class TestGroupDetailContract:
    """Contract tests for GET /groups/<int:id>/ (group-contracts.md 2.3)."""

    def test_anonymous_user_redirected_to_login(self, client):
        response = client.get("/groups/1/")
        assert response.status_code == 302
        assert response.url.startswith("/accounts/login/")

    def test_detail_pagination_in_group_search_available_contacts_and_cross_tenant_404(
        self, authenticated_client, user_factory
    ):
        client, owner = authenticated_client(username="grp_det_own", email="grpdetown@example.com")
        other = user_factory(username="grp_det_oth", email="grpdetoth@example.com")

        group = _create_group(owner, group_name="VIP Clients", description="Key accounts")
        foreign_group = _create_group(other, group_name="Other Group")

        # Create 23 contacts in group (to verify 20/page pagination) + 2 unassigned contacts
        for idx in range(1, 23):
            contact = _create_contact(
                owner,
                full_name=f"Member {idx:02d}",
                phones=[(f"0901000{idx:03d}", "Mobile", True)],
                email=f"member{idx:02d}@example.com",
            )
            _assign_member(group, contact)

        special_member = _create_contact(
            owner,
            full_name="Zara Special",
            phones=[("0988777666", "Work", True)],
            email="zara@vip.org",
        )
        _assign_member(group, special_member)

        unassigned_a = _create_contact(owner, full_name="Aaron Available")
        unassigned_b = _create_contact(owner, full_name="Bella Available")
        _create_contact(other, full_name="Foreign Unassigned")

        # Page 1
        resp_p1 = client.get(f"/groups/{group.pk}/")
        assert resp_p1.status_code == 200
        template_names = [t.name for t in resp_p1.templates if t.name]
        assert "groups/group_detail.html" in template_names
        assert resp_p1.context["group"] == group
        assert len(list(resp_p1.context["member_contacts"])) == 20
        available_ids = {c.pk for c in resp_p1.context["available_contacts"]}
        assert available_ids == {unassigned_a.pk, unassigned_b.pk}

        # Page 2
        resp_p2 = client.get(f"/groups/{group.pk}/?page=2")
        assert resp_p2.status_code == 200
        assert len(list(resp_p2.context["member_contacts"])) == 3

        # In-group search (?q=)
        resp_search = client.get(f"/groups/{group.pk}/?q=  Zara ")
        assert resp_search.status_code == 200
        matched_names = [c.full_name for c in resp_search.context["member_contacts"]]
        assert matched_names == ["Zara Special"]

        # HTMX in-group search returns member section partial
        resp_htmx_search = client.get(
            f"/groups/{group.pk}/?q=Zara",
            HTTP_HX_REQUEST="true",
        )
        assert resp_htmx_search.status_code == 200
        assert "groups/partials/group_member_section.html" in [
            t.name for t in resp_htmx_search.templates if t.name
        ]
        assert b"Zara Special" in resp_htmx_search.content

        # Cross-tenant or missing group -> 404
        assert client.get(f"/groups/{foreign_group.pk}/").status_code == 404
        assert client.get("/groups/999999/").status_code == 404


@pytest.mark.django_db
class TestGroupEditContract:
    """Contract tests for POST /groups/<int:id>/edit/ (group-contracts.md 2.4)."""

    def test_edit_auth_update_same_name_case_duplicate_and_cross_tenant_404(
        self, client, authenticated_client, user_factory
    ):
        anon_resp = client.post("/groups/1/edit/", {"group_name": "Updated"})
        assert anon_resp.status_code == 302
        assert anon_resp.url.startswith("/accounts/login/")

        auth_client, owner = authenticated_client(
            username="grp_ed_own", email="grpedown@example.com"
        )
        other = user_factory(username="grp_ed_oth", email="grpedoth@example.com")

        g1 = _create_group(owner, group_name="Work", description="Initial desc")
        _create_group(owner, group_name="Family", description="Relatives")
        foreign_group = _create_group(other, group_name="Foreign Work")

        # GET edit form
        resp_get_edit = auth_client.get(f"/groups/{g1.pk}/edit/")
        assert resp_get_edit.status_code == 200
        assert auth_client.get(f"/groups/{foreign_group.pk}/edit/").status_code == 404

        # Same-name / case-change edit succeeds
        resp_same_case = auth_client.post(
            f"/groups/{g1.pk}/edit/",
            {"group_name": "  work  ", "description": "Updated desc"},
        )
        assert resp_same_case.status_code == 302
        assert resp_same_case.url == f"/groups/{g1.pk}/"
        msgs = [str(m) for m in get_messages(resp_same_case.wsgi_request)]
        assert "Group updated successfully." in msgs
        g1.refresh_from_db()
        assert g1.group_name == "work"
        assert g1.description == "Updated desc"

        # Rename colliding case-insensitively with another group in same book -> 400
        resp_dup = auth_client.post(
            f"/groups/{g1.pk}/edit/",
            {"group_name": "FAMILY", "description": "Collision"},
        )
        assert resp_dup.status_code == 400
        assert (
            b"You already have a group with this name. Please choose a distinct name."
            in resp_dup.content
        )
        g1.refresh_from_db()
        assert g1.group_name == "work"

        # Cross-tenant or missing -> 404
        assert (
            auth_client.post(
                f"/groups/{foreign_group.pk}/edit/",
                {"group_name": "Hijacked"},
            ).status_code
            == 404
        )
        assert (
            auth_client.post("/groups/999999/edit/", {"group_name": "Missing"}).status_code == 404
        )


@pytest.mark.django_db
class TestGroupDeleteContract:
    """Contract tests for POST /groups/<int:id>/delete/ (group-contracts.md 2.5)."""

    def test_delete_requires_auth_post_confirm_preserves_contacts_and_cross_tenant_404(
        self, client, authenticated_client, user_factory
    ):
        from apps.contacts.models import Contact
        from apps.groups.models import ContactGroup, Group

        anon_resp = client.post("/groups/1/delete/", {"confirm": "true"})
        assert anon_resp.status_code == 302
        assert anon_resp.url.startswith("/accounts/login/")

        auth_client, owner = authenticated_client(
            username="grp_del_own", email="grpdelown@example.com"
        )
        other = user_factory(username="grp_del_oth", email="grpdeloth@example.com")

        group = _create_group(owner, group_name="Coworkers")
        foreign_group = _create_group(other, group_name="Foreign Group")
        c1 = _create_contact(owner, full_name="Alice Retained")
        c2 = _create_contact(owner, full_name="Bob Retained")
        _assign_member(group, c1)
        _assign_member(group, c2)

        assert auth_client.get(f"/groups/{group.pk}/delete/").status_code == 405

        # Missing confirm=true -> 400 and group remains intact
        unconfirmed = auth_client.post(f"/groups/{group.pk}/delete/")
        assert unconfirmed.status_code == 400
        assert Group.objects.filter(pk=group.pk).exists()

        # Confirmed delete -> 302 to /groups/, ContactGroup deleted, Contact retained
        confirmed = auth_client.post(f"/groups/{group.pk}/delete/", {"confirm": "true"})
        assert confirmed.status_code == 302
        assert confirmed.url == "/groups/"
        msgs = [str(m) for m in get_messages(confirmed.wsgi_request)]
        assert (
            "Group 'Coworkers' deleted. All associated contacts remain in your directory." in msgs
        )
        assert not Group.objects.filter(pk=group.pk).exists()
        assert not ContactGroup.objects.filter(group_id=group.pk).exists()
        assert Contact.objects.filter(pk=c1.pk).exists()
        assert Contact.objects.filter(pk=c2.pk).exists()

        # Cross-tenant or missing -> 404
        assert (
            auth_client.post(
                f"/groups/{foreign_group.pk}/delete/",
                {"confirm": "true"},
            ).status_code
            == 404
        )
        assert auth_client.post("/groups/999999/delete/", {"confirm": "true"}).status_code == 404
        assert Group.objects.filter(pk=foreign_group.pk).exists()


@pytest.mark.django_db
class TestGroupMemberAddAndRemoveContract:
    """Contract tests for member add/remove endpoints (group-contracts.md 2.6, 2.7)."""

    def test_add_member_standard_htmx_duplicate_and_cross_tenant_404(
        self, client, authenticated_client, user_factory
    ):
        from apps.groups.models import ContactGroup

        anon_resp = client.post("/groups/1/members/add/", {"contact_id": "1"})
        assert anon_resp.status_code == 302
        assert anon_resp.url.startswith("/accounts/login/")

        auth_client, owner = authenticated_client(
            username="grp_add_own", email="grpaddown@example.com"
        )
        other = user_factory(username="grp_add_oth", email="grpaddoth@example.com")

        group = _create_group(owner, group_name="Friends")
        foreign_group = _create_group(other, group_name="Foreign Friends")
        c1 = _create_contact(owner, full_name="Alice Friend")
        c2 = _create_contact(owner, full_name="Bob Friend")
        foreign_contact = _create_contact(other, full_name="Foreign Contact")

        assert auth_client.get(f"/groups/{group.pk}/members/add/").status_code == 405

        # Standard POST add
        resp_std = auth_client.post(
            f"/groups/{group.pk}/members/add/",
            {"contact_id": str(c1.pk)},
        )
        assert resp_std.status_code == 302
        assert resp_std.url == f"/groups/{group.pk}/"
        assert ContactGroup.objects.filter(group=group, contact=c1).exists()

        # HTMX POST add
        resp_htmx = auth_client.post(
            f"/groups/{group.pk}/members/add/",
            {"contact_id": str(c2.pk)},
            HTTP_HX_REQUEST="true",
        )
        assert resp_htmx.status_code == 200
        assert b"Bob Friend" in resp_htmx.content
        assert b'id="group-member-count-badge"' in resp_htmx.content
        assert b'hx-swap-oob="true"' in resp_htmx.content
        assert ContactGroup.objects.filter(group=group, contact=c2).exists()

        # Duplicate assignment -> 400 ERR_CONTACT_ALREADY_IN_GROUP
        resp_dup = auth_client.post(
            f"/groups/{group.pk}/members/add/",
            {"contact_id": str(c1.pk)},
        )
        assert resp_dup.status_code == 400
        assert b"Contact is already a member of this group." in resp_dup.content
        assert ContactGroup.objects.filter(group=group, contact=c1).count() == 1

        # Missing / invalid contact_id -> 400
        assert auth_client.post(f"/groups/{group.pk}/members/add/", {}).status_code == 400
        assert (
            auth_client.post(
                f"/groups/{group.pk}/members/add/",
                {"contact_id": "invalid"},
            ).status_code
            == 400
        )

        # Cross-tenant contact into own group -> 404
        assert (
            auth_client.post(
                f"/groups/{group.pk}/members/add/",
                {"contact_id": str(foreign_contact.pk)},
            ).status_code
            == 404
        )
        # Own contact into foreign group -> 404
        assert (
            auth_client.post(
                f"/groups/{foreign_group.pk}/members/add/",
                {"contact_id": str(c1.pk)},
            ).status_code
            == 404
        )
        assert not ContactGroup.objects.filter(contact=foreign_contact).exists()

    def test_remove_member_standard_htmx_retains_contact_and_404_cases(
        self, client, authenticated_client, user_factory
    ):
        from apps.contacts.models import Contact
        from apps.groups.models import ContactGroup

        anon_resp = client.post("/groups/1/members/1/remove/")
        assert anon_resp.status_code == 302
        assert anon_resp.url.startswith("/accounts/login/")

        auth_client, owner = authenticated_client(
            username="grp_rem_own", email="grpremown@example.com"
        )
        other = user_factory(username="grp_rem_oth", email="grpremoth@example.com")

        g1 = _create_group(owner, group_name="Team A")
        g2 = _create_group(owner, group_name="Team B")
        foreign_group = _create_group(other, group_name="Foreign Team")

        c1 = _create_contact(owner, full_name="Charlie Multi")
        c2 = _create_contact(owner, full_name="Diana Multi")
        c_unassigned = _create_contact(owner, full_name="Unassigned Contact")
        foreign_contact = _create_contact(other, full_name="Foreign Member")

        _assign_member(g1, c1)
        _assign_member(g2, c1)
        _assign_member(g1, c2)
        _assign_member(foreign_group, foreign_contact)

        assert auth_client.get(f"/groups/{g1.pk}/members/{c1.pk}/remove/").status_code == 405

        # Standard POST remove -> 302, retains contact and membership in g2
        resp_std = auth_client.post(f"/groups/{g1.pk}/members/{c1.pk}/remove/")
        assert resp_std.status_code == 302
        assert resp_std.url == f"/groups/{g1.pk}/"
        msgs = [str(m) for m in get_messages(resp_std.wsgi_request)]
        assert "Contact removed from group." in msgs
        assert not ContactGroup.objects.filter(group=g1, contact=c1).exists()
        assert ContactGroup.objects.filter(group=g2, contact=c1).exists()
        assert Contact.objects.filter(pk=c1.pk).exists()

        # HTMX POST remove -> 200 renders updated member section + OOB count badge + empty state
        resp_htmx = auth_client.post(
            f"/groups/{g1.pk}/members/{c2.pk}/remove/",
            HTTP_HX_REQUEST="true",
        )
        assert resp_htmx.status_code == 200
        assert resp_htmx["HX-Trigger"] == "groupMemberRemoved"
        template_names = [t.name for t in resp_htmx.templates if t.name]
        assert "groups/partials/group_member_section.html" in template_names
        assert b'id="group-member-count-badge"' in resp_htmx.content
        assert b'hx-swap-oob="true"' in resp_htmx.content
        assert b"No contacts assigned to this group yet." in resp_htmx.content
        assert b"Diana Multi" in resp_htmx.content  # restored to #group-add-contact-select
        assert not ContactGroup.objects.filter(group=g1, contact=c2).exists()
        assert Contact.objects.filter(pk=c2.pk).exists()

        # Missing membership or cross-tenant -> 404
        assert (
            auth_client.post(f"/groups/{g1.pk}/members/{c_unassigned.pk}/remove/").status_code
            == 404
        )
        assert (
            auth_client.post(
                f"/groups/{foreign_group.pk}/members/{foreign_contact.pk}/remove/"
            ).status_code
            == 404
        )
        assert (
            auth_client.post(f"/groups/{g1.pk}/members/{foreign_contact.pk}/remove/").status_code
            == 404
        )
        assert ContactGroup.objects.filter(group=foreign_group, contact=foreign_contact).exists()
