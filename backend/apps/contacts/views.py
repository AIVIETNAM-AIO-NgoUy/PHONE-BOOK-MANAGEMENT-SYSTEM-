"""Views for core contact lifecycle management (list, detail, create, edit, delete)."""

import os
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST

from apps.contacts import forms as contact_forms, services as contact_services
from apps.contacts.models import Contact, ContactBook
from apps.core.utils import delete_media_file, resolve_media_path, schedule_media_delete_on_commit
from apps.favorites.services import FavoriteNotFoundError, FavoriteService, FrequencyTrackingService
from apps.groups.models import ContactGroup, Group

CONTACTS_PER_PAGE = 20
_FORMSET_PHONE_KEY_RE = re.compile(r"^phone_numbers-(\d+)-phone_number$")


def _get_user_contact_book(user) -> ContactBook:
    """Resolve the authenticated user's isolated ContactBook container."""
    contact_book, _ = ContactBook.objects.get_or_create(user=user)
    return contact_book


def _save_contact_avatar(avatar_file) -> str:
    """Persist an uploaded contact avatar under MEDIA_ROOT/contact_avatars/."""
    avatars_dir = Path(settings.MEDIA_ROOT) / "contact_avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)
    storage = FileSystemStorage(
        location=str(avatars_dir),
        base_url=f"{settings.MEDIA_URL}contact_avatars/",
    )
    ext = os.path.splitext(avatar_file.name or "")[1].lower()
    filename = f"contact_{uuid.uuid4().hex[:12]}{ext}"
    saved_name = storage.save(filename, avatar_file)
    return storage.url(saved_name)


@transaction.atomic
def _persist_contact_with_phones(
    *,
    contact_form: contact_forms.ContactForm,
    phone_formset,
    contact_book: ContactBook,
) -> Contact:
    """Atomically save a Contact, PhoneNumber records, avatar, and group memberships."""
    ContactBook.objects.select_for_update().get(pk=contact_book.pk)
    contact = contact_form.save(commit=False)
    contact.book = contact_book
    old_avatar = contact.avatar if contact.pk else None

    avatar_file = contact_form.cleaned_data.get("avatar")
    new_avatar_path = None
    if avatar_file is False:
        contact.avatar = None
    elif avatar_file is not None:
        contact.avatar = _save_contact_avatar(avatar_file)
        new_avatar_path = resolve_media_path(contact.avatar)

    try:
        contact.save()

        phone_formset.instance = contact
        instances = phone_formset.save(commit=False)

        for deleted_obj in phone_formset.deleted_objects:
            deleted_obj.delete()

        # Save non-primary numbers before primary ones so PostgreSQL's partial unique index
        # idx_unique_primary_phone_per_contact never collides when swapping primary numbers.
        for phone_obj in sorted(instances, key=lambda item: bool(item.is_primary)):
            phone_obj.contact = contact
            if phone_obj.is_primary:
                if phone_obj.pk is None:
                    contact.phone_numbers.filter(is_primary=True).update(is_primary=False)
                else:
                    contact.phone_numbers.exclude(pk=phone_obj.pk).filter(is_primary=True).update(
                        is_primary=False
                    )
            phone_obj.save()

        if "group_ids" in contact_form.data or contact_form.data.get("_groups_submitted") == "1":
            selected_group_ids = {g.pk for g in (contact_form.cleaned_data.get("group_ids") or [])}
            existing_group_ids = set(
                ContactGroup.objects.filter(contact=contact).values_list("group_id", flat=True)
            )
            to_remove = existing_group_ids - selected_group_ids
            if to_remove:
                ContactGroup.objects.filter(contact=contact, group_id__in=to_remove).delete()
            to_add = selected_group_ids - existing_group_ids
            if to_add:
                ContactGroup.objects.bulk_create(
                    [ContactGroup(contact=contact, group_id=gid) for gid in sorted(to_add)],
                    ignore_conflicts=True,
                )
    except Exception:
        delete_media_file(new_avatar_path)
        raise

    if old_avatar and old_avatar != contact.avatar:
        schedule_media_delete_on_commit(old_avatar)

    return contact


def _apply_group_filter(
    *,
    book: ContactBook,
    queryset,
    raw_group: str | None,
) -> tuple[object, Group | None, bool]:
    """Filter contact queryset by owned group ID if requested via ?group=<id>."""
    cleaned_group = (raw_group or "").strip()
    if not cleaned_group:
        return queryset, None, False
    if not cleaned_group.isdigit():
        return queryset.none(), None, True

    selected_group = Group.objects.filter(pk=int(cleaned_group), book=book).first()
    if selected_group is None:
        return queryset.none(), None, True
    return queryset.filter(contact_groups__group=selected_group).distinct(), selected_group, True


