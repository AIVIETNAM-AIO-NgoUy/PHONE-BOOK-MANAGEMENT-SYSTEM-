"""Contract tests for duplicate detection and smart merge endpoints (T055)."""

import pytest
from django.contrib.messages import get_messages


def _create_contact(user, *, full_name, phones=None, **kwargs):
    from apps.contacts.models import Contact, PhoneNumber

    contact = Contact.objects.create(book=user.contact_book, full_name=full_name, **kwargs)
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
class TestDuplicateCheckContract:
    """Contract tests for POST /contacts/check-duplicate/ (contact-contracts.md Section 2.5)."""

    def test_check_duplicate_requires_authentication_and_post(self, client, authenticated_client):
        anon_resp = client.post("/contacts/check-duplicate/", {"full_name": "Alice Smith"})
        assert anon_resp.status_code == 302
        assert anon_resp.url.startswith("/accounts/login/")

        auth_client, _ = authenticated_client(username="dup_method", email="dupmethod@example.com")
        get_resp = auth_client.get("/contacts/check-duplicate/")
        assert get_resp.status_code == 405

    def test_check_duplicate_matches_phone_and_normalized_name_within_book(
        self, authenticated_client, user_factory
    ):
        client, owner = authenticated_client(username="dup_owner", email="dupowner@example.com")
        other = user_factory(username="dup_other", email="dupother@example.com")

        existing = _create_contact(
            owner,
            full_name="Michael Brown",
            phones=[("0905111222", "Mobile", True)],
        )
        _create_contact(
            other,
            full_name="Foreign Duplicate",
            phones=[("0999111222", "Mobile", True)],
        )

        # Phone match with formatting / E.164 variant
        phone_resp = client.post(
            "/contacts/check-duplicate/",
            {"full_name": "Someone Else", "phone_number": "+84 905 111 222"},
        )
        assert phone_resp.status_code == 200
        template_names = [t.name for t in phone_resp.templates if t.name]
        assert "contacts/partials/duplicate_warning_card.html" in template_names
        assert b"Michael Brown" in phone_resp.content
        assert b"0905111222" in phone_resp.content
        assert f"/contacts/{existing.pk}/".encode() in phone_resp.content
        assert b"View Existing" in phone_resp.content
        assert b"Proceed Anyway" in phone_resp.content

        # Formset phone input match (from contact_form.html hx-include)
        formset_resp = client.post(
            "/contacts/check-duplicate/",
            {
                "full_name": "",
                "phone_numbers-0-phone_number": "0905-111-222",
            },
        )
        assert formset_resp.status_code == 200
        assert b"Michael Brown" in formset_resp.content

        # Normalized full name match (case + internal extra whitespace)
        name_resp = client.post(
            "/contacts/check-duplicate/",
            {"full_name": "  michael   BROWN  ", "phone_number": ""},
        )
        assert name_resp.status_code == 200
        assert b"Michael Brown" in name_resp.content

        # Foreign user's contact must never trigger a duplicate warning
        foreign_resp = client.post(
            "/contacts/check-duplicate/",
            {"full_name": "Foreign Duplicate", "phone_number": "0999111222"},
        )
        assert foreign_resp.status_code == 200
        assert foreign_resp.content.strip() == b""

    def test_check_duplicate_respects_exclude_contact_id_and_empty_results(
        self, authenticated_client
    ):
        client, owner = authenticated_client(username="dup_excl", email="dupexcl@example.com")
        c1 = _create_contact(
            owner,
            full_name="Alice Smith",
            phones=[("0901234567", "Mobile", True)],
        )
        c2 = _create_contact(
            owner,
            full_name="Alice M. Smith",
            phones=[("0901234567", "Mobile", True)],
        )

        # When editing c2 and only c1 matches, c1 is shown with Smart Merge action
        edit_resp = client.post(
            "/contacts/check-duplicate/",
            {
                "full_name": "Alice M. Smith",
                "phone_number": "0901234567",
                "exclude_contact_id": str(c2.pk),
            },
        )
        assert edit_resp.status_code == 200
        assert b"Alice Smith" in edit_resp.content
        assert b"Alice M. Smith" not in edit_resp.content
        assert b"Smart Merge" in edit_resp.content
        assert f"target_contact_id={c1.pk}".encode() in edit_resp.content
        assert f"source_contact_id={c2.pk}".encode() in edit_resp.content

        # When c2 is deleted and editing c1 excludes c1, no duplicate remains -> empty 200
        c2.delete()
        no_dup_resp = client.post(
            "/contacts/check-duplicate/",
            {
                "full_name": "Alice Smith",
                "phone_number": "0901234567",
                "exclude_contact_id": str(c1.pk),
            },
        )
        assert no_dup_resp.status_code == 200
        assert no_dup_resp.content.strip() == b""

        # Blank input returns empty 200
        blank_resp = client.post("/contacts/check-duplicate/", {"full_name": "   "})
        assert blank_resp.status_code == 200
        assert blank_resp.content.strip() == b""


