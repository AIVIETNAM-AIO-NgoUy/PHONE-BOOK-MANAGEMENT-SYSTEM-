"""Domain services for contact group management and memberships (T081)."""

from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, QuerySet

from apps.contacts.models import Contact, ContactBook
from apps.contacts.services import SearchOptimizationService
from apps.core.utils import sanitize_contact_text
from apps.groups.models import ContactGroup, Group

ERR_GROUP_NAME_REQUIRED = "Group name cannot be empty."
ERR_GROUP_NAME_TOO_LONG = f"Group name cannot exceed {Group.MAX_NAME_LENGTH} characters."
ERR_GROUP_NAME_DUPLICATE = "You already have a group with this name. Please choose a distinct name."
ERR_GROUP_DESCRIPTION_TOO_LONG = (
    f"Description cannot exceed {Group.MAX_DESCRIPTION_LENGTH} characters."
)
ERR_GROUP_NOT_FOUND = "Group not found."
ERR_CONTACT_NOT_FOUND = "Contact not found."
ERR_CONTACT_ALREADY_IN_GROUP = "Contact is already a member of this group."
ERR_MEMBERSHIP_NOT_FOUND = "Membership link not found."


class GroupValidationError(ValueError):
    """Raised when group input violates domain validation rules."""

    def __init__(self, message: str, *, code: str = "group_validation_error") -> None:
        super().__init__(message)
        self.code = code


class GroupDuplicateError(GroupValidationError):
    """Raised when a group name collides case-insensitively within a ContactBook."""

    def __init__(self, message: str = ERR_GROUP_NAME_DUPLICATE) -> None:
        super().__init__(message, code="ERR_GROUP_NAME_DUPLICATE")


class GroupMemberDuplicateError(GroupValidationError):
    """Raised when assigning a contact who is already a member of the group."""

    def __init__(self, message: str = ERR_CONTACT_ALREADY_IN_GROUP) -> None:
        super().__init__(message, code="ERR_CONTACT_ALREADY_IN_GROUP")


class GroupNotFoundError(LookupError):
    """Raised when a Group, Contact, or ContactGroup link does not exist in scope."""


