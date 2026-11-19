"""Contract tests for contact search and sorting endpoints (T045)."""

import pytest


def _create_contact(user, *, full_name, email=None, phones=None):
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


@pytest.mark.django_db
class TestContactSearchContract:
    """Contract tests for GET /contacts/search/ (contact-contracts.md Section 2.2)."""

    def test_search_requires_authentication(self, client):
        response = client.get("/contacts/search/?q=Rob")
        assert response.status_code == 302
        assert response.url.startswith("/accounts/login/")

    def test_search_scopes_strictly_to_user_contact_book(self, authenticated_client, user_factory):
        client, owner = authenticated_client(
            username="search_owner", email="searchowner@example.com"
        )
        other = user_factory(username="search_other", email="searchother@example.com")

        _create_contact(
            owner,
            full_name="Robert Johnson",
            email="rob@corp.com",
            phones=[("0912345678", "Mobile", True)],
        )
        _create_contact(
            other,
            full_name="Robert Foreign",
            email="rob@foreign.com",
            phones=[("0912345999", "Mobile", True)],
        )

        resp = client.get("/contacts/search/?q=Rob")
        assert resp.status_code == 200
        assert b"Robert Johnson" in resp.content
        assert b"Robert Foreign" not in resp.content

    def test_search_matches_partial_name_email_and_phone_via_htmx(self, authenticated_client):
        client, owner = authenticated_client(username="htmx_search", email="htmxsearch@example.com")

        _create_contact(
            owner,
            full_name="Robert Johnson",
            email="rob@corp.com",
            phones=[("0912345678", "Mobile", True)],
        )
        _create_contact(
            owner,
            full_name="Roberta Lee",
            email="roberta@edu.vn",
            phones=[("0987654321", "Mobile", True), ("02838227777", "Work", False)],
        )

        # Partial name match via HTMX returns contact_table_rows partial without full layout
        name_resp = client.get("/contacts/search/?q=rob", HTTP_HX_REQUEST="true")
        assert name_resp.status_code == 200
        template_names = [t.name for t in name_resp.templates if t.name]
        assert "contacts/partials/contact_table_rows.html" in template_names
        assert b"<!DOCTYPE html>" not in name_resp.content
        assert b"Robert Johnson" in name_resp.content
        assert b"Roberta Lee" in name_resp.content

        # Partial phone match (including secondary phone)
        phone_resp = client.get("/contacts/search/?q=3456", HTTP_HX_REQUEST="true")
        assert phone_resp.status_code == 200
        assert b"Robert Johnson" in phone_resp.content
        assert b"Roberta Lee" not in phone_resp.content

        secondary_phone_resp = client.get("/contacts/search/?q=227777", HTTP_HX_REQUEST="true")
        assert secondary_phone_resp.status_code == 200
        assert b"Roberta Lee" in secondary_phone_resp.content
        assert b"Robert Johnson" not in secondary_phone_resp.content

        # Partial email match
        email_resp = client.get("/contacts/search/?q=edu.vn", HTTP_HX_REQUEST="true")
        assert email_resp.status_code == 200
        assert b"Roberta Lee" in email_resp.content
        assert b"Robert Johnson" not in email_resp.content

    def test_search_htmx_zero_matches_renders_empty_search_state_partial(
        self, authenticated_client
    ):
        client, owner = authenticated_client(username="zero_htmx", email="zerohtmx@example.com")
        _create_contact(owner, full_name="Alice Smith", email="alice@example.com")

        resp = client.get("/contacts/search/?q=NonExistentContactXYZ", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        template_names = [t.name for t in resp.templates if t.name]
        assert "contacts/partials/empty_search_state.html" in template_names
        assert b"Clear Search" in resp.content
        assert b"NonExistentContactXYZ" in resp.content

    def test_search_empty_query_returns_standard_unfiltered_list(self, authenticated_client):
        client, owner = authenticated_client(username="empty_q", email="emptyq@example.com")
        _create_contact(owner, full_name="Alice Smith")
        _create_contact(owner, full_name="Bob Jones")

        htmx_resp = client.get("/contacts/search/?q=   ", HTTP_HX_REQUEST="true")
        assert htmx_resp.status_code == 200
        template_names = [t.name for t in htmx_resp.templates if t.name]
        assert "contacts/partials/contact_table_rows.html" in template_names
        assert b"Alice Smith" in htmx_resp.content
        assert b"Bob Jones" in htmx_resp.content

        full_resp = client.get("/contacts/search/?q=")
        assert full_resp.status_code == 200
        full_templates = [t.name for t in full_resp.templates if t.name]
        assert "contacts/contact_list.html" in full_templates
        assert b"Alice Smith" in full_resp.content
        assert b"Bob Jones" in full_resp.content
        assert b'id="contact-search-clear-btn"' in full_resp.content
        assert b"syncClearButtonVisibility" in full_resp.content

    def test_search_non_htmx_full_page_fallback_renders_contact_list(self, authenticated_client):
        client, owner = authenticated_client(username="full_search", email="fullsearch@example.com")
        _create_contact(owner, full_name="Charlie Brown", email="charlie@example.com")
        _create_contact(owner, full_name="Dana White", email="dana@example.com")

        resp = client.get("/contacts/search/?q=Charlie")
        assert resp.status_code == 200
        template_names = [t.name for t in resp.templates if t.name]
        assert "contacts/contact_list.html" in template_names
        assert b"<!DOCTYPE html>" in resp.content
        assert b"Charlie Brown" in resp.content
        assert b"Dana White" not in resp.content
        assert resp.context["search_query"] == "Charlie"

        no_match_resp = client.get("/contacts/search/?q=NoSuchPerson")
        assert no_match_resp.status_code == 200
        assert b"<!DOCTYPE html>" in no_match_resp.content
        assert b"Clear Search" in no_match_resp.content


@pytest.mark.django_db
class TestContactSortingContract:
    """Contract tests for GET /contacts/?sort=... (contact-contracts.md Section 2.1)."""

    def test_list_sorting_name_asc_name_desc_recent_and_invalid_fallback(
        self, authenticated_client
    ):
        client, owner = authenticated_client(username="sort_u", email="sortu@example.com")
        alpha = _create_contact(
            owner, full_name="Alpha Person", phones=[("0901111111", "Mobile", True)]
        )
        zulu = _create_contact(
            owner, full_name="Zulu Person", phones=[("0902222222", "Mobile", True)]
        )
        mid = _create_contact(
            owner, full_name="Mike Person", phones=[("0903333333", "Mobile", True)]
        )

        # Touch alpha last so it is the most recently updated
        alpha.notes = "Updated most recently"
        alpha.save()

        # name_asc
        asc_resp = client.get("/contacts/?sort=name_asc")
        assert asc_resp.status_code == 200
        assert asc_resp.context["current_sort"] == "name_asc"
        asc_ids = [c.pk for c in asc_resp.context["contacts"]]
        assert asc_ids == [alpha.pk, mid.pk, zulu.pk]

        # name_desc
        desc_resp = client.get("/contacts/?sort=name_desc")
        assert desc_resp.status_code == 200
        assert desc_resp.context["current_sort"] == "name_desc"
        desc_ids = [c.pk for c in desc_resp.context["contacts"]]
        assert desc_ids == [zulu.pk, mid.pk, alpha.pk]

        # recent
        recent_resp = client.get("/contacts/?sort=recent")
        assert recent_resp.status_code == 200
        assert recent_resp.context["current_sort"] == "recent"
        recent_ids = [c.pk for c in recent_resp.context["contacts"]]
        assert recent_ids[0] == alpha.pk

        # invalid sort falls back cleanly to name_asc
        invalid_resp = client.get("/contacts/?sort=invalid_sort_key")
        assert invalid_resp.status_code == 200
        assert invalid_resp.context["current_sort"] == "name_asc"
        assert [c.pk for c in invalid_resp.context["contacts"]] == [alpha.pk, mid.pk, zulu.pk]