@pytest.mark.django_db
class TestSmartMergeContract:
    """Contract tests for GET/POST /contacts/merge/ (contact-contracts.md Section 2.9)."""

    def test_merge_requires_authentication(self, client):
        get_resp = client.get("/contacts/merge/?target_contact_id=1&source_contact_id=2")
        assert get_resp.status_code == 302
        assert get_resp.url.startswith("/accounts/login/")

        post_resp = client.post(
            "/contacts/merge/",
            {"target_contact_id": "1", "source_contact_id": "2"},
        )
        assert post_resp.status_code == 302
        assert post_resp.url.startswith("/accounts/login/")

    def test_merge_preview_get_returns_modal_partial_and_validates_bounds(
        self, authenticated_client, user_factory
    ):
        client, owner = authenticated_client(username="merge_prev", email="mergeprev@example.com")
        other = user_factory(username="merge_prev_other", email="mergeprevother@example.com")

        target = _create_contact(
            owner,
            full_name="Target Contact",
            email="target@example.com",
            phones=[("0901111111", "Mobile", True)],
        )
        source = _create_contact(
            owner,
            full_name="Source Contact",
            address="123 Merge St",
            phones=[("0902222222", "Work", True)],
        )
        foreign = _create_contact(
            other,
            full_name="Foreign Contact",
            phones=[("0903333333", "Mobile", True)],
        )

        # Valid HTMX preview GET
        preview_resp = client.get(
            f"/contacts/merge/?target_contact_id={target.pk}&source_contact_id={source.pk}",
            HTTP_HX_REQUEST="true",
        )
        assert preview_resp.status_code == 200
        template_names = [t.name for t in preview_resp.templates if t.name]
        assert "contacts/partials/merge_preview_modal.html" in template_names
        assert b"Target Contact" in preview_resp.content
        assert b"Source Contact" in preview_resp.content
        assert b"123 Merge St" in preview_resp.content
        assert b"0902222222" in preview_resp.content

        # Valid non-HTMX full-page preview GET
        full_preview_resp = client.get(
            f"/contacts/merge/?target_contact_id={target.pk}&source_contact_id={source.pk}"
        )
        assert full_preview_resp.status_code == 200
        full_templates = [t.name for t in full_preview_resp.templates if t.name]
        assert "contacts/merge_preview.html" in full_templates
        assert "contacts/partials/merge_preview_modal.html" in full_templates

        # Self-merge preview -> 400
        self_resp = client.get(
            f"/contacts/merge/?target_contact_id={target.pk}&source_contact_id={target.pk}"
        )
        assert self_resp.status_code == 400

        # Missing params -> 400
        missing_params = client.get(f"/contacts/merge/?target_contact_id={target.pk}")
        assert missing_params.status_code == 400

        # Cross-tenant or missing IDs -> 404
        cross_resp = client.get(
            f"/contacts/merge/?target_contact_id={target.pk}&source_contact_id={foreign.pk}"
        )
        assert cross_resp.status_code == 404

        missing_id_resp = client.get(
            f"/contacts/merge/?target_contact_id={target.pk}&source_contact_id=999999"
        )
        assert missing_id_resp.status_code == 404

    def test_merge_post_redirects_on_success_and_rejects_self_or_cross_tenant(
        self, authenticated_client, user_factory
    ):
        from apps.contacts.models import Contact

        client, owner = authenticated_client(username="merge_post", email="mergepost@example.com")
        other = user_factory(username="merge_post_other", email="mergepostother@example.com")

        target = _create_contact(
            owner,
            full_name="Keep Me",
            phones=[("0901111111", "Mobile", True)],
        )
        source = _create_contact(
            owner,
            full_name="Merge Me",
            email="merge@example.com",
            phones=[("0902222222", "Home", True)],
        )
        foreign = _create_contact(
            other,
            full_name="Foreign Untouched",
            phones=[("0903333333", "Mobile", True)],
        )

        # Self-merge -> 400
        self_resp = client.post(
            "/contacts/merge/",
            {"target_contact_id": str(target.pk), "source_contact_id": str(target.pk)},
        )
        assert self_resp.status_code == 400
        assert b"Cannot merge a contact into itself." in self_resp.content

        # Missing IDs -> 400
        bad_resp = client.post("/contacts/merge/", {"target_contact_id": str(target.pk)})
        assert bad_resp.status_code == 400

        # Cross-tenant -> 404 and leaves both intact
        cross_resp = client.post(
            "/contacts/merge/",
            {"target_contact_id": str(target.pk), "source_contact_id": str(foreign.pk)},
        )
        assert cross_resp.status_code == 404
        assert Contact.objects.filter(pk=target.pk).exists()
        assert Contact.objects.filter(pk=foreign.pk).exists()

        # Non-existent -> 404
        missing_resp = client.post(
            "/contacts/merge/",
            {"target_contact_id": str(target.pk), "source_contact_id": "999999"},
        )
        assert missing_resp.status_code == 404

        # Valid merge -> 302 to /contacts/<target.pk>/ with flash message
        ok_resp = client.post(
            "/contacts/merge/",
            {"target_contact_id": str(target.pk), "source_contact_id": str(source.pk)},
        )
        assert ok_resp.status_code == 302
        assert ok_resp.url == f"/contacts/{target.pk}/"
        msgs = [str(m) for m in get_messages(ok_resp.wsgi_request)]
        assert "Contacts merged successfully without data loss." in msgs
        assert not Contact.objects.filter(pk=source.pk).exists()
        target.refresh_from_db()
        assert target.email == "merge@example.com"
