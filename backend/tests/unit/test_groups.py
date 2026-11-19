"""Unit tests for Group and ContactGroup models, constraints, forms, and services (T087)."""

from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction

from apps.contacts.models import Contact, PhoneNumber
from apps.groups import forms as group_forms, services as group_services
from apps.groups.models import ContactGroup, Group


def _make_contact(user, *, full_name="Alice Smith", phones=None, email=None):
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
class TestGroupAndContactGroupModelConstraintsUnit:
    """Database constraint and cascade tests for Group and ContactGroup."""

    def test_defaults_str_and_optional_description(self, user_factory):
        owner = user_factory(username="grp_u_def", email="grpudef@example.com")
        contact = _make_contact(owner, full_name="Member One")

        group_null = Group.objects.create(
            book=owner.contact_book,
            group_name="Family",
            description=None,
        )
        group_empty = Group.objects.create(
            book=owner.contact_book,
            group_name="Friends",
            description="",
        )
        link = ContactGroup.objects.create(group=group_null, contact=contact)

        assert group_null.created_at is not None
        assert group_empty.description == ""
        assert link.assigned_at is not None
        assert f"Family (book={owner.contact_book.pk})" == str(group_null)
        assert f"contact={contact.pk}" in str(link)
        assert f"group={group_null.pk}" in str(link)

    @pytest.mark.parametrize("bad_name", ["", " ", "   "])
    def test_chk_group_name_non_empty_enforced_at_db_level(self, user_factory, bad_name):
        owner = user_factory(username="grp_u_chk_name", email="grpuchkname@example.com")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Group.objects.create(book=owner.contact_book, group_name=bad_name)

    def test_chk_group_description_max_length_enforced_at_db_level(self, user_factory):
        owner = user_factory(username="grp_u_chk_desc", email="grpuchkdesc@example.com")
        # Exactly 500 characters succeeds
        ok_group = Group.objects.create(
            book=owner.contact_book,
            group_name="Exact500",
            description="x" * 500,
        )
        assert len(ok_group.description) == 500

        # 501 characters violates chk_group_description_max_length
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Group.objects.create(
                    book=owner.contact_book,
                    group_name="TooLong",
                    description="x" * 501,
                )

    def test_unique_constraints_per_book_and_cross_user_allowance(self, user_factory):
        user_a = user_factory(username="grp_u_uq_a", email="grpuqa@example.com")
        user_b = user_factory(username="grp_u_uq_b", email="grpuqb@example.com")

        Group.objects.create(book=user_a.contact_book, group_name="Coworkers")

        # Identical name allowed in another user's ContactBook
        other_group = Group.objects.create(book=user_b.contact_book, group_name="Coworkers")
        assert other_group.pk is not None

        # Exact duplicate in same book violates uq_groups_book_name
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Group.objects.create(book=user_a.contact_book, group_name="Coworkers")

        # Case-insensitive duplicate in same book violates uq_groups_book_name_ci
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Group.objects.create(book=user_a.contact_book, group_name="cOwOrKeRs")

    def test_uq_contactgroup_contact_group_enforced_at_db_level(self, user_factory):
        owner = user_factory(username="grp_u_cg_uq", email="grpucguq@example.com")
        group = Group.objects.create(book=owner.contact_book, group_name="Team")
        contact = _make_contact(owner, full_name="Team Member")

        ContactGroup.objects.create(group=group, contact=contact)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ContactGroup.objects.create(group=group, contact=contact)