@method_decorator(login_required, name="dispatch")
class ContactListView(View):
    """Display paginated directory of contacts belonging to the authenticated user."""

    template_name = "contacts/contact_list.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        sort_key = contact_services.SearchOptimizationService.resolve_sort_key(
            request.GET.get("sort")
        )
        search_query = contact_services.SearchOptimizationService.sanitize_query(
            request.GET.get("q")
        )

        queryset = contact_services.SearchOptimizationService.search_contacts(
            book=book,
            query=search_query,
            sort_key=sort_key,
        )
        queryset, selected_group, has_group_filter = _apply_group_filter(
            book=book,
            queryset=queryset,
            raw_group=request.GET.get("group"),
        )
        paginator = Paginator(queryset, CONTACTS_PER_PAGE)
        page_obj = paginator.get_page(request.GET.get("page"))
        page_contacts = list(page_obj.object_list)
        favorite_list = FavoriteService.get_or_create_favorite_list(request.user)
        favorite_contact_ids = FavoriteService.get_favorite_contact_ids(
            favorite_list=favorite_list,
            contact_ids=[c.pk for c in page_contacts],
        )
        for contact_item in page_contacts:
            contact_item.is_favorite = contact_item.pk in favorite_contact_ids

        groups = list(Group.objects.filter(book=book).order_by("group_name", "id"))
        total_contacts_count = (
            Contact.objects.filter(book=book).count()
            if (search_query or has_group_filter)
            else paginator.count
        )

        return render(
            request,
            self.template_name,
            {
                "page_obj": page_obj,
                "contacts": page_contacts,
                "favorite_contact_ids": favorite_contact_ids,
                "current_sort": sort_key,
                "search_query": search_query,
                "total_contacts_count": total_contacts_count,
                "matched_contacts_count": paginator.count,
                "groups": groups,
                "selected_group": selected_group,
                "has_group_filter": has_group_filter,
            },
        )


@method_decorator(login_required, name="dispatch")
class ContactSearchView(View):
    """Handle HTMX live partial-match search and full-page search fallback."""

    full_template_name = "contacts/contact_list.html"
    rows_partial_template = "contacts/partials/contact_table_rows.html"
    empty_partial_template = "contacts/partials/empty_search_state.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        search_query = contact_services.SearchOptimizationService.sanitize_query(
            request.GET.get("q")
        )
        sort_key = contact_services.SearchOptimizationService.resolve_sort_key(
            request.GET.get("sort")
        )

        queryset = contact_services.SearchOptimizationService.search_contacts(
            book=book,
            query=search_query,
            sort_key=sort_key,
        )
        queryset, selected_group, has_group_filter = _apply_group_filter(
            book=book,
            queryset=queryset,
            raw_group=request.GET.get("group"),
        )
        paginator = Paginator(queryset, CONTACTS_PER_PAGE)
        page_obj = paginator.get_page(request.GET.get("page"))
        page_contacts = list(page_obj.object_list)
        favorite_list = FavoriteService.get_or_create_favorite_list(request.user)
        favorite_contact_ids = FavoriteService.get_favorite_contact_ids(
            favorite_list=favorite_list,
            contact_ids=[c.pk for c in page_contacts],
        )
        for contact_item in page_contacts:
            contact_item.is_favorite = contact_item.pk in favorite_contact_ids

        groups = list(Group.objects.filter(book=book).order_by("group_name", "id"))
        total_contacts_count = (
            Contact.objects.filter(book=book).count()
            if (search_query or has_group_filter)
            else paginator.count
        )

        context = {
            "page_obj": page_obj,
            "contacts": page_contacts,
            "favorite_contact_ids": favorite_contact_ids,
            "current_sort": sort_key,
            "search_query": search_query,
            "total_contacts_count": total_contacts_count,
            "matched_contacts_count": paginator.count,
            "groups": groups,
            "selected_group": selected_group,
            "has_group_filter": has_group_filter,
        }

        if request.headers.get("HX-Request") == "true":
            if search_query and paginator.count == 0:
                return render(request, self.empty_partial_template, context)
            return render(request, self.rows_partial_template, context)

        return render(request, self.full_template_name, context)


