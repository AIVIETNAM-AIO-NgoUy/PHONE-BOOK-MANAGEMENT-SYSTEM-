"""Unit tests for DuplicateDetectionService and SmartMergeService (T064)."""

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.contacts import services as contact_services
from apps.contacts.models import Contact, PhoneNumber

ERR_MERGE_SAME_CONTACT = contact_services.ERR_MERGE_SAME_CONTACT
DuplicateDetectionService = contact_services.DuplicateDetectionService
MergeNotFoundError = contact_services.MergeNotFoundError
MergeValidationError = contact_services.MergeValidationError
SmartMergeService = contact_services.SmartMergeService


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


class TestDuplicateNormalizationHelpersUnit:
    """Pure unit tests for name and phone normalization helpers."""

    def test_normalize_full_name_collapses_whitespace_and_casefolds(self):
        assert DuplicateDetectionService.normalize_full_name(None) == ""
        assert DuplicateDetectionService.normalize_full_name("   \t\n ") == ""
        assert (
            DuplicateDetectionService.normalize_full_name("  Alice   Marie\tSmith  ")
            == "alice marie smith"
        )
        assert (
            DuplicateDetectionService.normalize_full_name("  Nguyễn   Văn  An ") == "nguyễn văn an"
        )

    def test_canonical_phone_keys_handles_vietnamese_e164_and_invalid_inputs(self):
        assert DuplicateDetectionService.canonical_phone_keys(None) == set()
        assert DuplicateDetectionService.canonical_phone_keys("") == set()
        assert DuplicateDetectionService.canonical_phone_keys("12345") == set()

        local_keys = DuplicateDetectionService.canonical_phone_keys("0901 234 567")
        intl_keys = DuplicateDetectionService.canonical_phone_keys("+84-901-234-567")
        assert local_keys == {"0901234567", "84901234567"}
        assert intl_keys == {"84901234567", "0901234567"}
        assert local_keys == intl_keys

        us_keys = DuplicateDetectionService.canonical_phone_keys("+1 (555) 123-4567")
        assert us_keys == {"15551234567"}


@pytest.mark.django_db
class TestDuplicateDetectionServiceUnit:
    """Database-backed unit tests for DuplicateDetectionService."""

    def test_find_duplicates_matches_name_phone_secondary_and_ranks_dual_first(self, user_factory):
        owner = user_factory(username="u_dup1", email="udup1@example.com")
        other = user_factory(username="u_dup2", email="udup2@example.com")

        name_only = _make_contact(
            owner,
            full_name="Alice   Smith",
            phones=[("0909998888", "Mobile", True)],
        )
        phone_only = _make_contact(
            owner,
            full_name="Bob Builder",
            phones=[("0912223333", "Mobile", True), ("+84901234567", "Work", False)],
        )
        dual_match = _make_contact(
            owner,
            full_name="Alice Smith",
            phones=[("0901234567", "Mobile", True)],
        )
        # Cross-tenant identical contact must never be matched
        _make_contact(
            other,
            full_name="Alice Smith",
            phones=[("0901234567", "Mobile", True)],
        )

        candidates = DuplicateDetectionService.find_duplicates(
            book=owner.contact_book,
            full_name="  alice  SMITH ",
            phone_number="0901 234 567",
        )
        assert [c.contact.pk for c in candidates] == [dual_match.pk, phone_only.pk, name_only.pk]
        assert candidates[0].reasons == ("phone", "name")
        assert candidates[0].reason_label == "Matching Phone & Name"
        assert candidates[1].reasons == ("phone",)
        assert candidates[1].reason_label == "Matching Phone Number"
        assert candidates[2].reasons == ("name",)
        assert candidates[2].reason_label == "Matching Full Name"

        # Excluding dual_match removes only dual_match
        filtered = DuplicateDetectionService.find_duplicates(
            book=owner.contact_book,
            full_name="Alice Smith",
            phone_number="0901234567",
            exclude_contact_id=dual_match.pk,
        )
        assert [c.contact.pk for c in filtered] == [phone_only.pk, name_only.pk]

        # Empty input returns []
        assert DuplicateDetectionService.find_duplicates(book=owner.contact_book) == []


