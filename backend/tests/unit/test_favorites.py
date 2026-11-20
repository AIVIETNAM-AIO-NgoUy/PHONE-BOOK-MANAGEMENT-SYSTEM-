"""Unit tests for FavoriteItem constraints, forms, services, and sorting (T075)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction

from apps.contacts.models import Contact, PhoneNumber
from apps.contacts.services import SmartMergeService
from apps.favorites import services as favorite_services
from apps.favorites.forms import ERR_FAVORITE_INVALID_PRIORITY, FavoritePriorityForm
from apps.favorites.models import FavoriteItem, FavoriteList

FavoriteDuplicateError = favorite_services.FavoriteDuplicateError
FavoriteNotFoundError = favorite_services.FavoriteNotFoundError
FavoriteService = favorite_services.FavoriteService
FrequencyTrackingService = favorite_services.FrequencyTrackingService


def _make_contact(user, *, full_name, phones=None, **kwargs):
    contact = Contact.objects.create(book=user.contact_book, full_name=full_name, **kwargs)
    for number, ptype, is_primary in phones or [("0901234567", "Mobile", True)]:
        PhoneNumber.objects.create(
            contact=contact,
            phone_number=number,
            phone_type=ptype,
            is_primary=is_primary,
        )
    return contact


class TestFavoritePriorityFormUnit:
    """Unit tests for FavoritePriorityForm validation boundaries (FR-023)."""

    @pytest.mark.parametrize("valid_value", ["1", "5", "10", 1, 10])
    def test_valid_priority_bounds(self, valid_value):
        form = FavoritePriorityForm({"priority": valid_value})
        assert form.is_valid()
        assert form.cleaned_data["priority"] == int(valid_value)

    @pytest.mark.parametrize("invalid_value", ["0", "11", "-5", "abc", "5.5", "", None])
    def test_invalid_priority_rejected_with_domain_message(self, invalid_value):
        data = {} if invalid_value is None else {"priority": invalid_value}
        form = FavoritePriorityForm(data)
        assert not form.is_valid()
        assert ERR_FAVORITE_INVALID_PRIORITY in form.errors["priority"]


@pytest.mark.django_db
class TestFavoriteItemModelConstraintsUnit:
    """Database constraint tests for FavoriteItem (data-model.md 2.8, 3.2)."""

    def test_defaults_and_string_representations(self, user_factory):
        owner = user_factory(username="fav_m_def", email="favmdef@example.com")
        contact = _make_contact(owner, full_name="Default Fav")
        fav_list = owner.contact_book.favorite_list

        item = FavoriteItem.objects.create(favorite_list=fav_list, contact=contact)
        assert item.priority == 5
        assert item.added_at is not None
        assert f"book={owner.contact_book.pk}" in str(fav_list)
        assert f"contact={contact.pk}" in str(item)
        assert "priority=5" in str(item)

    @pytest.mark.parametrize("bad_priority", [0, -1, 11, 100])
    def test_chk_favorite_priority_range_enforced_at_db_level(self, user_factory, bad_priority):
        owner = user_factory(username=f"fav_chk_{bad_priority}", email=f"fchk{bad_priority}@ex.com")
        contact = _make_contact(owner, full_name="Bad Priority")
        fav_list = owner.contact_book.favorite_list

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                FavoriteItem.objects.create(
                    favorite_list=fav_list,
                    contact=contact,
                    priority=bad_priority,
                )

    def test_uq_favoriteitem_list_contact_prevents_duplicates_at_db_level(self, user_factory):
        owner = user_factory(username="fav_uq", email="favuq@example.com")
        contact = _make_contact(owner, full_name="Unique Fav")
        fav_list = owner.contact_book.favorite_list

        FavoriteItem.objects.create(favorite_list=fav_list, contact=contact, priority=2)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                FavoriteItem.objects.create(favorite_list=fav_list, contact=contact, priority=4)


@pytest.mark.django_db
class TestFavoriteAndFrequencyServicesUnit:
    """Unit tests for FavoriteService, FrequencyTrackingService, EC-002/004, and SmartMerge."""

    def test_sorting_tie_breakers_for_priority_frequency_and_name(self, user_factory):
        owner = user_factory(username="fav_svc_sort", email="favsvcsort@example.com")
        fav_list = FavoriteService.get_or_create_favorite_list(owner)
        now = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)

        c_alpha_null = _make_contact(
            owner,
            full_name="Alpha Null",
            interaction_count=4,
            last_contacted_at=None,
        )
        c_beta_recent = _make_contact(
            owner,
            full_name="Beta Recent",
            interaction_count=4,
            last_contacted_at=now,
        )
        c_gamma_older = _make_contact(
            owner,
            full_name="Gamma Older",
            interaction_count=4,
            last_contacted_at=now - timedelta(hours=3),
        )
        c_delta_high_freq = _make_contact(
            owner,
            full_name="Delta HighFreq",
            interaction_count=9,
            last_contacted_at=now - timedelta(days=1),
        )

        FavoriteItem.objects.create(favorite_list=fav_list, contact=c_gamma_older, priority=2)
        FavoriteItem.objects.create(favorite_list=fav_list, contact=c_alpha_null, priority=2)
        FavoriteItem.objects.create(favorite_list=fav_list, contact=c_beta_recent, priority=1)
        FavoriteItem.objects.create(favorite_list=fav_list, contact=c_delta_high_freq, priority=10)

        assert FavoriteService.resolve_sort_key(None) == "priority"
        assert FavoriteService.resolve_sort_key("unknown") == "priority"

        by_prio = [
            i.contact.full_name
            for i in FavoriteService.list_favorites(favorite_list=fav_list, sort_key="priority")
        ]
        assert by_prio == ["Beta Recent", "Alpha Null", "Gamma Older", "Delta HighFreq"]

        by_freq = [
            i.contact.full_name
            for i in FavoriteService.list_favorites(favorite_list=fav_list, sort_key="frequency")
        ]
        assert by_freq == ["Delta HighFreq", "Beta Recent", "Gamma Older", "Alpha Null"]

        by_name = [
            i.contact.full_name
            for i in FavoriteService.list_favorites(favorite_list=fav_list, sort_key="name")
        ]
        assert by_name == ["Alpha Null", "Beta Recent", "Delta HighFreq", "Gamma Older"]

    def test_add_remove_update_and_interaction_scoping(self, user_factory):
        owner = user_factory(username="fav_svc_own", email="favsvcown@example.com")
        other = user_factory(username="fav_svc_oth", email="favsvcoth@example.com")

        own_c = _make_contact(owner, full_name="Own Contact")
        other_c = _make_contact(other, full_name="Other Contact")

        item = FavoriteService.add_favorite(book=owner.contact_book, contact_id=own_c.pk)
        assert item.priority == 5

        with pytest.raises(FavoriteDuplicateError):
            FavoriteService.add_favorite(book=owner.contact_book, contact_id=own_c.pk)

        with pytest.raises(FavoriteNotFoundError):
            FavoriteService.add_favorite(book=owner.contact_book, contact_id=other_c.pk)

        updated_item = FavoriteService.update_priority(
            book=owner.contact_book,
            item_id=item.pk,
            priority=1,
        )
        assert updated_item.priority == 1

        with pytest.raises(FavoriteNotFoundError):
            FavoriteService.update_priority(
                book=other.contact_book,
                item_id=item.pk,
                priority=2,
            )

        updated_contact = FrequencyTrackingService.record_interaction(
            book=owner.contact_book,
            contact_id=own_c.pk,
        )
        assert updated_contact.interaction_count == 1
        assert updated_contact.last_contacted_at is not None

        with pytest.raises(FavoriteNotFoundError):
            FrequencyTrackingService.record_interaction(
                book=owner.contact_book,
                contact_id=other_c.pk,
            )

        # EC-004: removing favorite retains Contact & PhoneNumber
        FavoriteService.remove_favorite(book=owner.contact_book, contact_id=own_c.pk)
        assert not FavoriteItem.objects.filter(pk=item.pk).exists()
        assert Contact.objects.filter(pk=own_c.pk).exists()
        assert PhoneNumber.objects.filter(contact=own_c).count() == 1

        with pytest.raises(FavoriteNotFoundError):
            FavoriteService.remove_favorite(book=owner.contact_book, contact_id=own_c.pk)

    def test_ec002_contact_delete_cascades_favorite_and_smart_merge_transfers_favorite(
        self, user_factory
    ):
        owner = user_factory(username="fav_ec002", email="favec002@example.com")
        fav_list = owner.contact_book.favorite_list

        # EC-002 cascade
        doomed = _make_contact(owner, full_name="Doomed Contact")
        FavoriteItem.objects.create(favorite_list=fav_list, contact=doomed, priority=3)
        doomed.delete()
        assert not FavoriteItem.objects.filter(contact_id=doomed.pk).exists()
        assert FavoriteList.objects.filter(pk=fav_list.pk).exists()

        # SmartMerge transfers FavoriteItem when target isn't favorite
        target = _make_contact(
            owner,
            full_name="Merge Target",
            phones=[("0901112222", "Mobile", True)],
        )
        source = _make_contact(
            owner,
            full_name="Merge Source",
            phones=[("0903334444", "Mobile", True)],
        )
        FavoriteItem.objects.create(favorite_list=fav_list, contact=source, priority=1)

        preview = SmartMergeService.build_merge_preview(
            target_contact=target,
            source_contact=source,
        )
        assert preview["will_transfer_favorite"] is True

        merged = SmartMergeService.merge_contacts(target_contact=target, source_contact=source)
        assert FavoriteItem.objects.filter(
            favorite_list=fav_list, contact=merged, priority=1
        ).exists()

    def test_add_favorite_distinguishes_fk_integrity_error_from_duplicate(self, user_factory):
        """L1: FK IntegrityError (pgcode 23503) raises FavoriteNotFoundError."""
        owner = user_factory(username="fav_fk_u", email="favfku@example.com")
        contact = _make_contact(owner, full_name="FK Contact")

        class _FakePGError(Exception):
            def __init__(self, sqlstate: str):
                super().__init__(sqlstate)
                self.sqlstate = sqlstate
                self.pgcode = sqlstate

        fk_exc = IntegrityError("insert or update violates foreign key constraint")
        fk_exc.__cause__ = _FakePGError("23503")

        with patch("apps.favorites.services.FavoriteItem.objects.create", side_effect=fk_exc):
            with pytest.raises(FavoriteNotFoundError):
                FavoriteService.add_favorite(book=owner.contact_book, contact_id=contact.pk)

        dup_exc = IntegrityError("duplicate key violates uq_favoriteitem_list_contact")
        dup_exc.__cause__ = _FakePGError("23505")

        with patch("apps.favorites.services.FavoriteItem.objects.create", side_effect=dup_exc):
            with pytest.raises(FavoriteDuplicateError):
                FavoriteService.add_favorite(book=owner.contact_book, contact_id=contact.pk)
