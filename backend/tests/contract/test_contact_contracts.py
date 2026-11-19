"""Contract tests for core contact lifecycle endpoints (T031)."""

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

VALID_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\x00\x00"
    b"\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _create_contact_with_phones(user, full_name="Alice Smith", phones=None, **kwargs):
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
class TestContactListContract:
    """Contract tests for GET /contacts/ (contact-contracts.md 2.1)."""

    def test_anonymous_user_redirected_to_login(self, client):
        response = client.get("/contacts/")
        assert response.status_code == 302
        assert response.url.startswith("/accounts/login/")

    def test_authenticated_list_renders_20_per_page_and_scopes_to_user(
        self, authenticated_client, user_factory
    ):
        client, owner = authenticated_client(username="list_owner", email="listowner@example.com")
        other_user = user_factory(username="other_list", email="otherlist@example.com")

        for idx in range(1, 26):
            _create_contact_with_phones(
                owner,
                full_name=f"Contact {idx:02d}",
                phones=[(f"0900000{idx:03d}", "Mobile", True)],
            )
        _create_contact_with_phones(
            other_user,
            full_name="Secret Foreign Contact",
            phones=[("0999888777", "Mobile", True)],
        )

        page_1 = client.get("/contacts/")
        assert page_1.status_code == 200
        assert page_1.context["total_contacts_count"] == 25
        assert len(page_1.context["page_obj"].object_list) == 20
        assert b"Contact 01" in page_1.content
        assert b"Secret Foreign Contact" not in page_1.content

        page_2 = client.get("/contacts/?page=2")
        assert page_2.status_code == 200
        assert len(page_2.context["page_obj"].object_list) == 5
        assert b"Contact 25" in page_2.content