@pytest.mark.django_db
class TestSmartMergeServiceUnit:
    """Unit tests for SmartMergeService field consolidation, notes clamping, and safeguards."""

    def test_notes_truncation_safeguard_respects_1000_char_db_constraint(self, user_factory):
        owner = user_factory(username="u_notes", email="unotes@example.com")
        target = _make_contact(
            owner,
            full_name="Long Notes Target",
            notes="A" * 650,
            phones=[("0901111111", "Mobile", True)],
        )
        source = _make_contact(
            owner,
            full_name="Long Notes Source",
            notes="B" * 650,
            phones=[("0902222222", "Mobile", True)],
        )

        preview = SmartMergeService.build_merge_preview(
            target_contact=target,
            source_contact=source,
        )
        assert preview["notes_truncated"] is True
        assert len(preview["consolidated_fields"]["notes"]) == 1000
        assert preview["consolidated_fields"]["notes"].endswith("...")

        # Preview must not mutate database
        assert Contact.objects.filter(pk=source.pk).exists()

        merged = SmartMergeService.merge_contacts(target_contact=target, source_contact=source)
        assert len(merged.notes) <= 1000
        assert merged.notes.endswith("...")
        assert not Contact.objects.filter(pk=source.pk).exists()

    def test_identical_notes_not_duplicated_and_blank_target_fields_filled(self, user_factory):
        owner = user_factory(username="u_idnotes", email="uidnotes@example.com")
        t_earlier = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
        t_later = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)

        target = _make_contact(
            owner,
            full_name="Target One",
            email=None,
            address="",
            work_address="Existing Work",
            avatar=None,
            birthday=None,
            notes="  Shared note line  ",
            interaction_count=0,
            last_contacted_at=None,
            phones=[("0901234567", "Mobile", True)],
        )
        source = _make_contact(
            owner,
            full_name="Source Two",
            email="filled@example.com",
            address="99 Home Blvd",
            work_address="Should Not Overwrite",
            avatar="/media/contact_avatars/a.png",
            birthday=date(1995, 1, 2),
            notes="Shared note line",
            interaction_count=5,
            last_contacted_at=t_later,
            phones=[("+84901234567", "Mobile", True), ("0988777666", "Home", False)],
        )

        merged = SmartMergeService.merge_contacts(target_contact=target, source_contact=source)
        assert merged.email == "filled@example.com"
        assert merged.address == "99 Home Blvd"
        assert merged.work_address == "Existing Work"
        assert merged.avatar == "/media/contact_avatars/a.png"
        assert merged.birthday == date(1995, 1, 2)
        assert merged.notes == "Shared note line"
        assert "--- Merged Note ---" not in merged.notes
        assert merged.interaction_count == 5
        assert merged.last_contacted_at == t_later

        # +84901234567 recognized as duplicate of 0901234567 and discarded; 0988777666 adopted
        numbers = list(merged.phone_numbers.order_by("id"))
        assert [(p.phone_number, p.is_primary) for p in numbers] == [
            ("0901234567", True),
            ("0988777666", False),
        ]

        # Test target keeping newer last_contacted_at when source is older
        older_source = _make_contact(
            owner,
            full_name="Older Source",
            last_contacted_at=t_earlier,
            interaction_count=2,
            phones=[("0977666555", "Work", True)],
        )
        merged_again = SmartMergeService.merge_contacts(
            target_contact=merged,
            source_contact=older_source,
        )
        assert merged_again.interaction_count == 7
        assert merged_again.last_contacted_at == t_later
        assert merged_again.phone_numbers.get(phone_number="0977666555").is_primary is False

    def test_self_merge_and_cross_book_rejection(self, user_factory):
        u1 = user_factory(username="u_err1", email="uerr1@example.com")
        u2 = user_factory(username="u_err2", email="uerr2@example.com")

        c1 = _make_contact(u1, full_name="Owner Contact")
        c2 = _make_contact(u2, full_name="Foreign Contact")

        with pytest.raises(MergeValidationError) as exc_info:
            SmartMergeService.merge_contacts(target_contact=c1, source_contact=c1)
        assert str(exc_info.value) == ERR_MERGE_SAME_CONTACT
        assert exc_info.value.code == "ERR_MERGE_SAME_CONTACT"

        with pytest.raises(MergeValidationError):
            SmartMergeService.build_merge_preview(target_contact=c1, source_contact=c1)

        with pytest.raises(MergeNotFoundError):
            SmartMergeService.merge_contacts(target_contact=c1, source_contact=c2)

        with pytest.raises(MergeNotFoundError):
            SmartMergeService.build_merge_preview(target_contact=c1, source_contact=c2)

    def test_optional_group_and_favorite_transfer_hooks_work_when_models_installed(
        self, user_factory
    ):
        owner = user_factory(username="u_hooks", email="uhooks@example.com")
        target = _make_contact(
            owner, full_name="Hook Target", phones=[("0901111111", "Mobile", True)]
        )
        source = _make_contact(
            owner, full_name="Hook Source", phones=[("0902222222", "Mobile", True)]
        )

        # Mock ContactGroup (1 overlapping group_id=10, 1 new group_id=20)
        cg_overlap = MagicMock(group_id=10)
        cg_new = MagicMock(group_id=20)
        mock_cg_model = MagicMock()
        mock_cg_model.objects.filter.side_effect = [
            MagicMock(values_list=MagicMock(return_value=[10])),
            [cg_overlap, cg_new],
        ]

        # Mock FavoriteItem (source is favorite, target is not)
        fav_source = SimpleNamespace(contact=source, save=MagicMock(), delete=MagicMock())
        mock_fav_model = MagicMock()
        mock_fav_model.objects.filter.side_effect = [
            MagicMock(first=MagicMock(return_value=fav_source)),
            MagicMock(first=MagicMock(return_value=None)),
        ]

        def _fake_get_model(app_label, model_name):
            if (app_label, model_name) == ("groups", "ContactGroup"):
                return mock_cg_model
            if (app_label, model_name) == ("favorites", "FavoriteItem"):
                return mock_fav_model
            raise LookupError("Not installed")

        with patch.object(SmartMergeService, "_get_optional_model", side_effect=_fake_get_model):
            SmartMergeService.merge_contacts(target_contact=target, source_contact=source)

        cg_overlap.delete.assert_called_once()
        assert cg_new.contact.pk == target.pk
        cg_new.save.assert_called_once_with(update_fields=["contact"])
        assert fav_source.contact.pk == target.pk
        fav_source.save.assert_called_once_with(update_fields=["contact"])

    def test_merge_avatar_cleanup_deletes_unkept_source_avatar_and_preserves_kept(
        self, user_factory, tmp_path, django_capture_on_commit_callbacks
    ):
        """M5: Merge deletes source avatar only when target keeps its own different avatar."""
        owner = user_factory(username="u_merge_av", email="umergeav@example.com")
        avatars_dir = Path(tmp_path) / "avatars"
        avatars_dir.mkdir(parents=True, exist_ok=True)
        target_file = avatars_dir / "target.png"
        source_discard_file = avatars_dir / "source_discard.png"
        source_keep_file = avatars_dir / "source_keep.png"
        target_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        source_discard_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        source_keep_file.write_bytes(b"\x89PNG\r\n\x1a\n")

        target_has_av = _make_contact(
            owner,
            full_name="Target Has Avatar",
            avatar="/media/avatars/target.png",
            phones=[("0901111111", "Mobile", True)],
        )
        source_discard = _make_contact(
            owner,
            full_name="Source Discarded Avatar",
            avatar="/media/avatars/source_discard.png",
            phones=[("0902222222", "Mobile", True)],
        )

        with override_settings(MEDIA_ROOT=tmp_path):
            with django_capture_on_commit_callbacks(execute=True):
                merged_keep_target = SmartMergeService.merge_contacts(
                    target_contact=target_has_av,
                    source_contact=source_discard,
                )
            assert merged_keep_target.avatar == "/media/avatars/target.png"
            assert target_file.exists()
            assert not source_discard_file.exists()

            # When target had no avatar, source avatar is adopted and NOT deleted
            target_no_av = _make_contact(
                owner,
                full_name="Target No Avatar",
                avatar=None,
                phones=[("0903333333", "Mobile", True)],
            )
            source_keep = _make_contact(
                owner,
                full_name="Source Kept Avatar",
                avatar="/media/avatars/source_keep.png",
                phones=[("0904444444", "Mobile", True)],
            )
            with django_capture_on_commit_callbacks(execute=True):
                merged_adopted = SmartMergeService.merge_contacts(
                    target_contact=target_no_av,
                    source_contact=source_keep,
                )
            assert merged_adopted.avatar == "/media/avatars/source_keep.png"
            assert source_keep_file.exists()
