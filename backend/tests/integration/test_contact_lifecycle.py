"""Integration tests for User Story 2: Core Contact Lifecycle Management (T032)."""

import re

import pytest
from django.test import Client


@pytest.mark.django_db
class TestContactLifecycleIntegration:
    """End-to-end integration tests covering US2 Scenarios 1-5, EC-002, EC-008, and EC-010."""

    def test_full_contact_crud_lifecycle_and_validation(self, authenticated_client):
        from apps.contacts.models import Contact, ContactBook, PhoneNumber

        client, user = authenticated_client(username="lifecycle_u", email="life@example.com")

        # 1. Invalid submission preserves input and aborts persistence (US2.2, FR-010, EC-008)
        bad_resp = client.post(
            "/contacts/create/",
            {
                "full_name": "Alice Smith",
                "email": "alice@example.org",
                "notes": "Keep me on error",
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "0",
                "phone_numbers-0-phone_number": "123",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
            },
        )
        assert bad_resp.status_code == 400
        assert b"Keep me on error" in bad_resp.content
        assert Contact.objects.filter(book=user.contact_book).count() == 0

        # 2. Valid multi-attribute creation with Vietnamese & E.164 numbers (US2.1, EC-008)
        create_resp = client.post(
            "/contacts/create/",
            {
                "full_name": "Alice Smith",
                "email": "alice@example.org",
                "address": "12 Nguyen Hue, Q1",
                "work_address": "Bitexco Tower",
                "birthday": "1994-03-10",
                "notes": "College friend",
                "phone_numbers-TOTAL_FORMS": "2",
                "phone_numbers-INITIAL_FORMS": "0",
                "phone_numbers-0-phone_number": "0901234567",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
                "phone_numbers-1-phone_number": "+84-28-3822-9999",
                "phone_numbers-1-phone_type": "Work",
            },
        )
        assert create_resp.status_code == 302
        contact = Contact.objects.get(book=user.contact_book, full_name="Alice Smith")
        assert create_resp.url == f"/contacts/{contact.pk}/"
        assert PhoneNumber.objects.filter(contact=contact).count() == 2

        # 3. Inspect detail view (FR-012)
        detail_resp = client.get(f"/contacts/{contact.pk}/")
        assert detail_resp.status_code == 200
        assert b"0901234567" in detail_resp.content
        assert b"+842838229999" in detail_resp.content
        assert b"College friend" in detail_resp.content

        # 4. Update contact details and add a third phone number (US2.3, FR-013)
        p1, p2 = list(contact.phone_numbers.order_by("id"))
        old_updated_at = contact.updated_at
        edit_resp = client.post(
            f"/contacts/{contact.pk}/edit/",
            {
                "full_name": "Alice M. Smith",
                "email": "alice.m@example.org",
                "address": "12 Nguyen Hue, Q1",
                "work_address": "Saigon Centre",
                "birthday": "1994-03-10",
                "notes": "Updated notes",
                "phone_numbers-TOTAL_FORMS": "3",
                "phone_numbers-INITIAL_FORMS": "2",
                "phone_numbers-0-id": str(p1.pk),
                "phone_numbers-0-contact": str(contact.pk),
                "phone_numbers-0-phone_number": "0901234567",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
                "phone_numbers-1-id": str(p2.pk),
                "phone_numbers-1-contact": str(contact.pk),
                "phone_numbers-1-phone_number": "+842838229999",
                "phone_numbers-1-phone_type": "Work",
                "phone_numbers-2-phone_number": "0912345678",
                "phone_numbers-2-phone_type": "Home",
            },
        )
        assert edit_resp.status_code == 302
        contact.refresh_from_db()
        assert contact.full_name == "Alice M. Smith"
        assert contact.notes == "Updated notes"
        assert contact.updated_at >= old_updated_at
        assert contact.phone_numbers.count() == 3

        # 5. Deletion without confirmation aborts and leaves data intact (US2.5, SC-003)
        abort_resp = client.post(f"/contacts/{contact.pk}/delete/", {})
        assert abort_resp.status_code == 400
        assert Contact.objects.filter(pk=contact.pk).exists()
        assert PhoneNumber.objects.filter(contact=contact).count() == 3

        # 6. Confirmed deletion cascades to PhoneNumber while preserving ContactBook (US2.4, EC-002)
        # Note: Group/ContactGroup (Phase 8) and FavoriteItem (Phase 7) cascades will be
        # verified once those models are introduced in Phases 7 and 8.
        del_resp = client.post(f"/contacts/{contact.pk}/delete/", {"confirm": "true"})
        assert del_resp.status_code == 302
        assert del_resp.url == "/contacts/"
        assert not Contact.objects.filter(pk=contact.pk).exists()
        assert not PhoneNumber.objects.filter(contact_id=contact.pk).exists()
        assert ContactBook.objects.filter(pk=user.contact_book.pk).exists()

    def test_concurrent_delete_idempotency_returns_clean_404(self, user_factory):
        """EC-010: Concurrent second delete on already-deleted contact returns clean 404."""
        from apps.contacts.models import Contact, PhoneNumber

        user = user_factory(username="conc_u", email="concu@example.com", password="Password123!")
        contact = Contact.objects.create(book=user.contact_book, full_name="Race Target")
        PhoneNumber.objects.create(
            contact=contact, phone_number="0909876543", phone_type="Mobile", is_primary=True
        )

        session_a = Client()
        session_b = Client()
        session_a.force_login(user)
        session_b.force_login(user)

        first_resp = session_a.post(f"/contacts/{contact.pk}/delete/", {"confirm": "true"})
        assert first_resp.status_code == 302
        assert not Contact.objects.filter(pk=contact.pk).exists()

        second_resp = session_b.post(f"/contacts/{contact.pk}/delete/", {"confirm": "true"})
        assert second_resp.status_code == 404

    def test_csrf_enforced_and_multi_tenant_isolation_in_lifecycle(self, user_factory):
        """FR-042 & Constitution IV: CSRF required and cross-tenant operations fail safely."""
        from apps.contacts.models import Contact, PhoneNumber

        owner = user_factory(username="tenant_a", email="tenanta@example.com")
        attacker = user_factory(username="tenant_b", email="tenantb@example.com")

        contact = Contact.objects.create(book=owner.contact_book, full_name="Private Contact")
        PhoneNumber.objects.create(
            contact=contact, phone_number="0901122334", phone_type="Mobile", is_primary=True
        )

        # CSRF enforced
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(owner)
        assert csrf_client.post("/contacts/create/", {"full_name": "X"}).status_code == 403

        # Attacker cannot view, edit, or delete owner's contact
        attacker_client = Client()
        attacker_client.force_login(attacker)
        assert attacker_client.get(f"/contacts/{contact.pk}/").status_code == 404
        assert attacker_client.get(f"/contacts/{contact.pk}/edit/").status_code == 404
        victim_resp = attacker_client.post(f"/contacts/{contact.pk}/delete/", {"confirm": "true"})
        assert victim_resp.status_code == 404
        assert Contact.objects.filter(pk=contact.pk).exists()

    def test_contact_form_rerender_keeps_deleted_phone_row_hidden_and_primary_radio_synced(
        self, authenticated_client
    ):
        """H3 regression: deleted row stays hidden and unchecked on validation re-render."""
        from apps.contacts.models import Contact, PhoneNumber

        client, owner = authenticated_client(username="h3_user", email="h3user@example.com")
        contact = Contact.objects.create(
            book=owner.contact_book,
            full_name="H3 Contact",
            email="valid@example.com",
        )
        p1 = PhoneNumber.objects.create(
            contact=contact, phone_number="0901111111", phone_type="Mobile", is_primary=True
        )
        p2 = PhoneNumber.objects.create(
            contact=contact, phone_number="0902222222", phone_type="Work", is_primary=False
        )

        # Mark secondary row deleted AND submit invalid email to force 400 re-render
        resp = client.post(
            f"/contacts/{contact.pk}/edit/",
            {
                "full_name": "H3 Contact",
                "email": "not-an-email",
                "phone_numbers-TOTAL_FORMS": "2",
                "phone_numbers-INITIAL_FORMS": "2",
                "phone_numbers-0-id": str(p1.pk),
                "phone_numbers-0-contact": str(contact.pk),
                "phone_numbers-0-phone_number": "0901111111",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
                "phone_numbers-1-id": str(p2.pk),
                "phone_numbers-1-contact": str(contact.pk),
                "phone_numbers-1-phone_number": "0902222222",
                "phone_numbers-1-phone_type": "Work",
                "phone_numbers-1-is_primary": "on",
                "phone_numbers-1-DELETE": "on",
            },
        )
        assert resp.status_code == 400
        html = resp.content.decode("utf-8")
        rows = re.findall(r"<div[^>]*data-phone-row[^>]*>.*?</div>\s*</div>", html, flags=re.S)
        assert len(rows) >= 2
        row0, row1 = rows[0], rows[1]

        assert 'data-deleted="true"' not in row0
        assert 'data-deleted="true"' in row1
        assert 'style="display: none;"' in row1

        # Row 0 radio checked; deleted Row 1 radio NOT checked
        radio0_match = re.search(r'<input[^>]*class="[^"]*primary-phone-radio[^"]*"[^>]*>', row0)
        radio1_match = re.search(r'<input[^>]*class="[^"]*primary-phone-radio[^"]*"[^>]*>', row1)
        assert radio0_match and "checked" in radio0_match.group(0)
        assert radio1_match and "checked" not in radio1_match.group(0)

        # Verify database unchanged on failed validation
        contact.refresh_from_db()
        assert contact.email == "valid@example.com"
        assert contact.phone_numbers.count() == 2

    def test_contact_lifecycle_with_group_ids_and_foreign_group_rejection(
        self, authenticated_client, user_factory
    ):
        """H2 lifecycle: assign, update, clear group_ids and reject foreign IDs."""
        from apps.contacts.models import Contact
        from apps.groups.models import ContactGroup, Group

        client, owner = authenticated_client(username="h2_life_u", email="h2life@example.com")
        other = user_factory(username="h2_life_o", email="h2lifeo@example.com")

        g1 = Group.objects.create(book=owner.contact_book, group_name="Engineering")
        g2 = Group.objects.create(book=owner.contact_book, group_name="Design")
        foreign_g = Group.objects.create(book=other.contact_book, group_name="Foreign Org")

        create_resp = client.post(
            "/contacts/create/",
            {
                "full_name": "Grouped Lifecycle",
                "group_ids": [str(g1.pk)],
                "_groups_submitted": "1",
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "0",
                "phone_numbers-0-phone_number": "0905551111",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
            },
        )
        assert create_resp.status_code == 302
        contact = Contact.objects.get(book=owner.contact_book, full_name="Grouped Lifecycle")
        phone = contact.phone_numbers.get()
        assert list(
            ContactGroup.objects.filter(contact=contact).values_list("group_id", flat=True)
        ) == [g1.pk]

        # Foreign group_id tampered on edit -> 400 and membership unchanged
        tamper_resp = client.post(
            f"/contacts/{contact.pk}/edit/",
            {
                "full_name": "Grouped Lifecycle",
                "group_ids": [str(foreign_g.pk)],
                "_groups_submitted": "1",
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "1",
                "phone_numbers-0-id": str(phone.pk),
                "phone_numbers-0-contact": str(contact.pk),
                "phone_numbers-0-phone_number": "0905551111",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
            },
        )
        assert tamper_resp.status_code == 400
        assert list(
            ContactGroup.objects.filter(contact=contact).values_list("group_id", flat=True)
        ) == [g1.pk]

        # Valid edit swaps g1 -> g2
        swap_resp = client.post(
            f"/contacts/{contact.pk}/edit/",
            {
                "full_name": "Grouped Lifecycle",
                "group_ids": [str(g2.pk)],
                "_groups_submitted": "1",
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "1",
                "phone_numbers-0-id": str(phone.pk),
                "phone_numbers-0-contact": str(contact.pk),
                "phone_numbers-0-phone_number": "0905551111",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
            },
        )
        assert swap_resp.status_code == 302
        assert list(
            ContactGroup.objects.filter(contact=contact).values_list("group_id", flat=True)
        ) == [g2.pk]