@pytest.mark.django_db
class TestGroupFormsUnit:
    """Unit tests for GroupForm and GroupMemberAddForm validation."""

    def test_group_form_trims_name_normalizes_blank_description_and_checks_uniqueness(
        self, user_factory
    ):
        owner = user_factory(username="grp_f_own", email="grpfown@example.com")
        other = user_factory(username="grp_f_oth", email="grpfoth@example.com")

        existing = Group.objects.create(book=owner.contact_book, group_name="Coworkers")
        Group.objects.create(book=other.contact_book, group_name="Vendors")

        # Valid form trims name, converts blank description -> None, allows cross-user name
        form_ok = group_forms.GroupForm(
            {"group_name": "  Vendors  ", "description": "   "},
            book=owner.contact_book,
        )
        assert form_ok.is_valid()
        assert form_ok.cleaned_data["group_name"] == "Vendors"
        assert form_ok.cleaned_data["description"] is None

        # Blank / whitespace name fails with ERR_GROUP_NAME_REQUIRED
        form_blank = group_forms.GroupForm({"group_name": "   "}, book=owner.contact_book)
        assert not form_blank.is_valid()
        assert group_forms.ERR_GROUP_NAME_REQUIRED in form_blank.errors["group_name"]

        # Case-insensitive duplicate in same book fails with ERR_GROUP_NAME_DUPLICATE
        form_dup = group_forms.GroupForm({"group_name": "COWORKERS"}, book=owner.contact_book)
        assert not form_dup.is_valid()
        assert group_forms.ERR_GROUP_NAME_DUPLICATE in form_dup.errors["group_name"]

        # Edit form with exclude_group_id allows saving own name with different case
        form_edit_self = group_forms.GroupForm(
            {"group_name": "coworkers", "description": "Updated"},
            instance=existing,
            book=owner.contact_book,
            exclude_group_id=existing.pk,
        )
        assert form_edit_self.is_valid()
        assert form_edit_self.cleaned_data["group_name"] == "coworkers"

        # Description > 500 chars rejected
        form_long_desc = group_forms.GroupForm(
            {"group_name": "Valid Name", "description": "a" * 501},
            book=owner.contact_book,
        )
        assert not form_long_desc.is_valid()
        assert "description" in form_long_desc.errors

    def test_group_member_add_form_scopes_contact_to_book(self, user_factory):
        owner = user_factory(username="grp_mf_own", email="grpmfown@example.com")
        other = user_factory(username="grp_mf_oth", email="grpmfoth@example.com")

        own_contact = _make_contact(owner, full_name="Own Contact")
        other_contact = _make_contact(other, full_name="Other Contact")

        valid_form = group_forms.GroupMemberAddForm(
            {"contact_id": str(own_contact.pk)},
            book=owner.contact_book,
        )
        assert valid_form.is_valid()
        assert valid_form.cleaned_data["contact_id"] == own_contact.pk
        assert valid_form.resolved_contact == own_contact

        foreign_form = group_forms.GroupMemberAddForm(
            {"contact_id": str(other_contact.pk)},
            book=owner.contact_book,
        )
        assert not foreign_form.is_valid()
        assert foreign_form.errors.as_data()["contact_id"][0].code == "contact_not_found"

        invalid_form = group_forms.GroupMemberAddForm(
            {"contact_id": "abc"},
            book=owner.contact_book,
        )
        assert not invalid_form.is_valid()
        assert group_forms.ERR_GROUP_CONTACT_REQUIRED in invalid_form.errors["contact_id"]