class GroupMembershipService:
    """Tenant-scoped group lifecycle and many-to-many membership operations."""

    @classmethod
    def list_groups(cls, *, book: ContactBook) -> QuerySet[Group]:
        """Return all groups in a ContactBook annotated with member_count."""
        return (
            Group.objects.filter(book=book)
            .annotate(member_count=Count("contact_groups"))
            .order_by("group_name", "id")
        )

    @classmethod
    def get_group(cls, *, book: ContactBook, group_id: int) -> Group:
        """Resolve an owned Group or raise GroupNotFoundError."""
        group = Group.objects.filter(pk=group_id, book=book).first()
        if group is None:
            raise GroupNotFoundError(ERR_GROUP_NOT_FOUND)
        return group

    @classmethod
    def list_group_members(
        cls,
        *,
        group: Group,
        query: str | None = None,
    ) -> QuerySet[Contact]:
        """Return contacts belonging to a group with optional in-group search."""
        queryset = Contact.objects.filter(
            book=group.book,
        ).filter(
            Exists(ContactGroup.objects.filter(contact_id=OuterRef("pk"), group=group)),
        )
        cleaned_query = SearchOptimizationService.sanitize_query(query)
        if cleaned_query:
            queryset = queryset.filter(SearchOptimizationService.build_search_filter(cleaned_query))
        return queryset.prefetch_related("phone_numbers").order_by("full_name", "id")

    @classmethod
    def list_available_contacts(cls, *, group: Group) -> QuerySet[Contact]:
        """Return contacts in the book not yet assigned to this group."""
        return (
            Contact.objects.filter(book=group.book)
            .exclude(contact_groups__group=group)
            .prefetch_related("phone_numbers")
            .order_by("full_name", "id")
        )

    @classmethod
    def _clean_group_fields(
        cls,
        *,
        group_name: str | None,
        description: str | None,
    ) -> tuple[str, str | None]:
        cleaned_name = sanitize_contact_text(group_name, collapse_newlines=True)
        if not cleaned_name:
            raise GroupValidationError(ERR_GROUP_NAME_REQUIRED, code="ERR_GROUP_NAME_REQUIRED")
        if len(cleaned_name) > Group.MAX_NAME_LENGTH:
            raise GroupValidationError(ERR_GROUP_NAME_TOO_LONG, code="group_name_too_long")

        cleaned_desc = sanitize_contact_text(description, collapse_newlines=False)
        if cleaned_desc and len(cleaned_desc) > Group.MAX_DESCRIPTION_LENGTH:
            raise GroupValidationError(
                ERR_GROUP_DESCRIPTION_TOO_LONG,
                code="description_too_long",
            )
        return cleaned_name, cleaned_desc

    @classmethod
    @transaction.atomic
    def create_group(
        cls,
        *,
        book: ContactBook,
        group_name: str,
        description: str | None = None,
    ) -> Group:
        """Create a uniquely named group within the user's ContactBook."""
        cleaned_name, cleaned_desc = cls._clean_group_fields(
            group_name=group_name,
            description=description,
        )
        if Group.objects.filter(book=book, group_name__iexact=cleaned_name).exists():
            raise GroupDuplicateError(ERR_GROUP_NAME_DUPLICATE)

        try:
            with transaction.atomic():
                return Group.objects.create(
                    book=book,
                    group_name=cleaned_name,
                    description=cleaned_desc,
                )
        except IntegrityError as exc:
            raise GroupDuplicateError(ERR_GROUP_NAME_DUPLICATE) from exc

    @classmethod
    @transaction.atomic
    def update_group(
        cls,
        *,
        book: ContactBook,
        group_id: int,
        group_name: str,
        description: str | None = None,
    ) -> Group:
        """Update an owned group's name and description while preserving uniqueness."""
        group = Group.objects.select_for_update().filter(pk=group_id, book=book).first()
        if group is None:
            raise GroupNotFoundError(ERR_GROUP_NOT_FOUND)

        cleaned_name, cleaned_desc = cls._clean_group_fields(
            group_name=group_name,
            description=description,
        )
        if (
            Group.objects.filter(book=book, group_name__iexact=cleaned_name)
            .exclude(pk=group.pk)
            .exists()
        ):
            raise GroupDuplicateError(ERR_GROUP_NAME_DUPLICATE)

        group.group_name = cleaned_name
        group.description = cleaned_desc
        try:
            with transaction.atomic():
                group.save(update_fields=["group_name", "description"])
        except IntegrityError as exc:
            raise GroupDuplicateError(ERR_GROUP_NAME_DUPLICATE) from exc
        return group

    @classmethod
    @transaction.atomic
    def delete_group(cls, *, book: ContactBook, group_id: int) -> str:
        """Delete a group and its ContactGroup links while retaining all Contacts."""
        group = Group.objects.select_for_update().filter(pk=group_id, book=book).first()
        if group is None:
            raise GroupNotFoundError(ERR_GROUP_NOT_FOUND)

        group_name = group.group_name
        group.delete()
        return group_name

    @classmethod
    @transaction.atomic
    def add_member(
        cls,
        *,
        book: ContactBook,
        group_id: int,
        contact_id: int,
    ) -> ContactGroup:
        """Assign an owned contact to an owned group without duplicate memberships."""
        group = Group.objects.select_for_update().filter(pk=group_id, book=book).first()
        if group is None:
            raise GroupNotFoundError(ERR_GROUP_NOT_FOUND)

        contact = Contact.objects.select_for_update().filter(pk=contact_id, book=book).first()
        if contact is None:
            raise GroupNotFoundError(ERR_CONTACT_NOT_FOUND)

        if ContactGroup.objects.filter(group=group, contact=contact).exists():
            raise GroupMemberDuplicateError(ERR_CONTACT_ALREADY_IN_GROUP)

        try:
            with transaction.atomic():
                return ContactGroup.objects.create(group=group, contact=contact)
        except IntegrityError as exc:
            sqlstate = getattr(getattr(exc, "__cause__", None), "sqlstate", None)
            if sqlstate == "23503":
                if not Group.objects.filter(pk=group_id, book=book).exists():
                    raise GroupNotFoundError(ERR_GROUP_NOT_FOUND) from exc
                raise GroupNotFoundError(ERR_CONTACT_NOT_FOUND) from exc
            if not Group.objects.filter(pk=group_id, book=book).exists():
                raise GroupNotFoundError(ERR_GROUP_NOT_FOUND) from exc
            if not Contact.objects.filter(pk=contact_id, book=book).exists():
                raise GroupNotFoundError(ERR_CONTACT_NOT_FOUND) from exc
            raise GroupMemberDuplicateError(ERR_CONTACT_ALREADY_IN_GROUP) from exc

    @classmethod
    @transaction.atomic
    def remove_member(cls, *, book: ContactBook, group_id: int, contact_id: int) -> None:
        """Sever a ContactGroup link without deleting the Contact or Group."""
        group = Group.objects.filter(pk=group_id, book=book).first()
        if group is None:
            raise GroupNotFoundError(ERR_GROUP_NOT_FOUND)

        deleted_count, _ = ContactGroup.objects.filter(
            group=group,
            contact_id=contact_id,
        ).delete()
        if deleted_count == 0:
            raise GroupNotFoundError(ERR_MEMBERSHIP_NOT_FOUND)
