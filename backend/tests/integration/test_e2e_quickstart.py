"""End-to-end quickstart verification suite (T106) covering Scenarios 1-6 and SC-001..SC-006."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client

from apps.accounts.forms import ERR_AUTH_CURRENT_PASSWORD_INCORRECT, ERR_AUTH_EMAIL_TAKEN_REGISTER
from apps.accounts.services import AccountLockedError
from apps.contacts.models import Contact, ContactBook, PhoneNumber
from apps.favorites.models import FavoriteItem, FavoriteList
from apps.groups.forms import ERR_GROUP_NAME_DUPLICATE
from apps.groups.models import ContactGroup, Group


def _create_contact_via_http(
    client: Client,
    *,
    full_name: str,
    primary_phone: str,
    primary_phone_type: str = "Mobile",
    secondary_phones: list[tuple[str, str]] | None = None,
    email: str = "",
    address: str = "",
    notes: str = "",
) -> Contact:
    """Submit the contact creation endpoint using standard form payload and return Contact."""
    payload: dict[str, object] = {
        "full_name": full_name,
        "primary_phone": primary_phone,
        "primary_phone_type": primary_phone_type,
        "email": email,
        "address": address,
        "notes": notes,
    }
    if secondary_phones:
        payload["secondary_phones"] = [num for num, _ in secondary_phones]
        payload["secondary_phone_types"] = [ptype for _, ptype in secondary_phones]

    resp = client.post("/contacts/create/", payload)
    assert resp.status_code == 302
    return Contact.objects.filter(full_name=full_name).order_by("-id").first()


@pytest.mark.django_db
class TestE2EQuickstartVerification:
    """End-to-end acceptance suite matching quickstart.md Scenarios 1-6 (SC-001..SC-006)."""

    def test_scenario_1_identity_and_authentication_lifecycle(self, client: Client):
        """Scenario 1 (US1, SC-001): register, duplicate reject, login, profile, password."""
        user_model = get_user_model()

        # 1. Register john_doe -> ContactBook & FavoriteList created atomically
        reg_resp = client.post(
            "/accounts/register/",
            {
                "username": "john_doe",
                "email": "john@example.com",
                "full_name": "John Doe",
                "password": "Password123!",
                "password_confirm": "Password123!",
            },
        )
        assert reg_resp.status_code == 302
        assert reg_resp.url == "/accounts/login/"

        john = user_model.objects.get(username="john_doe")
        assert john.email == "john@example.com"
        assert john.full_name == "John Doe"
        assert ContactBook.objects.filter(user=john).count() == 1
        assert FavoriteList.objects.filter(book__user=john).count() == 1

        # 2. Case-insensitive duplicate email registration rejected
        dup_resp = client.post(
            "/accounts/register/",
            {
                "username": "john_doe_2",
                "email": "JOHN@example.com",
                "full_name": "Duplicate John",
                "password": "Password123!",
                "password_confirm": "Password123!",
            },
        )
        assert dup_resp.status_code == 400
        assert ERR_AUTH_EMAIL_TAKEN_REGISTER.encode() in dup_resp.content
        assert user_model.objects.filter(email__iexact="john@example.com").count() == 1

        # 3. Login -> redirect /contacts/
        login_resp = client.post(
            "/accounts/login/",
            {"username_or_email": "john_doe", "password": "Password123!"},
        )
        assert login_resp.status_code == 302
        assert login_resp.url == "/contacts/"
        assert client.get("/contacts/").status_code == 200

        # 4. Profile update to Johnathan Doe
        profile_resp = client.post(
            "/accounts/profile/",
            {"full_name": "Johnathan Doe", "email": "john@example.com"},
        )
        assert profile_resp.status_code == 302
        assert profile_resp.url == "/accounts/profile/"
        john.refresh_from_db()
        assert john.full_name == "Johnathan Doe"

        profile_view = client.get("/accounts/profile/")
        assert profile_view.status_code == 200
        assert b"Johnathan Doe" in profile_view.content

        # 5. Password change: invalid current password rejected, valid rotation keeps session
        bad_pw_resp = client.post(
            "/accounts/password/change/",
            {
                "current_password": "WrongPassword99!",
                "new_password": "NewPassword2026!",
                "new_password_confirm": "NewPassword2026!",
            },
        )
        assert bad_pw_resp.status_code == 400
        assert ERR_AUTH_CURRENT_PASSWORD_INCORRECT.encode() in bad_pw_resp.content

        good_pw_resp = client.post(
            "/accounts/password/change/",
            {
                "current_password": "Password123!",
                "new_password": "NewPassword2026!",
                "new_password_confirm": "NewPassword2026!",
            },
        )
        assert good_pw_resp.status_code == 302
        assert good_pw_resp.url == "/accounts/profile/"
        assert client.get("/accounts/profile/").status_code == 200

        # 6. POST logout -> redirect /accounts/login/, subsequent /contacts/ redirects to login
        logout_resp = client.post("/accounts/logout/")
        assert logout_resp.status_code == 302
        assert logout_resp.url == "/accounts/login/"

        protected_resp = client.get("/contacts/")
        assert protected_resp.status_code == 302
        assert protected_resp.url.startswith("/accounts/login/")

        # Verify rotated password works for subsequent sign-in
        relogin_resp = client.post(
            "/accounts/login/",
            {"username_or_email": "john@example.com", "password": "NewPassword2026!"},
        )
        assert relogin_resp.status_code == 302
        assert relogin_resp.url == "/contacts/"

    def test_scenario_2_core_contact_lifecycle_management(self, authenticated_client):
        """Scenario 2 (US2, SC-001, SC-003): create, detail badges, edit, delete safeguard."""
        client, owner = authenticated_client(username="s2_john", email="s2john@example.com")

        # 1. Create Alice Smith with primary Mobile and secondary Work phone
        alice = _create_contact_via_http(
            client,
            full_name="Alice Smith",
            primary_phone="0901234567",
            primary_phone_type="Mobile",
            secondary_phones=[("0243888999", "Work")],
            email="alice@example.org",
            notes="Senior Partner at TechCorp",
        )
        assert alice is not None
        assert alice.book_id == owner.contact_book.pk
        assert alice.phone_numbers.filter(is_primary=True).count() == 1
        assert alice.phone_numbers.count() == 2

        # 2. View detail page showing badges/fields
        detail_resp = client.get(f"/contacts/{alice.pk}/")
        assert detail_resp.status_code == 200
        assert b"Alice Smith" in detail_resp.content
        assert b"0901234567" in detail_resp.content
        assert b"0243888999" in detail_resp.content
        assert b"Mobile" in detail_resp.content
        assert b"Primary" in detail_resp.content
        assert b"Work" in detail_resp.content
        assert b"alice@example.org" in detail_resp.content
        assert b"Senior Partner at TechCorp" in detail_resp.content

        # 3. Edit address to 123 Main Street
        edit_resp = client.post(
            f"/contacts/{alice.pk}/edit/",
            {
                "full_name": "Alice Smith",
                "primary_phone": "0901234567",
                "primary_phone_type": "Mobile",
                "secondary_phones": ["0243888999"],
                "secondary_phone_types": ["Work"],
                "email": "alice@example.org",
                "address": "123 Main Street",
                "notes": "Senior Partner at TechCorp",
            },
        )
        assert edit_resp.status_code == 302
        assert edit_resp.url == f"/contacts/{alice.pk}/"
        alice.refresh_from_db()
        assert alice.address == "123 Main Street"

        updated_detail = client.get(f"/contacts/{alice.pk}/")
        assert updated_detail.status_code == 200
        assert b"123 Main Street" in updated_detail.content

        # 4. Delete safeguard (SC-003): requires confirm=true before permanent deletion
        reject_del = client.post(f"/contacts/{alice.pk}/delete/", {})
        assert reject_del.status_code == 400
        assert Contact.objects.filter(pk=alice.pk).exists()

        confirm_del = client.post(f"/contacts/{alice.pk}/delete/", {"confirm": "true"})
        assert confirm_del.status_code == 302
        assert confirm_del.url == "/contacts/"
        assert not Contact.objects.filter(pk=alice.pk).exists()

    def test_scenario_3_search_sorting_duplicate_check_and_smart_merge(self, authenticated_client):
        """Scenario 3 (US3 & US4, SC-002, SC-005): search, sort, duplicate, smart merge."""
        client, owner = authenticated_client(username="s3_john", email="s3john@example.com")

        alice = _create_contact_via_http(
            client,
            full_name="Alice Smith",
            primary_phone="0901234567",
            primary_phone_type="Mobile",
            email="alice@example.org",
            notes="Primary profile note.",
        )
        zoe = _create_contact_via_http(
            client,
            full_name="Zoe Carter",
            primary_phone="0988776655",
            primary_phone_type="Mobile",
            secondary_phones=[("0249994567", "Work")],
            email="zoe@example.org",
        )
        assert zoe is not None
        bob = _create_contact_via_http(
            client,
            full_name="Bob Vance",
            primary_phone="0912223344",
            primary_phone_type="Work",
        )

        # 1. Substring search by name ("Smi") and phone digits ("4567")
        name_search = client.get("/contacts/search/?q=Smi", HTTP_HX_REQUEST="true")
        assert name_search.status_code == 200
        assert b"Alice Smith" in name_search.content
        assert b"Bob Vance" not in name_search.content
        assert b"Zoe Carter" not in name_search.content

        phone_search = client.get("/contacts/search/?q=4567", HTTP_HX_REQUEST="true")
        assert phone_search.status_code == 200
        assert b"Alice Smith" in phone_search.content
        assert b"Zoe Carter" in phone_search.content
        assert b"Bob Vance" not in phone_search.content

        # 2. Alphabetical sort (name_asc, name_desc)
        asc_resp = client.get("/contacts/?sort=name_asc")
        assert asc_resp.status_code == 200
        assert [c.full_name for c in asc_resp.context["contacts"]] == [
            "Alice Smith",
            "Bob Vance",
            "Zoe Carter",
        ]

        desc_resp = client.get("/contacts/?sort=name_desc")
        assert desc_resp.status_code == 200
        assert [c.full_name for c in desc_resp.context["contacts"]] == [
            "Zoe Carter",
            "Bob Vance",
            "Alice Smith",
        ]

        # 3. Duplicate check (POST /contacts/check-duplicate/)
        dup_resp = client.post(
            "/contacts/check-duplicate/",
            {
                "full_name": "Alice Smith",
                "phone_numbers-0-phone_number": "0901234567",
            },
            HTTP_HX_REQUEST="true",
        )
        assert dup_resp.status_code == 200
        assert b"Potential Duplicate Contact Detected" in dup_resp.content
        assert b"Alice Smith" in dup_resp.content
        assert b"0901234567" in dup_resp.content

        # Create duplicate source record with extra phone, note, group, and favorite
        alice_dup = _create_contact_via_http(
            client,
            full_name="Alice Smith",
            primary_phone="0901234567",
            primary_phone_type="Mobile",
            secondary_phones=[("0243888999", "Work")],
            address="123 Main Street",
            notes="Duplicate conference note.",
        )
        vip_group = Group.objects.create(book=owner.contact_book, group_name="VIP")
        ContactGroup.objects.create(contact=alice_dup, group=vip_group)
        FavoriteItem.objects.create(
            favorite_list=owner.contact_book.favorite_list,
            contact=alice_dup,
            priority=2,
        )

        # Duplicate check while editing alice_dup excludes itself and offers Smart Merge
        dup_edit_resp = client.post(
            "/contacts/check-duplicate/",
            {
                "full_name": "Alice Smith",
                "phone_numbers-0-phone_number": "0901234567",
                "exclude_contact_id": str(alice_dup.pk),
            },
            HTTP_HX_REQUEST="true",
        )
        assert dup_edit_resp.status_code == 200
        assert b"Smart Merge" in dup_edit_resp.content

        # 4. Smart merge preview and execution consolidate all fields without data loss
        preview_resp = client.get(
            f"/contacts/merge/?target_contact_id={alice.pk}&source_contact_id={alice_dup.pk}",
            HTTP_HX_REQUEST="true",
        )
        assert preview_resp.status_code == 200
        assert b"0243888999" in preview_resp.content
        assert b"Duplicate conference note." in preview_resp.content

        merge_resp = client.post(
            "/contacts/merge/",
            {
                "target_contact_id": str(alice.pk),
                "source_contact_id": str(alice_dup.pk),
            },
        )
        assert merge_resp.status_code == 302
        assert merge_resp.url == f"/contacts/{alice.pk}/"
        assert not Contact.objects.filter(pk=alice_dup.pk).exists()

        alice.refresh_from_db()
        assert alice.address == "123 Main Street"
        assert "Primary profile note." in (alice.notes or "")
        assert "Duplicate conference note." in (alice.notes or "")
        assert sorted(
            PhoneNumber.objects.filter(contact=alice).values_list("phone_number", flat=True)
        ) == ["0243888999", "0901234567"]
        assert alice.phone_numbers.filter(is_primary=True).count() == 1
        assert ContactGroup.objects.filter(contact=alice, group=vip_group).exists()
        assert FavoriteItem.objects.filter(
            favorite_list=owner.contact_book.favorite_list,
            contact=alice,
        ).exists()
        assert bob.pk is not None

    def test_scenario_4_contact_group_organization(self, authenticated_client):
        """Scenario 4 (US6, SC-003, SC-006): create group, duplicate reject, members, delete."""
        client, owner = authenticated_client(username="s4_john", email="s4john@example.com")

        bob = _create_contact_via_http(
            client,
            full_name="Bob Vance",
            primary_phone="0902223344",
            primary_phone_type="Work",
        )
        carol = _create_contact_via_http(
            client,
            full_name="Carol Danvers",
            primary_phone="0903334455",
            primary_phone_type="Mobile",
        )

        # 1. Create group Work Colleagues; duplicate name rejected
        create_resp = client.post(
            "/groups/create/",
            {"group_name": "Work Colleagues", "description": "Engineering team"},
        )
        assert create_resp.status_code == 302
        assert create_resp.url == "/groups/"
        group = Group.objects.get(book=owner.contact_book, group_name="Work Colleagues")
        assert group.description == "Engineering team"

        dup_group_resp = client.post(
            "/groups/create/",
            {"group_name": "Work Colleagues", "description": "Duplicate"},
        )
        assert dup_group_resp.status_code == 400
        assert ERR_GROUP_NAME_DUPLICATE.encode() in dup_group_resp.content
        assert Group.objects.filter(book=owner.contact_book).count() == 1

        # 2. Add Bob Vance and Carol Danvers via POST /groups/<id>/members/add/
        add_bob = client.post(
            f"/groups/{group.pk}/members/add/",
            {"contact_id": str(bob.pk)},
        )
        assert add_bob.status_code == 302
        add_carol = client.post(
            f"/groups/{group.pk}/members/add/",
            {"contact_id": str(carol.pk)},
        )
        assert add_carol.status_code == 302

        detail_resp = client.get(f"/groups/{group.pk}/")
        assert detail_resp.status_code == 200
        assert b"Bob Vance" in detail_resp.content
        assert b"Carol Danvers" in detail_resp.content

        # 3. Remove Bob Vance and verify Bob remains in /contacts/
        rem_bob = client.post(f"/groups/{group.pk}/members/{bob.pk}/remove/", {})
        assert rem_bob.status_code == 302
        assert not ContactGroup.objects.filter(group=group, contact=bob).exists()
        assert Contact.objects.filter(pk=bob.pk).exists()
        contacts_page = client.get("/contacts/")
        assert contacts_page.status_code == 200
        assert b"Bob Vance" in contacts_page.content

        # 4. Delete group safeguard (SC-003) and Carol preservation (SC-006)
        reject_del = client.post(f"/groups/{group.pk}/delete/", {})
        assert reject_del.status_code == 400
        assert Group.objects.filter(pk=group.pk).exists()

        confirm_del = client.post(f"/groups/{group.pk}/delete/", {"confirm": "true"})
        assert confirm_del.status_code == 302
        assert confirm_del.url == "/groups/"
        assert not Group.objects.filter(pk=group.pk).exists()

        contacts_after = client.get("/contacts/")
        assert contacts_after.status_code == 200
        assert b"Carol Danvers" in contacts_after.content
        assert Contact.objects.filter(pk=carol.pk).exists()

    def test_scenario_5_favorites_prioritization_and_frequency(self, authenticated_client):
        """Scenario 5 (US5, SC-006): add, duplicate reject, priority/frequency sort, safe remove."""
        client, owner = authenticated_client(username="s5_john", email="s5john@example.com")

        carol = _create_contact_via_http(
            client,
            full_name="Carol Danvers",
            primary_phone="0903334455",
            primary_phone_type="Mobile",
        )
        bob = _create_contact_via_http(
            client,
            full_name="Bob Vance",
            primary_phone="0902223344",
            primary_phone_type="Work",
        )

        # 1. Add Carol Danvers to favorites (priority=1); duplicate add rejected (400)
        add_carol = client.post(f"/favorites/add/{carol.pk}/", {"priority": "1"})
        assert add_carol.status_code == 302
        assert add_carol.url == "/favorites/"

        dup_carol = client.post(f"/favorites/add/{carol.pk}/", {"priority": "1"})
        assert dup_carol.status_code == 400
        assert (
            FavoriteItem.objects.filter(
                favorite_list=owner.contact_book.favorite_list,
                contact=carol,
            ).count()
            == 1
        )

        # 2. Add second contact with priority=5; ?sort=priority places priority=1 first
        add_bob = client.post(f"/favorites/add/{bob.pk}/", {"priority": "5"})
        assert add_bob.status_code == 302

        prio_page = client.get("/favorites/?sort=priority")
        assert prio_page.status_code == 200
        assert [item.contact.full_name for item in prio_page.context["favorite_items"]] == [
            "Carol Danvers",
            "Bob Vance",
        ]

        # 3. Log 3 interactions on priority=5 contact; ?sort=frequency places it first
        for expected_count in (1, 2, 3):
            interact_resp = client.post(f"/contacts/{bob.pk}/interact/", {})
            assert interact_resp.status_code == 200
            assert interact_resp.json() == {"status": "ok", "interaction_count": expected_count}

        freq_page = client.get("/favorites/?sort=frequency")
        assert freq_page.status_code == 200
        assert [item.contact.full_name for item in freq_page.context["favorite_items"]] == [
            "Bob Vance",
            "Carol Danvers",
        ]

        # 4. Remove from favorites; underlying Contact remains intact (SC-006)
        remove_resp = client.post(f"/favorites/remove/{carol.pk}/", {})
        assert remove_resp.status_code == 302
        assert not FavoriteItem.objects.filter(
            favorite_list=owner.contact_book.favorite_list,
            contact=carol,
        ).exists()
        assert Contact.objects.filter(pk=carol.pk).exists()
        contacts_page = client.get("/contacts/")
        assert contacts_page.status_code == 200
        assert b"Carol Danvers" in contacts_page.content

    def test_scenario_6_admin_governance_lock_unlock_and_healthz(self, user_factory):
        """Scenario 6 (US7, SC-004): roster, privacy/masking, lock eviction, unlock, /healthz."""
        admin_user = user_factory(
            username="admin_gov",
            email="admin@phonebook.local",
            full_name="System Admin",
            role="Admin",
            is_staff=True,
        )
        john = user_factory(
            username="john_doe",
            email="john@example.com",
            full_name="John Doe",
            password="Password123!",
        )
        private_contact = Contact.objects.create(
            book=john.contact_book,
            full_name="Private Secret Contact",
            email="secret@private.org",
            notes="Strictly confidential note",
        )
        PhoneNumber.objects.create(
            contact=private_contact,
            phone_number="0909998888",
            phone_type="Mobile",
            is_primary=True,
        )

        john_client = Client()
        john_login = john_client.post(
            "/accounts/login/",
            {"username_or_email": "john_doe", "password": "Password123!"},
        )
        assert john_login.status_code == 302
        assert john_login.url == "/contacts/"
        john_session_key = john_client.session.session_key
        assert john_session_key is not None
        assert john_client.get("/contacts/").status_code == 200

        # Standard user cannot access admin panel (FR-041)
        assert john_client.get("/admin-panel/users/").status_code == 403

        admin_client = Client()
        admin_client.force_login(admin_user)

        # 1. Admin inspects /admin-panel/users/?q=john and /admin-panel/users/<id>/ (FR-037, FR-042)
        roster_resp = admin_client.get("/admin-panel/users/?q=john")
        assert roster_resp.status_code == 200
        assert b"john_doe" in roster_resp.content

        detail_resp = admin_client.get(f"/admin-panel/users/{john.pk}/")
        assert detail_resp.status_code == 200
        assert detail_resp.context["target_user"].contact_count == 1
        assert b"john_doe" in detail_resp.content
        assert b"john@example.com" in detail_resp.content
        # Password hash omitted and personal contacts not exposed
        assert john.password.encode() not in detail_resp.content
        assert b"argon2" not in detail_resp.content
        assert b"Private Secret Contact" not in detail_resp.content
        assert b"0909998888" not in detail_resp.content
        assert b"secret@private.org" not in detail_resp.content
        assert admin_client.get(f"/contacts/{private_contact.pk}/").status_code == 404

        # 2. Admin locks john_doe -> session immediately evicted & login rejected (403, SC-004)
        lock_resp = admin_client.post(
            f"/admin-panel/users/{john.pk}/lock/",
            {"reason": "Quickstart verification lock"},
        )
        assert lock_resp.status_code == 302
        john.refresh_from_db()
        assert john.account_status == "Locked"
        assert not Session.objects.filter(session_key=john_session_key).exists()

        evicted_resp = john_client.get("/contacts/")
        assert evicted_resp.status_code == 302
        assert evicted_resp.url.startswith("/accounts/login/")

        # Also verify AccountLockMiddleware message when an active session user becomes Locked
        middleware_client = Client()
        middleware_client.force_login(john)
        mw_resp = middleware_client.get("/contacts/", follow=True)
        assert mw_resp.redirect_chain[-1][0] == "/accounts/login/"
        assert AccountLockedError().message.encode() in mw_resp.content

        locked_login = john_client.post(
            "/accounts/login/",
            {"username_or_email": "john_doe", "password": "Password123!"},
        )
        assert locked_login.status_code == 403
        assert AccountLockedError().message.encode() in locked_login.content

        # 3. Admin unlocks john_doe -> login succeeds again
        unlock_resp = admin_client.post(f"/admin-panel/users/{john.pk}/unlock/", {})
        assert unlock_resp.status_code == 302
        john.refresh_from_db()
        assert john.account_status == "Active"

        unlocked_login = john_client.post(
            "/accounts/login/",
            {"username_or_email": "john_doe", "password": "Password123!"},
        )
        assert unlocked_login.status_code == 302
        assert unlocked_login.url == "/contacts/"
        assert john_client.get("/contacts/").status_code == 200

        # 4. /healthz returns 200
        health_resp = Client().get("/healthz")
        assert health_resp.status_code == 200
        assert health_resp.json() == {"status": "ok", "database": "connected"}