@pytest.mark.django_db
class TestGroupMembershipServiceUnit:
    """Unit tests for GroupMembershipService, EC-002, and EC-003."""

    def test_crud_member_listing_search_available_and_ec002_ec003(self, user_factory):
        owner = user_factory(username="grp_svc_own", email="grpsvcown@example.com")
        other = user_factory(username="grp_svc_oth", email="grpsvcoth@example.com")

        c1 = _make_contact(
            owner,
            full_name="Alice Alpha",
            phones=[("0901111111", "Mobile", True)],
            email="alice@alpha.org",
        )
        c2 = _make_contact(
            owner,
            full_name="Bob Beta",
            phones=[("0902222222", "Mobile", True)],
            email="bob@beta.org",
        )
        c3 = _make_contact(
            owner,
            full_name="Charlie Gamma",
            phones=[("0903333333", "Mobile", True)],
        )
        foreign_contact = _make_contact(other, full_name="Foreign User")

        g1 = group_services.GroupMembershipService.create_group(
            book=owner.contact_book,
            group_name="  Engineering  ",
            description="  Core devs ",
        )
        assert g1.group_name == "Engineering"
        assert g1.description == "Core devs"

        with pytest.raises(group_services.GroupDuplicateError):
            group_services.GroupMembershipService.create_group(
                book=owner.contact_book,
                group_name="engineering",
            )

        with pytest.raises(group_services.GroupValidationError):
            group_services.GroupMembershipService.create_group(
                book=owner.contact_book,
                group_name="   ",
            )

        group_services.GroupMembershipService.add_member(
            book=owner.contact_book,
            group_id=g1.pk,
            contact_id=c1.pk,
        )
        group_services.GroupMembershipService.add_member(
            book=owner.contact_book,
            group_id=g1.pk,
            contact_id=c2.pk,
        )

        # Duplicate member -> GroupMemberDuplicateError
        with pytest.raises(group_services.GroupMemberDuplicateError):
            group_services.GroupMembershipService.add_member(
                book=owner.contact_book,
                group_id=g1.pk,
                contact_id=c1.pk,
            )

        # Cross-tenant contact -> GroupNotFoundError
        with pytest.raises(group_services.GroupNotFoundError):
            group_services.GroupMembershipService.add_member(
                book=owner.contact_book,
                group_id=g1.pk,
                contact_id=foreign_contact.pk,
            )

        # Annotated list_groups
        listed = list(group_services.GroupMembershipService.list_groups(book=owner.contact_book))
        assert len(listed) == 1
        assert listed[0].member_count == 2

        # In-group search & available_contacts
        searched = list(
            group_services.GroupMembershipService.list_group_members(group=g1, query="  090222 ")
        )
        assert [c.full_name for c in searched] == ["Bob Beta"]

        available = list(group_services.GroupMembershipService.list_available_contacts(group=g1))
        assert [c.pk for c in available] == [c3.pk]

        # EC-002: Deleting a contact cascades ContactGroup while preserving Group
        c2.delete()
        assert not ContactGroup.objects.filter(contact_id=c2.pk).exists()
        assert Group.objects.filter(pk=g1.pk).exists()

        # Removing missing membership raises GroupNotFoundError
        with pytest.raises(group_services.GroupNotFoundError):
            group_services.GroupMembershipService.remove_member(
                book=owner.contact_book,
                group_id=g1.pk,
                contact_id=c3.pk,
            )

        # EC-003: Deleting group removes ContactGroup while preserving Contact & PhoneNumber
        deleted_name = group_services.GroupMembershipService.delete_group(
            book=owner.contact_book,
            group_id=g1.pk,
        )
        assert deleted_name == "Engineering"
        assert not Group.objects.filter(pk=g1.pk).exists()
        assert not ContactGroup.objects.filter(group_id=g1.pk).exists()
        assert Contact.objects.filter(pk=c1.pk).exists()
        assert PhoneNumber.objects.filter(contact=c1).count() == 1

    def test_add_member_distinguishes_fk_integrity_error_from_duplicate(self, user_factory):
        """L1: FK IntegrityError (pgcode 23503) raises GroupNotFoundError instead of Duplicate."""
        owner = user_factory(username="grp_fk_u", email="grpfku@example.com")
        group = Group.objects.create(book=owner.contact_book, group_name="FK Group")
        contact = _make_contact(owner, full_name="FK Member")

        class _FakePGError(Exception):
            def __init__(self, sqlstate: str):
                super().__init__(sqlstate)
                self.sqlstate = sqlstate
                self.pgcode = sqlstate

        fk_exc = IntegrityError("insert or update violates foreign key constraint")
        fk_exc.__cause__ = _FakePGError("23503")

        with patch("apps.groups.services.ContactGroup.objects.create", side_effect=fk_exc):
            with pytest.raises(group_services.GroupNotFoundError):
                group_services.GroupMembershipService.add_member(
                    book=owner.contact_book,
                    group_id=group.pk,
                    contact_id=contact.pk,
                )

        dup_exc = IntegrityError("duplicate key violates uq_contactgroup_contact_group")
        dup_exc.__cause__ = _FakePGError("23505")

        with patch("apps.groups.services.ContactGroup.objects.create", side_effect=dup_exc):
            with pytest.raises(group_services.GroupMemberDuplicateError):
                group_services.GroupMembershipService.add_member(
                    book=owner.contact_book,
                    group_id=group.pk,
                    contact_id=contact.pk,
                )