@method_decorator(login_required, name="dispatch")
class ContactDetailView(View):
    """Display full contact profile details scoped to the authenticated user's ContactBook."""

    template_name = "contacts/contact_detail.html"

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        contact = get_object_or_404(
            Contact.objects.prefetch_related("phone_numbers"),
            pk=pk,
            book=book,
        )
        phone_numbers = list(contact.phone_numbers.all())
        contact_groups = list(
            Group.objects.filter(contact_groups__contact=contact).order_by("group_name", "id")
        )
        duplicate_candidates = contact_services.DuplicateDetectionService.find_duplicates(
            book=book,
            full_name=contact.full_name,
            phone_numbers=[p.phone_number for p in phone_numbers],
            exclude_contact_id=contact.pk,
        )
        other_contacts = (
            Contact.objects.filter(book=book)
            .exclude(pk=contact.pk)
            .prefetch_related("phone_numbers")
            .order_by("full_name", "id")[:50]
        )
        favorite_list = FavoriteService.get_or_create_favorite_list(request.user)
        is_favorite = contact.pk in FavoriteService.get_favorite_contact_ids(
            favorite_list=favorite_list,
            contact_ids=[contact.pk],
        )
        return render(
            request,
            self.template_name,
            {
                "contact": contact,
                "phone_numbers": phone_numbers,
                "groups": contact_groups,
                "is_favorite": is_favorite,
                "interaction_count": contact.interaction_count,
                "last_contacted_at": contact.last_contacted_at,
                "duplicate_candidates": duplicate_candidates,
                "other_contacts": other_contacts,
            },
        )