@pytest.mark.django_db
class TestContactCreateContract:
    """Contract tests for GET/POST /contacts/create/ (contact-contracts.md 2.4)."""

    def test_create_requires_authentication(self, client):
        response = client.get("/contacts/create/")
        assert response.status_code == 302
        assert response.url.startswith("/accounts/login/")

    def test_post_create_via_formset_persists_contact_and_redirects(
        self, authenticated_client, tmp_path
    ):
        from apps.contacts.models import Contact

        client, user = authenticated_client(username="creator", email="creator@example.com")
        avatar_file = SimpleUploadedFile(
            "avatar.png", BytesIO(VALID_PNG_BYTES).getvalue(), content_type="image/png"
        )

        with override_settings(MEDIA_ROOT=tmp_path):
            payload = {
                "full_name": "  Alice Smith  ",
                "email": "ALICE@Example.ORG",
                "address": "123 Main St",
                "work_address": "456 Tech Park",
                "birthday": "1995-05-15",
                "notes": "VIP client",
                "avatar": avatar_file,
                "phone_numbers-TOTAL_FORMS": "2",
                "phone_numbers-INITIAL_FORMS": "0",
                "phone_numbers-MIN_NUM_FORMS": "0",
                "phone_numbers-MAX_NUM_FORMS": "1000",
                "phone_numbers-0-phone_number": "090 123 4567",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
                "phone_numbers-1-phone_number": "+84 28 3822 1234",
                "phone_numbers-1-phone_type": "Work",
            }
            response = client.post("/contacts/create/", payload)

        contact = Contact.objects.get(book=user.contact_book, full_name="Alice Smith")
        assert response.status_code == 302
        assert response.url == f"/contacts/{contact.pk}/"
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        assert "Contact created successfully." in msgs
        assert contact.email == "alice@example.org"
        assert contact.avatar is not None
        assert contact.phone_numbers.count() == 2
        assert contact.phone_numbers.get(is_primary=True).phone_number == "0901234567"

    def test_post_create_via_contract_fields_and_htmx_succeeds(self, authenticated_client):
        from apps.contacts.models import Contact

        client, user = authenticated_client(username="contract_c", email="contractc@example.com")
        response = client.post(
            "/contacts/create/",
            {
                "full_name": "Bob Contract",
                "primary_phone": "+84901234567",
                "primary_phone_type": "Mobile",
                "secondary_phones": ["02838221234"],
                "secondary_phone_types": ["Work"],
            },
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        contact = Contact.objects.get(book=user.contact_book, full_name="Bob Contract")
        assert response.headers.get("HX-Redirect") == f"/contacts/{contact.pk}/"
        assert contact.phone_numbers.get(is_primary=True).phone_number == "+84901234567"

    def test_post_create_validation_errors_return_400(self, authenticated_client):
        from apps.contacts.models import Contact

        client, user = authenticated_client(username="bad_c", email="badc@example.com")

        missing_name = client.post(
            "/contacts/create/",
            {
                "full_name": "   ",
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "0",
                "phone_numbers-0-phone_number": "0901234567",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
            },
        )
        assert missing_name.status_code == 400
        assert b"Full name is required." in missing_name.content

        missing_phone = client.post(
            "/contacts/create/",
            {
                "full_name": "No Phone User",
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "0",
                "phone_numbers-0-phone_number": "",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
            },
        )
        assert missing_phone.status_code == 400
        assert b"At least one primary phone number is required." in missing_phone.content

        invalid_phone = client.post(
            "/contacts/create/",
            {
                "full_name": "Short Phone User",
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "0",
                "phone_numbers-0-phone_number": "12345",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
            },
        )
        assert invalid_phone.status_code == 400
        assert b"Phone number must contain between 8 and 20 digits." in invalid_phone.content
        assert Contact.objects.filter(book=user.contact_book).count() == 0

    def test_post_create_with_group_ids_syncs_owned_and_rejects_foreign_groups(
        self, authenticated_client, user_factory
    ):
        from apps.contacts.models import Contact
        from apps.groups.models import ContactGroup, Group

        client, owner = authenticated_client(username="grp_c_own", email="grpcown@example.com")
        other = user_factory(username="grp_c_oth", email="grpcoth@example.com")
        g1 = Group.objects.create(book=owner.contact_book, group_name="Family")
        g2 = Group.objects.create(book=owner.contact_book, group_name="VIP")
        foreign_g = Group.objects.create(book=other.contact_book, group_name="Foreign Group")

        # GET renders checkboxes and _groups_submitted marker
        get_resp = client.get("/contacts/create/")
        assert get_resp.status_code == 200
        assert b'name="_groups_submitted"' in get_resp.content
        assert b"Family" in get_resp.content

        # Valid owned group_ids assigned atomically on create
        ok_resp = client.post(
            "/contacts/create/",
            {
                "full_name": "Grouped Contact",
                "group_ids": [str(g1.pk), str(g2.pk)],
                "_groups_submitted": "1",
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "0",
                "phone_numbers-0-phone_number": "0901234567",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
            },
        )
        assert ok_resp.status_code == 302
        contact = Contact.objects.get(book=owner.contact_book, full_name="Grouped Contact")
        assert set(
            ContactGroup.objects.filter(contact=contact).values_list("group_id", flat=True)
        ) == {g1.pk, g2.pk}

        # Tampered foreign group_id rejected with 400
        bad_resp = client.post(
            "/contacts/create/",
            {
                "full_name": "Bad Group Contact",
                "group_ids": [str(foreign_g.pk)],
                "_groups_submitted": "1",
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "0",
                "phone_numbers-0-phone_number": "0908887777",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
            },
        )
        assert bad_resp.status_code == 400
        assert not Contact.objects.filter(
            book=owner.contact_book, full_name="Bad Group Contact"
        ).exists()


@pytest.mark.django_db
class TestContactDetailAndEditContract:
    """Contract tests for GET /contacts/<id>/ and POST /contacts/<id>/edit/."""

    def test_detail_renders_all_attributes_or_404_for_other_tenant(
        self, authenticated_client, user_factory
    ):
        client, owner = authenticated_client(username="detail_u", email="detailu@example.com")
        other = user_factory(username="other_d", email="otherd@example.com")

        own_contact = _create_contact_with_phones(
            owner,
            full_name="Clara Oswald",
            email="clara@example.com",
            address="10 Baker St",
            work_address="Coal Hill School",
            notes="Reliable partner",
            phones=[("0901112222", "Mobile", True), ("02838229999", "Work", False)],
        )
        foreign_contact = _create_contact_with_phones(other, full_name="Foreign Entry")

        resp = client.get(f"/contacts/{own_contact.pk}/")
        assert resp.status_code == 200
        assert b"Clara Oswald" in resp.content
        assert b"0901112222" in resp.content
        assert b"02838229999" in resp.content
        assert b"Primary" in resp.content
        assert b"Work" in resp.content
        assert b"Coal Hill School" in resp.content

        other_resp = client.get(f"/contacts/{foreign_contact.pk}/")
        assert other_resp.status_code == 404

    def test_edit_updates_fields_swaps_primary_phone_and_returns_302(self, authenticated_client):
        client, owner = authenticated_client(username="edit_u", email="editu@example.com")
        contact = _create_contact_with_phones(
            owner,
            full_name="David Tennant",
            email="david@old.org",
            phones=[("0901111111", "Mobile", True), ("0902222222", "Home", False)],
        )
        p1, p2 = list(contact.phone_numbers.order_by("id"))

        resp = client.post(
            f"/contacts/{contact.pk}/edit/",
            {
                "full_name": "David Tennant Updated",
                "email": "david@new.org",
                "notes": "Updated note",
                "phone_numbers-TOTAL_FORMS": "3",
                "phone_numbers-INITIAL_FORMS": "2",
                "phone_numbers-MIN_NUM_FORMS": "0",
                "phone_numbers-MAX_NUM_FORMS": "1000",
                "phone_numbers-0-id": str(p1.pk),
                "phone_numbers-0-contact": str(contact.pk),
                "phone_numbers-0-phone_number": "0901111111",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-1-id": str(p2.pk),
                "phone_numbers-1-contact": str(contact.pk),
                "phone_numbers-1-phone_number": "0902222222",
                "phone_numbers-1-phone_type": "Home",
                "phone_numbers-1-is_primary": "on",
                "phone_numbers-2-phone_number": "02838889999",
                "phone_numbers-2-phone_type": "Work",
            },
        )
        assert resp.status_code == 302
        assert resp.url == f"/contacts/{contact.pk}/"
        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        assert "Contact details updated successfully." in msgs

        contact.refresh_from_db()
        assert contact.full_name == "David Tennant Updated"
        assert contact.email == "david@new.org"
        assert contact.phone_numbers.count() == 3
        assert contact.phone_numbers.get(is_primary=True).pk == p2.pk

    def test_edit_group_ids_sync_and_backward_compatibility(
        self, authenticated_client, user_factory
    ):
        from apps.groups.models import ContactGroup, Group

        client, owner = authenticated_client(username="edit_grp_u", email="editgrpu@example.com")
        other = user_factory(username="edit_grp_o", email="editgrpo@example.com")

        g1 = Group.objects.create(book=owner.contact_book, group_name="Team")
        g2 = Group.objects.create(book=owner.contact_book, group_name="Friends")
        foreign_g = Group.objects.create(book=other.contact_book, group_name="Other Team")

        contact = _create_contact_with_phones(owner, full_name="Group Sync Contact")
        phone = contact.phone_numbers.get()
        ContactGroup.objects.create(group=g1, contact=contact)

        # GET edit pre-populates existing group_ids checkbox
        get_resp = client.get(f"/contacts/{contact.pk}/edit/")
        assert get_resp.status_code == 200
        assert get_resp.context["form"].initial["group_ids"] == [g1.pk]

        # POST without group_ids or _groups_submitted preserves existing memberships
        preserve_resp = client.post(
            f"/contacts/{contact.pk}/edit/",
            {
                "full_name": "Group Sync Preserved",
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "1",
                "phone_numbers-0-id": str(phone.pk),
                "phone_numbers-0-contact": str(contact.pk),
                "phone_numbers-0-phone_number": "0901234567",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
            },
        )
        assert preserve_resp.status_code == 302
        assert list(
            ContactGroup.objects.filter(contact=contact).values_list("group_id", flat=True)
        ) == [g1.pk]

        # POST switching group_ids=[g2.pk] replaces g1 with g2
        switch_resp = client.post(
            f"/contacts/{contact.pk}/edit/",
            {
                "full_name": "Group Sync Switched",
                "group_ids": [str(g2.pk)],
                "_groups_submitted": "1",
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "1",
                "phone_numbers-0-id": str(phone.pk),
                "phone_numbers-0-contact": str(contact.pk),
                "phone_numbers-0-phone_number": "0901234567",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
            },
        )
        assert switch_resp.status_code == 302
        assert list(
            ContactGroup.objects.filter(contact=contact).values_list("group_id", flat=True)
        ) == [g2.pk]

        # POST with _groups_submitted=1 and no group_ids clears all groups
        clear_resp = client.post(
            f"/contacts/{contact.pk}/edit/",
            {
                "full_name": "Group Sync Cleared",
                "_groups_submitted": "1",
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "1",
                "phone_numbers-0-id": str(phone.pk),
                "phone_numbers-0-contact": str(contact.pk),
                "phone_numbers-0-phone_number": "0901234567",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
            },
        )
        assert clear_resp.status_code == 302
        assert not ContactGroup.objects.filter(contact=contact).exists()

        # POST with tampered foreign group_id -> 400
        bad_resp = client.post(
            f"/contacts/{contact.pk}/edit/",
            {
                "full_name": "Group Sync Bad",
                "group_ids": [str(foreign_g.pk)],
                "_groups_submitted": "1",
                "phone_numbers-TOTAL_FORMS": "1",
                "phone_numbers-INITIAL_FORMS": "1",
                "phone_numbers-0-id": str(phone.pk),
                "phone_numbers-0-contact": str(contact.pk),
                "phone_numbers-0-phone_number": "0901234567",
                "phone_numbers-0-phone_type": "Mobile",
                "phone_numbers-0-is_primary": "on",
            },
        )
        assert bad_resp.status_code == 400
        assert not ContactGroup.objects.filter(contact=contact).exists()

    def test_contact_avatar_replace_clear_rollback_and_delete_cleanup(
        self, authenticated_client, tmp_path, django_capture_on_commit_callbacks
    ):
        from apps.contacts.models import Contact

        client, owner = authenticated_client(username="av_c_u", email="avcu@example.com")

        with override_settings(MEDIA_ROOT=tmp_path):
            # 1. Create with avatar
            avatar1 = SimpleUploadedFile("one.png", VALID_PNG_BYTES, content_type="image/png")
            with django_capture_on_commit_callbacks(execute=True):
                resp1 = client.post(
                    "/contacts/create/",
                    {
                        "full_name": "Avatar Contact",
                        "avatar": avatar1,
                        "phone_numbers-TOTAL_FORMS": "1",
                        "phone_numbers-INITIAL_FORMS": "0",
                        "phone_numbers-0-phone_number": "0901112222",
                        "phone_numbers-0-phone_type": "Mobile",
                        "phone_numbers-0-is_primary": "on",
                    },
                )
            assert resp1.status_code == 302
            contact = Contact.objects.get(book=owner.contact_book, full_name="Avatar Contact")
            phone = contact.phone_numbers.get()
            file1 = Path(tmp_path) / contact.avatar.replace("/media/", "")
            assert file1.exists()

            # 2. Failed save cleans up newly uploaded avatar file without deleting old one
            avatar_fail = SimpleUploadedFile("fail.png", VALID_PNG_BYTES, content_type="image/png")
            with patch(
                "apps.contacts.views.Contact.save", side_effect=RuntimeError("DB write error")
            ):
                with pytest.raises(RuntimeError, match="DB write error"):
                    client.post(
                        f"/contacts/{contact.pk}/edit/",
                        {
                            "full_name": "Avatar Contact",
                            "avatar": avatar_fail,
                            "phone_numbers-TOTAL_FORMS": "1",
                            "phone_numbers-INITIAL_FORMS": "1",
                            "phone_numbers-0-id": str(phone.pk),
                            "phone_numbers-0-contact": str(contact.pk),
                            "phone_numbers-0-phone_number": "0901112222",
                            "phone_numbers-0-phone_type": "Mobile",
                            "phone_numbers-0-is_primary": "on",
                        },
                    )
            assert file1.exists()
            assert len(list(file1.parent.iterdir())) == 1

            # 3. Replace avatar deletes old file on commit
            avatar2 = SimpleUploadedFile("two.png", VALID_PNG_BYTES, content_type="image/png")
            with django_capture_on_commit_callbacks(execute=True):
                resp2 = client.post(
                    f"/contacts/{contact.pk}/edit/",
                    {
                        "full_name": "Avatar Contact",
                        "avatar": avatar2,
                        "phone_numbers-TOTAL_FORMS": "1",
                        "phone_numbers-INITIAL_FORMS": "1",
                        "phone_numbers-0-id": str(phone.pk),
                        "phone_numbers-0-contact": str(contact.pk),
                        "phone_numbers-0-phone_number": "0901112222",
                        "phone_numbers-0-phone_type": "Mobile",
                        "phone_numbers-0-is_primary": "on",
                    },
                )
            assert resp2.status_code == 302
            contact.refresh_from_db()
            file2 = Path(tmp_path) / contact.avatar.replace("/media/", "")
            assert file2.exists()
            assert not file1.exists()

            # 4. Clear avatar via avatar-clear removes file on commit and sets avatar=None
            with django_capture_on_commit_callbacks(execute=True):
                resp_clear = client.post(
                    f"/contacts/{contact.pk}/edit/",
                    {
                        "full_name": "Avatar Contact",
                        "avatar-clear": "on",
                        "phone_numbers-TOTAL_FORMS": "1",
                        "phone_numbers-INITIAL_FORMS": "1",
                        "phone_numbers-0-id": str(phone.pk),
                        "phone_numbers-0-contact": str(contact.pk),
                        "phone_numbers-0-phone_number": "0901112222",
                        "phone_numbers-0-phone_type": "Mobile",
                        "phone_numbers-0-is_primary": "on",
                    },
                )
            assert resp_clear.status_code == 302
            contact.refresh_from_db()
            assert contact.avatar is None
            assert not file2.exists()

            # 5. Single delete and batch delete remove avatar files on commit
            c_del = Contact.objects.create(book=owner.contact_book, full_name="Single Del Av")
            c_batch = Contact.objects.create(book=owner.contact_book, full_name="Batch Del Av")
            (Path(tmp_path) / "avatars").mkdir(parents=True, exist_ok=True)
            f_single = Path(tmp_path) / "avatars" / "single_del.png"
            f_batch = Path(tmp_path) / "avatars" / "batch_del.png"
            f_single.write_bytes(VALID_PNG_BYTES)
            f_batch.write_bytes(VALID_PNG_BYTES)
            c_del.avatar = "/media/avatars/single_del.png"
            c_del.save(update_fields=["avatar"])
            c_batch.avatar = "/media/avatars/batch_del.png"
            c_batch.save(update_fields=["avatar"])

            with django_capture_on_commit_callbacks(execute=True):
                assert (
                    client.post(f"/contacts/{c_del.pk}/delete/", {"confirm": "true"}).status_code
                    == 302
                )
            assert not f_single.exists()

            with django_capture_on_commit_callbacks(execute=True):
                assert (
                    client.post(
                        "/contacts/batch-delete/",
                        {"contact_ids": [str(c_batch.pk)], "confirm": "true"},
                    ).status_code
                    == 302
                )
            assert not f_batch.exists()


@pytest.mark.django_db
class TestContactDeleteAndBatchDeleteContract:
    """Contract tests for delete and batch-delete endpoints (contact-contracts.md 2.7 & 2.8)."""

    def test_delete_requires_confirm_true_and_handles_htmx_and_redirect(self, authenticated_client):
        from apps.contacts.models import Contact

        client, owner = authenticated_client(username="del_u", email="delu@example.com")
        c1 = _create_contact_with_phones(owner, full_name="Alice Smith")
        c2 = _create_contact_with_phones(owner, full_name="Bob Jones")

        # GET rejected with 405
        assert client.get(f"/contacts/{c1.pk}/delete/").status_code == 405

        # Missing confirm=true -> 400
        no_confirm = client.post(f"/contacts/{c1.pk}/delete/", {})
        assert no_confirm.status_code == 400
        assert Contact.objects.filter(pk=c1.pk).exists()

        # Confirmed standard POST -> 302 with flash message
        ok_resp = client.post(f"/contacts/{c1.pk}/delete/", {"confirm": "true"})
        assert ok_resp.status_code == 302
        assert ok_resp.url == "/contacts/"
        msgs = [str(m) for m in get_messages(ok_resp.wsgi_request)]
        assert "Contact 'Alice Smith' has been deleted." in msgs
        assert not Contact.objects.filter(pk=c1.pk).exists()

        # Confirmed HTMX POST -> 200 with HX-Trigger header
        htmx_resp = client.post(
            f"/contacts/{c2.pk}/delete/",
            {"confirm": "true"},
            HTTP_HX_REQUEST="true",
        )
        assert htmx_resp.status_code == 200
        assert htmx_resp.headers.get("HX-Trigger") == "contactDeleted"
        assert not Contact.objects.filter(pk=c2.pk).exists()

    def test_batch_delete_requires_selection_and_confirm_true(
        self, authenticated_client, user_factory
    ):
        from apps.contacts.models import Contact

        client, owner = authenticated_client(username="batch_u", email="batchu@example.com")
        other = user_factory(username="batch_other", email="batchother@example.com")

        c1 = _create_contact_with_phones(owner, full_name="Batch One")
        c2 = _create_contact_with_phones(owner, full_name="Batch Two")
        c3 = _create_contact_with_phones(owner, full_name="Batch Keep")
        foreign = _create_contact_with_phones(other, full_name="Foreign Keep")

        # Empty selection -> 400
        assert client.post("/contacts/batch-delete/", {"confirm": "true"}).status_code == 400

        # Missing confirm=true -> 400
        assert (
            client.post(
                "/contacts/batch-delete/",
                {"contact_ids": [str(c1.pk), str(c2.pk)]},
            ).status_code
            == 400
        )
        assert Contact.objects.filter(pk__in=[c1.pk, c2.pk]).count() == 2

        # Confirmed batch delete ignores foreign IDs and deletes only owner's matched records
        resp = client.post(
            "/contacts/batch-delete/",
            {
                "contact_ids": [str(c1.pk), str(c2.pk), str(foreign.pk)],
                "confirm": "true",
            },
        )
        assert resp.status_code == 302
        assert resp.url == "/contacts/"
        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        assert "Successfully deleted 2 contacts." in msgs
        assert not Contact.objects.filter(pk__in=[c1.pk, c2.pk]).exists()
        assert Contact.objects.filter(pk=c3.pk).exists()
        assert Contact.objects.filter(pk=foreign.pk).exists()
