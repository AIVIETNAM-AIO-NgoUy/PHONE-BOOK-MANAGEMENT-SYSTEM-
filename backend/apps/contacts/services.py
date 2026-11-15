"""Domain services for contact search, duplicate detection, and smart merging."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.db.models import CharField, Exists, F, Field, Func, Lookup, OuterRef, Q, QuerySet, Value
from django.db.models.functions import Trim

from apps.contacts.models import Contact, ContactBook, PhoneNumber
from apps.core.utils import schedule_media_delete_on_commit

ERR_MERGE_SAME_CONTACT = "Cannot merge a contact into itself."
ERR_MERGE_CONTACT_NOT_FOUND = "One or both contacts could not be found."


@Field.register_lookup
class ILike(Lookup):
    """Case-insensitive PostgreSQL ILIKE lookup generating UPPER-free SQL for pg_trgm GIN."""

    lookup_name = "ilike"
    prepare_rhs = False

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        if self.rhs_is_direct_value() and rhs_params:
            escaped = (
                str(rhs_params[0]).replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
            )
            rhs_params[0] = f"%{escaped}%"
        params = [*lhs_params, *rhs_params]
        if connection.vendor == "postgresql":
            return f"{lhs} ILIKE {rhs} ESCAPE '\\'", params
        return f"UPPER({lhs}) LIKE UPPER({rhs}) ESCAPE '\\'", params


class MergeValidationError(ValueError):
    """Raised when a merge request violates domain validation rules."""

    def __init__(self, message: str, *, code: str = "merge_validation_error") -> None:
        super().__init__(message)
        self.code = code


class MergeNotFoundError(LookupError):
    """Raised when target or source contact does not exist in the authorized book."""


@dataclass(frozen=True)
class DuplicateCandidate:
    """Represents a potential duplicate Contact with match diagnostics."""

    contact: Contact
    reasons: tuple[str, ...]
    matched_phones: tuple[str, ...]

    @property
    def primary_phone(self) -> PhoneNumber | None:
        return self.contact.primary_phone

    @property
    def has_phone_match(self) -> bool:
        return "phone" in self.reasons

    @property
    def has_name_match(self) -> bool:
        return "name" in self.reasons

    @property
    def reason_label(self) -> str:
        if self.has_phone_match and self.has_name_match:
            return "Matching Phone & Name"
        if self.has_phone_match:
            return "Matching Phone Number"
        return "Matching Full Name"


class SearchOptimizationService:
    """Sanitized trigram-backed partial-match search and sorting scoped to a ContactBook."""

    DEFAULT_SORT_KEY = "name_asc"
    SORT_ORDER_MAP: dict[str, tuple[str, ...]] = {
        "name_asc": ("full_name", "id"),
        "name_desc": ("-full_name", "id"),
        "recent": ("-updated_at", "-id"),
    }

    @classmethod
    def sanitize_query(cls, raw_query: str | None) -> str:
        """Trim leading/trailing whitespace and strip NUL bytes safely (EC-007)."""
        if raw_query is None:
            return ""
        return str(raw_query).replace("\x00", "").strip()

    @classmethod
    def resolve_sort_key(cls, sort_key: str | None) -> str:
        """Return a validated sort key, falling back to name_asc on invalid values."""
        if sort_key in cls.SORT_ORDER_MAP:
            return sort_key
        return cls.DEFAULT_SORT_KEY

    @classmethod
    def get_order_by(cls, sort_key: str | None) -> tuple[str, ...]:
        """Return deterministic Django ORM order_by tuple for the resolved sort key."""
        return cls.SORT_ORDER_MAP[cls.resolve_sort_key(sort_key)]

    @classmethod
    def build_search_filter(cls, sanitized_query: str) -> Q:
        """Build UPPER-free ILIKE + Exists Q filter across name, email, and phones."""
        return (
            Q(full_name__ilike=sanitized_query)
            | Q(email__ilike=sanitized_query)
            | Exists(
                PhoneNumber.objects.filter(
                    contact_id=OuterRef("pk"),
                    phone_number__ilike=sanitized_query,
                )
            )
        )

    @classmethod
    def search_contacts(
        cls,
        *,
        book: ContactBook,
        query: str | None = None,
        sort_key: str | None = DEFAULT_SORT_KEY,
    ) -> QuerySet[Contact]:
        """Execute tenant-scoped, deduplicated search and sorting over a ContactBook."""
        queryset = Contact.objects.filter(book=book)
        cleaned_query = cls.sanitize_query(query)
        if cleaned_query:
            queryset = queryset.filter(cls.build_search_filter(cleaned_query))

        return queryset.prefetch_related("phone_numbers").order_by(*cls.get_order_by(sort_key))


class DuplicateDetectionService:
    """Tenant-scoped duplicate detection by normalized full name and canonical phone digits."""

    _NON_DIGITS_RE = re.compile(r"\D+")

    @classmethod
    def normalize_full_name(cls, full_name: str | None) -> str:
        """Collapse internal whitespace, trim edges, and casefold for duplicate matching."""
        if not full_name:
            return ""
        return " ".join(str(full_name).replace("\x00", "").split()).casefold()

    @classmethod
    def canonical_phone_keys(cls, raw_phone: str | None) -> set[str]:
        """Return canonical digit keys accommodating formatting and +84/0 VN equivalents."""
        if not raw_phone:
            return set()
        digits = cls._NON_DIGITS_RE.sub("", str(raw_phone).strip())
        if not (8 <= len(digits) <= 20):
            return set()

        keys = {digits}
        if digits.startswith("84") and len(digits) >= 10:
            keys.add("0" + digits[2:])
        elif digits.startswith("0") and len(digits) >= 9:
            keys.add("84" + digits[1:])
        return keys

    @classmethod
    def find_duplicates(
        cls,
        *,
        book: ContactBook,
        full_name: str | None = None,
        phone_number: str | None = None,
        phone_numbers: Iterable[str] | None = None,
        exclude_contact_id: int | None = None,
    ) -> list[DuplicateCandidate]:
        """Find duplicate Contact candidates strictly within the given ContactBook."""
        normalized_name = cls.normalize_full_name(full_name)

        target_phone_keys: set[str] = set()
        if phone_number:
            target_phone_keys.update(cls.canonical_phone_keys(phone_number))
        if phone_numbers:
            for item in phone_numbers:
                target_phone_keys.update(cls.canonical_phone_keys(item))

        if not normalized_name and not target_phone_keys:
            return []

        queryset = Contact.objects.filter(book=book)
        if exclude_contact_id is not None:
            queryset = queryset.exclude(pk=exclude_contact_id)

        match_q = Q()
        if normalized_name:
            queryset = queryset.annotate(
                _normalized_full_name=Func(
                    Trim("full_name"),
                    Value(r"\s+"),
                    Value(" "),
                    Value("g"),
                    function="REGEXP_REPLACE",
                    output_field=CharField(),
                )
            )
            match_q |= Q(_normalized_full_name__iexact=normalized_name)

        if target_phone_keys:
            queryset = queryset.annotate(
                _normalized_phone_digits=Func(
                    F("phone_numbers__phone_number"),
                    Value(r"[^0-9]"),
                    Value(""),
                    Value("g"),
                    function="REGEXP_REPLACE",
                    output_field=CharField(),
                )
            )
            match_q |= Q(_normalized_phone_digits__in=target_phone_keys)

        contacts = (
            queryset.filter(match_q)
            .distinct()
            .prefetch_related("phone_numbers")
            .order_by("full_name", "id")
        )

        candidates: list[DuplicateCandidate] = []
        for contact in contacts:
            reasons: list[str] = []
            matched_phones: list[str] = []

            if target_phone_keys:
                for phone in contact.phone_numbers.all():
                    if cls.canonical_phone_keys(phone.phone_number) & target_phone_keys:
                        matched_phones.append(phone.phone_number)
                if matched_phones:
                    reasons.append("phone")

            if normalized_name and cls.normalize_full_name(contact.full_name) == normalized_name:
                reasons.append("name")

            if reasons:
                candidates.append(
                    DuplicateCandidate(
                        contact=contact,
                        reasons=tuple(reasons),
                        matched_phones=tuple(matched_phones),
                    )
                )

        # Rank dual matches first, then phone matches, then name matches
        candidates.sort(
            key=lambda item: (
                (
                    0
                    if (item.has_phone_match and item.has_name_match)
                    else (1 if item.has_phone_match else 2)
                ),
                item.contact.full_name.casefold(),
                item.contact.pk,
            )
        )
        return candidates


class SmartMergeService:
    """Atomic duplicate merge service preserving fields, notes, phones, groups, and favorites."""

    NOTES_AUDIT_DELIMITER = "\n\n--- Merged Note ---\n"
    MAX_NOTES_LENGTH = 1000
    SCALAR_MERGE_FIELDS = ("email", "address", "work_address", "avatar", "birthday")

    @classmethod
    def _get_optional_model(cls, app_label: str, model_name: str):
        try:
            return django_apps.get_model(app_label, model_name)
        except LookupError:
            return None

    @classmethod
    def _is_blank(cls, value) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        return False

    @classmethod
    def _merge_notes(
        cls, target_notes: str | None, source_notes: str | None
    ) -> tuple[str | None, bool]:
        target_clean = target_notes.strip() if isinstance(target_notes, str) else ""
        source_clean = source_notes.strip() if isinstance(source_notes, str) else ""

        if not target_clean and not source_clean:
            return None, False

        if not target_clean:
            if len(source_clean) > cls.MAX_NOTES_LENGTH:
                return source_clean[: cls.MAX_NOTES_LENGTH - 3].rstrip() + "...", True
            return source_clean, False

        if not source_clean or target_clean == source_clean:
            if len(target_clean) > cls.MAX_NOTES_LENGTH:
                return target_clean[: cls.MAX_NOTES_LENGTH - 3].rstrip() + "...", True
            return target_clean, False

        combined = f"{target_clean}{cls.NOTES_AUDIT_DELIMITER}{source_clean}"
        if len(combined) <= cls.MAX_NOTES_LENGTH:
            return combined, False

        clamped = combined[: cls.MAX_NOTES_LENGTH - 3].rstrip() + "..."
        return clamped, True

    @classmethod
    def _partition_phone_numbers(
        cls, target_phones: list[PhoneNumber], source_phones: list[PhoneNumber]
    ) -> tuple[list[PhoneNumber], list[PhoneNumber]]:
        """Return (adopted_source_phones, discarded_duplicate_source_phones)."""
        existing_keys: set[str] = set()
        for phone in target_phones:
            keys = DuplicateDetectionService.canonical_phone_keys(phone.phone_number)
            existing_keys.update(keys or {phone.phone_number.strip().casefold()})

        adopted: list[PhoneNumber] = []
        discarded: list[PhoneNumber] = []
        for sp in source_phones:
            sp_keys = DuplicateDetectionService.canonical_phone_keys(sp.phone_number) or {
                sp.phone_number.strip().casefold()
            }
            if sp_keys & existing_keys:
                discarded.append(sp)
            else:
                adopted.append(sp)
                existing_keys.update(sp_keys)

        return adopted, discarded

    @classmethod
    def build_merge_preview(cls, *, target_contact: Contact, source_contact: Contact) -> dict:
        """Build a non-mutating consolidation preview comparing target and source contacts."""
        if target_contact.pk == source_contact.pk:
            raise MergeValidationError(ERR_MERGE_SAME_CONTACT, code="ERR_MERGE_SAME_CONTACT")
        if target_contact.book_id != source_contact.book_id:
            raise MergeNotFoundError(ERR_MERGE_CONTACT_NOT_FOUND)

        consolidated_fields: dict[str, object] = {
            "full_name": target_contact.full_name,
        }
        for field in cls.SCALAR_MERGE_FIELDS:
            target_val = getattr(target_contact, field)
            source_val = getattr(source_contact, field)
            consolidated_fields[field] = (
                source_val
                if (cls._is_blank(target_val) and not cls._is_blank(source_val))
                else target_val
            )

        merged_notes, notes_truncated = cls._merge_notes(target_contact.notes, source_contact.notes)
        consolidated_fields["notes"] = merged_notes
        consolidated_fields["interaction_count"] = (target_contact.interaction_count or 0) + (
            source_contact.interaction_count or 0
        )

        last_contacted = target_contact.last_contacted_at
        if source_contact.last_contacted_at and (
            last_contacted is None or source_contact.last_contacted_at > last_contacted
        ):
            last_contacted = source_contact.last_contacted_at
        consolidated_fields["last_contacted_at"] = last_contacted

        target_phones = list(target_contact.phone_numbers.order_by("-is_primary", "id"))
        source_phones = list(source_contact.phone_numbers.order_by("-is_primary", "id"))
        adopted_phones, discarded_phones = cls._partition_phone_numbers(
            target_phones, source_phones
        )

        consolidated_phones = [
            {
                "phone_number": p.phone_number,
                "phone_type": p.phone_type,
                "is_primary": p.is_primary,
                "origin": "target",
            }
            for p in target_phones
        ] + [
            {
                "phone_number": p.phone_number,
                "phone_type": p.phone_type,
                "is_primary": False,
                "origin": "source",
            }
            for p in adopted_phones
        ]

        groups_to_migrate: list[str] = []
        contact_group_model = cls._get_optional_model("groups", "ContactGroup")
        if contact_group_model is not None:
            target_group_ids = set(
                contact_group_model.objects.filter(contact=target_contact).values_list(
                    "group_id", flat=True
                )
            )
            groups_to_migrate = list(
                contact_group_model.objects.filter(contact=source_contact)
                .exclude(group_id__in=target_group_ids)
                .select_related("group")
                .values_list("group__group_name", flat=True)
            )

        will_transfer_favorite = False
        favorite_item_model = cls._get_optional_model("favorites", "FavoriteItem")
        if favorite_item_model is not None:
            source_is_fav = favorite_item_model.objects.filter(contact=source_contact).exists()
            target_is_fav = favorite_item_model.objects.filter(contact=target_contact).exists()
            will_transfer_favorite = source_is_fav and not target_is_fav

        return {
            "target": target_contact,
            "source": source_contact,
            "target_phones": target_phones,
            "source_phones": source_phones,
            "adopted_phones": adopted_phones,
            "discarded_phones": discarded_phones,
            "consolidated_fields": consolidated_fields,
            "consolidated_phones": consolidated_phones,
            "notes_truncated": notes_truncated,
            "groups_to_migrate": groups_to_migrate,
            "will_transfer_favorite": will_transfer_favorite,
        }

    @classmethod
    @transaction.atomic
    def merge_by_ids(
        cls,
        *,
        book: ContactBook,
        target_contact_id: int,
        source_contact_id: int,
    ) -> Contact:
        """Lock and merge target and source contacts by ID strictly within book."""
        if target_contact_id == source_contact_id:
            raise MergeValidationError(ERR_MERGE_SAME_CONTACT, code="ERR_MERGE_SAME_CONTACT")

        ordered_pks = sorted([target_contact_id, source_contact_id])
        locked = {
            c.pk: c
            for c in Contact.objects.select_for_update()
            .filter(book=book, pk__in=ordered_pks)
            .order_by("pk")
        }
        if target_contact_id not in locked or source_contact_id not in locked:
            raise MergeNotFoundError(ERR_MERGE_CONTACT_NOT_FOUND)

        return cls._execute_locked_merge(
            target=locked[target_contact_id],
            source=locked[source_contact_id],
        )

    @classmethod
    @transaction.atomic
    def merge_contacts(
        cls,
        *,
        target_contact: Contact,
        source_contact: Contact,
        book: ContactBook | None = None,
    ) -> Contact:
        """Atomically merge source_contact into target_contact with row-level locking."""
        if target_contact.pk == source_contact.pk:
            raise MergeValidationError(ERR_MERGE_SAME_CONTACT, code="ERR_MERGE_SAME_CONTACT")
        if target_contact.book_id != source_contact.book_id:
            raise MergeNotFoundError(ERR_MERGE_CONTACT_NOT_FOUND)

        scoped_book = book or target_contact.book
        return cls.merge_by_ids(
            book=scoped_book,
            target_contact_id=target_contact.pk,
            source_contact_id=source_contact.pk,
        )

    @classmethod
    def _execute_locked_merge(cls, *, target: Contact, source: Contact) -> Contact:
        source_avatar = source.avatar

        # 1. Fill blank scalar fields on target from source without overwriting non-empty values
        for field in cls.SCALAR_MERGE_FIELDS:
            target_val = getattr(target, field)
            source_val = getattr(source, field)
            if cls._is_blank(target_val) and not cls._is_blank(source_val):
                setattr(target, field, source_val)

        # 2. Concatenate notes with audit delimiter and enforce <= 1000 char constraint
        merged_notes, _ = cls._merge_notes(target.notes, source.notes)
        target.notes = merged_notes

        # 3. Aggregate communication metrics
        target.interaction_count = (target.interaction_count or 0) + (source.interaction_count or 0)
        if source.last_contacted_at and (
            target.last_contacted_at is None or source.last_contacted_at > target.last_contacted_at
        ):
            target.last_contacted_at = source.last_contacted_at

        # 4. Re-parent phone numbers (discard duplicates, demote source numbers to secondary)
        target_phones = list(target.phone_numbers.select_for_update().order_by("-is_primary", "id"))
        source_phones = list(source.phone_numbers.select_for_update().order_by("-is_primary", "id"))
        adopted_phones, discarded_phones = cls._partition_phone_numbers(
            target_phones, source_phones
        )

        target_has_primary = any(p.is_primary for p in target_phones)
        for sp in discarded_phones:
            sp.delete()

        for idx, sp in enumerate(adopted_phones):
            sp.contact = target
            if not target_has_primary and idx == 0:
                sp.is_primary = True
                target_has_primary = True
            else:
                sp.is_primary = False
            sp.save(update_fields=["contact", "is_primary"])

        # 5. Safely migrate ContactGroup memberships if Phase 8 model is installed
        contact_group_model = cls._get_optional_model("groups", "ContactGroup")
        if contact_group_model is not None:
            target_group_ids = set(
                contact_group_model.objects.filter(contact=target).values_list(
                    "group_id", flat=True
                )
            )
            for cg in contact_group_model.objects.filter(contact=source):
                if cg.group_id in target_group_ids:
                    cg.delete()
                else:
                    try:
                        with transaction.atomic():
                            cg.contact = target
                            cg.save(update_fields=["contact"])
                        target_group_ids.add(cg.group_id)
                    except IntegrityError:
                        cg.delete()
                        target_group_ids.add(cg.group_id)

        # 6. Safely transfer FavoriteItem status if Phase 7 model is installed
        favorite_item_model = cls._get_optional_model("favorites", "FavoriteItem")
        if favorite_item_model is not None:
            source_fav = favorite_item_model.objects.filter(contact=source).first()
            if source_fav is not None:
                target_fav = favorite_item_model.objects.filter(contact=target).first()
                if target_fav is None:
                    try:
                        with transaction.atomic():
                            source_fav.contact = target
                            source_fav.save(update_fields=["contact"])
                    except IntegrityError:
                        source_fav.delete()
                else:
                    source_fav.delete()

        # 7. Persist target, permanently delete source, and clean up replaced avatar file on commit
        target.save()
        source.delete()
        if source_avatar and source_avatar != target.avatar:
            schedule_media_delete_on_commit(source_avatar)
        return Contact.objects.prefetch_related("phone_numbers").get(pk=target.pk)