@method_decorator(login_required, name="dispatch")
class ContactCreateView(View):
    """Create a new contact with one or more labeled phone numbers."""

    template_name = "contacts/contact_form.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        return render(
            request,
            self.template_name,
            {
                "form": contact_forms.ContactForm(book=book),
                "phone_formset": contact_forms.PhoneNumberInlineFormSet(prefix="phone_numbers"),
                "is_edit": False,
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        post_data = contact_forms.normalize_contact_post_data(request.POST, prefix="phone_numbers")
        with transaction.atomic():
            ContactBook.objects.select_for_update().get(pk=book.pk)
            form = contact_forms.ContactForm(post_data, request.FILES, book=book)
            phone_formset = contact_forms.PhoneNumberInlineFormSet(
                post_data, prefix="phone_numbers", book=book
            )

            if not (form.is_valid() and phone_formset.is_valid()):
                return render(
                    request,
                    self.template_name,
                    {
                        "form": form,
                        "phone_formset": phone_formset,
                        "is_edit": False,
                    },
                    status=400,
                )

            contact = _persist_contact_with_phones(
                contact_form=form,
                phone_formset=phone_formset,
                contact_book=book,
            )
        messages.success(request, "Contact created successfully.")
        detail_url = reverse("contacts:detail", kwargs={"pk": contact.pk})

        if request.headers.get("HX-Request") == "true":
            response = HttpResponse(status=200)
            response["HX-Redirect"] = detail_url
            return response

        return redirect(detail_url)


@method_decorator(login_required, name="dispatch")
class ContactEditView(View):
    """Update an existing contact and synchronize its phone numbers."""

    template_name = "contacts/contact_form.html"

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        contact = get_object_or_404(Contact, pk=pk, book=book)
        return render(
            request,
            self.template_name,
            {
                "form": contact_forms.ContactForm(instance=contact, book=book),
                "phone_formset": contact_forms.PhoneNumberEditInlineFormSet(
                    instance=contact,
                    prefix="phone_numbers",
                ),
                "contact": contact,
                "is_edit": True,
            },
        )

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        with transaction.atomic():
            ContactBook.objects.select_for_update().get(pk=book.pk)
            try:
                contact = Contact.objects.select_for_update().get(pk=pk, book=book)
            except Contact.DoesNotExist as exc:
                raise Http404("Contact not found.") from exc

            post_data = contact_forms.normalize_contact_post_data(
                request.POST,
                prefix="phone_numbers",
                instance=contact,
            )
            form = contact_forms.ContactForm(
                post_data,
                request.FILES,
                instance=contact,
                book=book,
            )
            phone_formset = contact_forms.PhoneNumberEditInlineFormSet(
                post_data,
                instance=contact,
                prefix="phone_numbers",
                book=book,
            )

            if not (form.is_valid() and phone_formset.is_valid()):
                return render(
                    request,
                    self.template_name,
                    {
                        "form": form,
                        "phone_formset": phone_formset,
                        "contact": contact,
                        "is_edit": True,
                    },
                    status=400,
                )

            updated_contact = _persist_contact_with_phones(
                contact_form=form,
                phone_formset=phone_formset,
                contact_book=book,
            )
        messages.success(request, "Contact details updated successfully.")
        detail_url = reverse("contacts:detail", kwargs={"pk": updated_contact.pk})

        if request.headers.get("HX-Request") == "true":
            response = HttpResponse(status=200)
            response["HX-Redirect"] = detail_url
            return response

        return redirect(detail_url)


@method_decorator(login_required, name="dispatch")
@method_decorator(require_POST, name="dispatch")
class ContactDeleteView(View):
    """Permanently delete a single contact after explicit confirmation safeguard."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        if request.POST.get("confirm") != "true":
            return HttpResponse("Deletion confirmation is required.", status=400)

        book = _get_user_contact_book(request.user)
        with transaction.atomic():
            try:
                contact = Contact.objects.select_for_update().get(pk=pk, book=book)
            except Contact.DoesNotExist:
                if request.headers.get("HX-Request") == "true":
                    return HttpResponse("Contact not found or already deleted.", status=404)
                return render(request, "404.html", status=404)

            contact_name = contact.full_name
            old_avatar = contact.avatar
            contact.delete()
            if old_avatar:
                schedule_media_delete_on_commit(old_avatar)

        messages.success(request, f"Contact '{contact_name}' has been deleted.")
        if request.headers.get("HX-Request") == "true":
            response = HttpResponse("", status=200)
            response["HX-Trigger"] = "contactDeleted"
            return response

        return redirect("contacts:list")


@method_decorator(login_required, name="dispatch")
@method_decorator(require_POST, name="dispatch")
class ContactBatchDeleteView(View):
    """Permanently delete multiple selected contacts scoped to the user's ContactBook."""

    def post(self, request: HttpRequest) -> HttpResponse:
        if request.POST.get("confirm") != "true":
            return HttpResponse("Deletion confirmation is required.", status=400)

        raw_ids = request.POST.getlist("contact_ids")
        parsed_ids: list[int] = []
        for item in raw_ids:
            for part in str(item).split(","):
                part = part.strip()
                if not part:
                    continue
                if not part.isdigit():
                    return HttpResponse("Invalid contact selection.", status=400)
                parsed_ids.append(int(part))

        if not parsed_ids:
            return HttpResponse("At least one contact must be selected.", status=400)

        book = _get_user_contact_book(request.user)
        with transaction.atomic():
            queryset = Contact.objects.filter(id__in=parsed_ids, book=book)
            deleted_count = queryset.count()
            if deleted_count == 0:
                if request.headers.get("HX-Request") == "true":
                    return HttpResponse("No matching contacts found.", status=404)
                return render(request, "404.html", status=404)
            avatars_to_delete = list(
                queryset.exclude(avatar__isnull=True)
                .exclude(avatar="")
                .values_list("avatar", flat=True)
            )
            queryset.delete()
            for avatar_url in avatars_to_delete:
                schedule_media_delete_on_commit(avatar_url)

        messages.success(request, f"Successfully deleted {deleted_count} contacts.")
        if request.headers.get("HX-Request") == "true":
            response = HttpResponse("", status=200)
            response["HX-Trigger"] = "contactDeleted"
            return response

        return redirect("contacts:list")


def _extract_candidate_phones(post_data) -> list[str]:
    """Collect phone numbers from direct fields or inline formset POST keys."""
    phones: list[str] = []

    direct_phone = post_data.get("phone_number")
    if direct_phone:
        phones.append(str(direct_phone))

    primary_phone = post_data.get("primary_phone")
    if primary_phone:
        phones.append(str(primary_phone))

    for sec_phone in post_data.getlist("secondary_phones"):
        if sec_phone:
            phones.append(str(sec_phone))

    for key, value in post_data.items():
        match = _FORMSET_PHONE_KEY_RE.match(key)
        if not match or not value:
            continue
        idx = match.group(1)
        delete_flag = str(post_data.get(f"phone_numbers-{idx}-DELETE") or "").lower()
        if delete_flag in {"on", "true", "1"}:
            continue
        phones.append(str(value))

    return phones


@method_decorator(login_required, name="dispatch")
@method_decorator(require_POST, name="dispatch")
class DuplicateCheckView(View):
    """Proactive duplicate contact detection endpoint triggered on form blur (T058)."""

    partial_template = "contacts/partials/duplicate_warning_card.html"

    def post(self, request: HttpRequest) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        full_name = request.POST.get("full_name")
        candidate_phones = _extract_candidate_phones(request.POST)

        raw_exclude = str(request.POST.get("exclude_contact_id") or "").strip()
        exclude_contact_id = int(raw_exclude) if raw_exclude.isdigit() else None

        candidates = contact_services.DuplicateDetectionService.find_duplicates(
            book=book,
            full_name=full_name,
            phone_numbers=candidate_phones,
            exclude_contact_id=exclude_contact_id,
        )

        if not candidates:
            return HttpResponse("", status=200)

        return render(
            request,
            self.partial_template,
            {
                "candidates": candidates,
                "exclude_contact_id": exclude_contact_id,
            },
        )


@method_decorator(login_required, name="dispatch")
class SmartMergeView(View):
    """Render side-by-side merge preview (GET) and execute atomic smart merge (POST) (T059)."""

    partial_template = "contacts/partials/merge_preview_modal.html"
    full_template = "contacts/merge_preview.html"

    @staticmethod
    def _parse_positive_int(raw_value: str | None) -> int | None:
        cleaned = str(raw_value or "").strip()
        if not cleaned.isdigit():
            return None
        val = int(cleaned)
        return val if val > 0 else None

    def get(self, request: HttpRequest) -> HttpResponse:
        target_id = self._parse_positive_int(request.GET.get("target_contact_id"))
        source_id = self._parse_positive_int(request.GET.get("source_contact_id"))
        if target_id is None or source_id is None:
            return HttpResponse(
                "Both target_contact_id and source_contact_id are required.",
                status=400,
            )

        if target_id == source_id:
            return HttpResponse(contact_services.ERR_MERGE_SAME_CONTACT, status=400)

        book = _get_user_contact_book(request.user)
        target_contact = (
            Contact.objects.prefetch_related("phone_numbers")
            .filter(pk=target_id, book=book)
            .first()
        )
        source_contact = (
            Contact.objects.prefetch_related("phone_numbers")
            .filter(pk=source_id, book=book)
            .first()
        )
        if target_contact is None or source_contact is None:
            if request.headers.get("HX-Request") == "true":
                return HttpResponse("One or both contacts could not be found.", status=404)
            return render(request, "404.html", status=404)

        preview = contact_services.SmartMergeService.build_merge_preview(
            target_contact=target_contact,
            source_contact=source_contact,
        )
        context = {
            "preview": preview,
            "is_htmx": request.headers.get("HX-Request") == "true",
        }
        if request.headers.get("HX-Request") == "true":
            return render(request, self.partial_template, context)
        return render(request, self.full_template, context)

    def post(self, request: HttpRequest) -> HttpResponse:
        target_id = self._parse_positive_int(request.POST.get("target_contact_id"))
        source_id = self._parse_positive_int(request.POST.get("source_contact_id"))
        if target_id is None or source_id is None:
            return HttpResponse(
                "Valid target_contact_id and source_contact_id are required.",
                status=400,
            )

        if target_id == source_id:
            return HttpResponse(contact_services.ERR_MERGE_SAME_CONTACT, status=400)

        book = _get_user_contact_book(request.user)
        try:
            merged_contact = contact_services.SmartMergeService.merge_by_ids(
                book=book,
                target_contact_id=target_id,
                source_contact_id=source_id,
            )
        except contact_services.MergeValidationError as exc:
            return HttpResponse(str(exc), status=400)
        except contact_services.MergeNotFoundError:
            if request.headers.get("HX-Request") == "true":
                return HttpResponse("One or both contacts could not be found.", status=404)
            return render(request, "404.html", status=404)

        messages.success(request, "Contacts merged successfully without data loss.")
        return redirect(reverse("contacts:detail", kwargs={"pk": merged_contact.pk}))


@method_decorator(login_required, name="dispatch")
@method_decorator(require_POST, name="dispatch")
class ContactInteractView(View):
    """Atomically record a user-initiated contact interaction (FR-025)."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        try:
            contact = FrequencyTrackingService.record_interaction(book=book, contact_id=pk)
        except FavoriteNotFoundError:
            return JsonResponse({"error": "Contact not found."}, status=404)

        return JsonResponse(
            {
                "status": "ok",
                "interaction_count": contact.interaction_count,
            },
            status=200,
        )
