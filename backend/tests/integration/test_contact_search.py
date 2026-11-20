"""Integration tests for User Story 3: Contact Discovery, Search & Sorting (T046)."""

from urllib.parse import quote

import pytest


def _seed_contact(user, *, full_name, email=None, phones=None):
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
class TestContactSearchAndSortingIntegration:
    """End-to-end integration tests for US3 Acceptance Scenarios 1-3 and EC-007."""

    def test_us3_scenario_1_partial_match_across_attributes(self, authenticated_client):
        client, owner = authenticated_client(username="us3_s1", email="us3s1@example.com")
        _seed_contact(
            owner,
            full_name="Robert Johnson",
            email="rob@corp.com",
            phones=[("0912345678", "Mobile", True)],
        )
        _seed_contact(
            owner,
            full_name="Roberta Lee",
            email="roberta@edu.vn",
            phones=[("0987654321", "Mobile", True)],
        )

        # Keyword "Rob" returns both
        resp_rob = client.get("/contacts/search/?q=Rob", HTTP_HX_REQUEST="true")
        assert resp_rob.status_code == 200
        assert b"Robert Johnson" in resp_rob.content
        assert b"Roberta Lee" in resp_rob.content

        # Keyword "3456" returns only Robert Johnson
        resp_phone = client.get("/contacts/search/?q=3456", HTTP_HX_REQUEST="true")
        assert resp_phone.status_code == 200
        assert b"Robert Johnson" in resp_phone.content
        assert b"Roberta Lee" not in resp_phone.content

        # Keyword "corp.com" returns only Robert Johnson
        resp_email = client.get("/contacts/search/?q=corp.com", HTTP_HX_REQUEST="true")
        assert resp_email.status_code == 200
        assert b"Robert Johnson" in resp_email.content
        assert b"Roberta Lee" not in resp_email.content

    def test_us3_scenario_2_no_matches_and_clear_search_flow(self, authenticated_client):
        client, owner = authenticated_client(username="us3_s2", email="us3s2@example.com")
        _seed_contact(owner, full_name="Alice Smith", email="alice@example.org")

        # Search yielding 0 matches shows friendly empty state with Clear Search link
        no_match = client.get("/contacts/search/?q=UnmatchedTerm", HTTP_HX_REQUEST="true")
        assert no_match.status_code == 200
        assert b"No matching contacts found" in no_match.content
        assert b'href="/contacts/"' in no_match.content
        assert b"Clear Search" in no_match.content

        # Following Clear Search returns full directory
        cleared = client.get("/contacts/")
        assert cleared.status_code == 200
        assert b"Alice Smith" in cleared.content

    def test_us3_scenario_3_alphabetical_sorting_and_with_search(self, authenticated_client):
        client, owner = authenticated_client(username="us3_s3", email="us3s3@example.com")
        _seed_contact(owner, full_name="Bob Adams", phones=[("0901111111", "Mobile", True)])
        _seed_contact(owner, full_name="Alice Adams", phones=[("0902222222", "Mobile", True)])
        _seed_contact(owner, full_name="Zack Adams", phones=[("0903333333", "Mobile", True)])

        asc = client.get("/contacts/?sort=name_asc")
        assert [c.full_name for c in asc.context["contacts"]] == [
            "Alice Adams",
            "Bob Adams",
            "Zack Adams",
        ]

        desc = client.get("/contacts/?sort=name_desc")
        assert [c.full_name for c in desc.context["contacts"]] == [
            "Zack Adams",
            "Bob Adams",
            "Alice Adams",
        ]

        # Sorting combined with live search query
        search_desc = client.get("/contacts/search/?q=Adams&sort=name_desc", HTTP_HX_REQUEST="true")
        assert search_desc.status_code == 200
        assert [c.full_name for c in search_desc.context["contacts"]] == [
            "Zack Adams",
            "Bob Adams",
            "Alice Adams",
        ]

    def test_ec007_whitespace_trimming_and_sql_wildcard_punctuation_safety(
        self, authenticated_client
    ):
        client, owner = authenticated_client(username="ec007_u", email="ec007@example.com")
        _seed_contact(
            owner,
            full_name="O'Connor 100% Real",
            email="user+tag@example.com",
            phones=[("+84-901-234", "Mobile", True)],
        )
        _seed_contact(
            owner,
            full_name="dev_user\\admin",
            email="dev_user@example.com",
            phones=[("0909998888", "Mobile", True)],
        )
        _seed_contact(
            owner,
            full_name="Normal Contact",
            email="normal@example.com",
            phones=[("0907776666", "Mobile", True)],
        )

        # Leading & trailing whitespace trimmed
        trimmed_query = quote("   O'Connor   ")
        trimmed_resp = client.get(f"/contacts/search/?q={trimmed_query}")
        assert trimmed_resp.status_code == 200
        assert [c.full_name for c in trimmed_resp.context["contacts"]] == ["O'Connor 100% Real"]

        # '%' must NOT act as SQL wildcard matching Normal Contact
        percent_resp = client.get(f"/contacts/search/?q={quote('%')}")
        assert percent_resp.status_code == 200
        assert [c.full_name for c in percent_resp.context["contacts"]] == ["O'Connor 100% Real"]

        # '_' must NOT act as single-char SQL wildcard matching Normal Contact
        underscore_resp = client.get("/contacts/search/?q=_")
        assert underscore_resp.status_code == 200
        assert [c.full_name for c in underscore_resp.context["contacts"]] == ["dev_user\\admin"]

        # Backslash, quotes, plus, hyphen, @ handled cleanly with zero SQL errors
        for special_q, expected_names in [
            ("\\", ["dev_user\\admin"]),
            ("O'Connor", ["O'Connor 100% Real"]),
            ("+84-901", ["O'Connor 100% Real"]),
            ("user+tag@", ["O'Connor 100% Real"]),
            ('"', []),
        ]:
            resp = client.get(f"/contacts/search/?q={quote(special_q)}")
            assert resp.status_code == 200
            assert [c.full_name for c in resp.context["contacts"]] == expected_names

    def test_distinct_deduplication_when_multiple_phones_match(self, authenticated_client):
        client, owner = authenticated_client(username="dedup_u", email="dedup@example.com")
        multi_phone_contact = _seed_contact(
            owner,
            full_name="Multi Phone Contact",
            email="multi@example.com",
            phones=[
                ("0901112222", "Mobile", True),
                ("0901113333", "Work", False),
                ("0901114444", "Home", False),
            ],
        )

        resp = client.get("/contacts/search/?q=090111")
        assert resp.status_code == 200
        contacts = list(resp.context["contacts"])
        assert len(contacts) == 1
        assert contacts[0].pk == multi_phone_contact.pk

    def test_multi_tenant_isolation_during_search(self, authenticated_client, user_factory):
        client, owner = authenticated_client(username="iso_a", email="isoa@example.com")
        other = user_factory(username="iso_b", email="isob@example.com")

        _seed_contact(owner, full_name="Shared Keyword Alice", email="alice@a.com")
        _seed_contact(
            other,
            full_name="Shared Keyword Secret",
            email="secret@b.com",
            phones=[("0912345678", "Mobile", True)],
        )

        resp = client.get("/contacts/search/?q=Shared Keyword")
        assert resp.status_code == 200
        assert [c.full_name for c in resp.context["contacts"]] == ["Shared Keyword Alice"]

        phone_resp = client.get("/contacts/search/?q=0912345678")
        assert phone_resp.status_code == 200
        assert list(phone_resp.context["contacts"]) == []
