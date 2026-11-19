"""Integration tests for User Story 4: Duplicate Detection & Smart Merge (T056)."""

from datetime import date, datetime, timezone

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
class TestDuplicateDetectionAndSmartMergeIntegration:
    """End-to-end integration tests for US4 Scenarios 1-3, FR-017, FR-018, EC-001, and SC-005."""

    def test_us4_proactive_duplicate_warning_and_non_blocking_proceed_anyway(
        self, authenticated_client
    ):
        from apps.contacts.models import Contact

        client, owner = authenticated_client(username="us4_warn", email="us4warn@example.com")
        existing = _seed_contact(
            owner,
            full_name="Michael Brown",
            phones=[("0905111222", "Mobile", True)],
        )

        # 1. Create form renders HTMX blur duplicate detection wiring
        form_page = client.get("/contacts/create/")
        assert form_page.status_code == 200
        assert b"/contacts/check-duplicate/" in form_page.content
        assert b'id="duplicate-warning-container"' in form_page.content

        # 2. User enters matching phone variant -> non-blocking soft warning card
        warn_resp = client.post(
            "/contacts/check-duplicate/",
            {
                "full_name": "Mike Brown",
                "phone_numbers-0-phone_number": "0905 111 222",
            },
            HTTP_HX_REQUEST="true",
        )
        assert warn_resp.status_code == 200
        assert b"Michael Brown" in warn_resp.content
        assert b"0905111222" in warn_resp.content
        assert f"/contacts/{existing.pk}/".encode() in warn_resp.content
        assert b"Proceed Anyway" in warn_resp.content

        # 3. User ignores warning and creates separate contact anyway (FR-018 soft warning)
        create_resp = client.post(
            "/contacts/create/",
            {
                "full_name": "Mike Brown",
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "0",
                "phone_numbers-0-phone_number": "0905111222",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
            },
        )
        assert create_resp.status_code == 302
        created = Contact.objects.get(book=owner.contact_book, full_name="Mike Brown")
        assert created.pk != existing.pk

        # 4. On edit of created contact, duplicate check excludes itself and offers Smart Merge
        edit_warn = client.post(
            "/contacts/check-duplicate/",
            {
                "full_name": "Mike Brown",
                "phone_numbers-0-phone_number": "0905111222",
                "exclude_contact_id": str(created.pk),
            },
            HTTP_HX_REQUEST="true",
        )
        assert edit_warn.status_code == 200
        assert b"Michael Brown" in edit_warn.content
        assert b"Smart Merge" in edit_warn.content

    def test_us4_guided_smart_merge_preserves_all_data_without_loss(self, user_factory):
        from apps.contacts.models import Contact, PhoneNumber

        owner = user_factory(username="us4_merge", email="us4merge@example.com")
        earlier = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
        later = datetime(2026, 11, 10, 14, 30, tzinfo=timezone.utc)

        target = _seed_contact(
            owner,
            full_name="Michael Brown",
            email="m1@work.com",
            address=None,
            work_address="100 Enterprise Way",
            avatar=None,
            birthday=None,
            notes="Target primary note.",
            interaction_count=4,
            last_contacted_at=earlier,
            phones=[
                ("0905111222", "Mobile", True),
                ("02838111222", "Work", False),
            ],
        )
        source = _seed_contact(
            owner,
            full_name="Mike Brown",
            email="m2@personal.com",
            address="45 Maple Ave",
            work_address="Old Startup Office",
            avatar="/media/contact_avatars/mike.png",
            birthday=date(1992, 8, 20),
            notes="Source secondary note.",
            interaction_count=7,
            last_contacted_at=later,
            phones=[
                ("0933444555", "Mobile", True),
                ("+84905111222", "Other", False),
                ("0911222333", "Home", False),
            ],
        )

        client = Client(enforce_csrf_checks=True)
        client.force_login(owner)

        # Fetch CSRF token via contact detail page
        detail_page = client.get(f"/contacts/{target.pk}/")
        assert detail_page.status_code == 200
        csrf_token = client.cookies["csrftoken"].value

        # Step 1: Preview merge via HTMX GET
        preview_resp = client.get(
            f"/contacts/merge/?target_contact_id={target.pk}&source_contact_id={source.pk}",
            HTTP_HX_REQUEST="true",
        )
        assert preview_resp.status_code == 200
        assert b"Michael Brown" in preview_resp.content
        assert b"Mike Brown" in preview_resp.content
        assert b"m1@work.com" in preview_resp.content
        assert b"45 Maple Ave" in preview_resp.content
        assert b"0933444555" in preview_resp.content

        # Step 2: Execute merge with CSRF token
        merge_resp = client.post(
            "/contacts/merge/",
            {
                "target_contact_id": str(target.pk),
                "source_contact_id": str(source.pk),
                "csrfmiddlewaretoken": csrf_token,
            },
        )
        assert merge_resp.status_code == 302
        assert merge_resp.url == f"/contacts/{target.pk}/"

        # Step 3: Verify complete zero-loss consolidation
        assert not Contact.objects.filter(pk=source.pk).exists()
        target.refresh_from_db()

        # Non-empty target fields preserved
        assert target.full_name == "Michael Brown"
        assert target.email == "m1@work.com"
        assert target.work_address == "100 Enterprise Way"

        # Blank target fields filled from source
        assert target.address == "45 Maple Ave"
        assert target.avatar == "/media/contact_avatars/mike.png"
        assert target.birthday == date(1992, 8, 20)

        # Notes concatenated with audit delimiter
        assert "Target primary note." in target.notes
        assert "Source secondary note." in target.notes
        assert "--- Merged Note ---" in target.notes

        # Interaction metrics aggregated
        assert target.interaction_count == 11
        assert target.last_contacted_at == later

        # Phone numbers re-parented: duplicate +84905111222 discarded,
        # source primary 0933444555 demoted to is_primary=False, 0911222333 kept as secondary
        phones = list(PhoneNumber.objects.filter(contact=target).order_by("id"))
        phone_map = {p.phone_number: p for p in phones}
        assert set(phone_map.keys()) == {"0905111222", "02838111222", "0933444555", "0911222333"}
        assert phone_map["0905111222"].is_primary is True
        assert phone_map["02838111222"].is_primary is False
        assert phone_map["0933444555"].is_primary is False
        assert phone_map["0911222333"].is_primary is False
        assert PhoneNumber.objects.filter(contact=target, is_primary=True).count() == 1

    def test_cross_tenant_duplicate_and_merge_isolation(self, user_factory):
        from apps.contacts.models import Contact

        owner = user_factory(username="iso_m_a", email="isoma@example.com")
        attacker = user_factory(username="iso_m_b", email="isomb@example.com")

        victim_target = _seed_contact(
            owner,
            full_name="Victim Target",
            phones=[("0908887777", "Mobile", True)],
        )
        attacker_source = _seed_contact(
            attacker,
            full_name="Attacker Source",
            phones=[("0908887777", "Mobile", True)],
        )

        attacker_client = Client()
        attacker_client.force_login(attacker)

        # Attacker duplicate check never sees victim's contact
        dup_resp = attacker_client.post(
            "/contacts/check-duplicate/",
            {"full_name": "Victim Target", "phone_number": "0908887777"},
        )
        assert dup_resp.status_code == 200
        assert b"Victim Target" not in dup_resp.content

        # Attacker cannot merge into victim's contact
        merge_resp = attacker_client.post(
            "/contacts/merge/",
            {
                "target_contact_id": str(victim_target.pk),
                "source_contact_id": str(attacker_source.pk),
            },
        )
        assert merge_resp.status_code == 404
        assert Contact.objects.filter(pk=victim_target.pk).exists()
        assert Contact.objects.filter(pk=attacker_source.pk).exists()
