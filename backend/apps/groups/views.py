"""Views for contact group lifecycle and membership management (T082)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST

from apps.contacts.models import ContactBook
from apps.contacts.services import SearchOptimizationService
from apps.groups import forms as group_forms, services as group_services
from apps.groups.models import ContactGroup

GROUP_MEMBERS_PER_PAGE = 20


def _get_user_contact_book(user) -> ContactBook:
    contact_book, _ = ContactBook.objects.get_or_create(user=user)
    return contact_book


def _is_htmx(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def _not_found_response(request: HttpRequest, message: str) -> HttpResponse:
    if _is_htmx(request):
        return HttpResponse(message, status=404)
    return render(request, "404.html", status=404)


def _extract_first_form_error(form) -> str:
    for field_errors in form.errors.values():
        if field_errors:
            return str(field_errors[0])
    non_field = form.non_field_errors()
    if non_field:
        return str(non_field[0])
    return "Invalid group submission."


@method_decorator(login_required, name="dispatch")
class GroupListView(View):
    """Display all custom groups in the user's ContactBook with member counts."""

    template_name = "groups/group_list.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        groups = list(group_services.GroupMembershipService.list_groups(book=book))
        return render(
            request,
            self.template_name,
            {
                "groups": groups,
                "total_groups_count": len(groups),
                "form": group_forms.GroupForm(book=book),
            },
        )


@method_decorator(login_required, name="dispatch")
class GroupCreateView(View):
    """Create a new contact group with unique name validation per ContactBook."""

    form_template_name = "groups/group_form.html"
    list_template_name = "groups/group_list.html"
    row_partial_template = "groups/partials/group_table_row.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        return render(
            request,
            self.form_template_name,
            {
                "form": group_forms.GroupForm(book=book),
                "is_edit": False,
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        form = group_forms.GroupForm(request.POST, book=book)
        if not form.is_valid():
            error_message = _extract_first_form_error(form)
            if _is_htmx(request):
                return HttpResponse(error_message, status=400)
            groups = list(group_services.GroupMembershipService.list_groups(book=book))
            return render(
                request,
                self.list_template_name,
                {
                    "groups": groups,
                    "total_groups_count": len(groups),
                    "form": form,
                    "open_create_modal": True,
                },
                status=400,
            )

        try:
            group = group_services.GroupMembershipService.create_group(
                book=book,
                group_name=form.cleaned_data["group_name"],
                description=form.cleaned_data["description"],
            )
        except group_services.GroupValidationError as exc:
            if _is_htmx(request):
                return HttpResponse(str(exc), status=400)
            form.add_error("group_name", str(exc))
            groups = list(group_services.GroupMembershipService.list_groups(book=book))
            return render(
                request,
                self.list_template_name,
                {
                    "groups": groups,
                    "total_groups_count": len(groups),
                    "form": form,
                    "open_create_modal": True,
                },
                status=400,
            )

        group.member_count = 0
        if _is_htmx(request):
            return render(
                request,
                self.row_partial_template,
                {"group": group},
            )

        messages.success(request, f"Group '{group.group_name}' created successfully.")
        return redirect("groups:list")


@method_decorator(login_required, name="dispatch")
class GroupDetailView(View):
    """Display group metadata, paginated/searchable members, and quick-add selector."""

    template_name = "groups/group_detail.html"
    members_partial_template = "groups/partials/group_member_section.html"

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        try:
            group = group_services.GroupMembershipService.get_group(book=book, group_id=pk)
        except group_services.GroupNotFoundError:
            return _not_found_response(request, group_services.ERR_GROUP_NOT_FOUND)

        search_query = SearchOptimizationService.sanitize_query(request.GET.get("q"))
        members_qs = group_services.GroupMembershipService.list_group_members(
            group=group,
            query=search_query,
        )
        paginator = Paginator(members_qs, GROUP_MEMBERS_PER_PAGE)
        page_obj = paginator.get_page(request.GET.get("page"))
        member_contacts = list(page_obj.object_list)
        available_contacts = list(
            group_services.GroupMembershipService.list_available_contacts(group=group)
        )
        total_members_count = ContactGroup.objects.filter(group=group).count()

        context = {
            "group": group,
            "page_obj": page_obj,
            "member_contacts": member_contacts,
            "available_contacts": available_contacts,
            "search_query": search_query,
            "total_members_count": total_members_count,
            "matched_members_count": paginator.count,
            "edit_form": group_forms.GroupForm(instance=group, book=book),
        }

        if _is_htmx(request):
            return render(request, self.members_partial_template, context)

        return render(request, self.template_name, context)


@method_decorator(login_required, name="dispatch")
class GroupEditView(View):
    """Update an owned group's name and optional description."""

    template_name = "groups/group_form.html"

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        try:
            group = group_services.GroupMembershipService.get_group(book=book, group_id=pk)
        except group_services.GroupNotFoundError:
            return _not_found_response(request, group_services.ERR_GROUP_NOT_FOUND)

        return render(
            request,
            self.template_name,
            {
                "form": group_forms.GroupForm(instance=group, book=book),
                "group": group,
                "is_edit": True,
            },
        )

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        try:
            group = group_services.GroupMembershipService.get_group(book=book, group_id=pk)
        except group_services.GroupNotFoundError:
            return _not_found_response(request, group_services.ERR_GROUP_NOT_FOUND)

        form = group_forms.GroupForm(
            request.POST,
            instance=group,
            book=book,
            exclude_group_id=group.pk,
        )
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "group": group,
                    "is_edit": True,
                },
                status=400,
            )

        try:
            updated_group = group_services.GroupMembershipService.update_group(
                book=book,
                group_id=group.pk,
                group_name=form.cleaned_data["group_name"],
                description=form.cleaned_data["description"],
            )
        except group_services.GroupValidationError as exc:
            form.add_error("group_name", str(exc))
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "group": group,
                    "is_edit": True,
                },
                status=400,
            )

        messages.success(request, "Group updated successfully.")
        return redirect("groups:detail", pk=updated_group.pk)


@method_decorator(login_required, name="dispatch")
@method_decorator(require_POST, name="dispatch")
class GroupDeleteView(View):
    """Delete an owned group after explicit confirmation while retaining all Contacts."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        try:
            group = group_services.GroupMembershipService.get_group(book=book, group_id=pk)
        except group_services.GroupNotFoundError:
            return _not_found_response(request, group_services.ERR_GROUP_NOT_FOUND)

        if request.POST.get("confirm") != "true":
            return HttpResponse("Deletion confirmation is required.", status=400)

        try:
            group_name = group_services.GroupMembershipService.delete_group(
                book=book,
                group_id=group.pk,
            )
        except group_services.GroupNotFoundError:
            return _not_found_response(request, group_services.ERR_GROUP_NOT_FOUND)

        messages.success(
            request,
            f"Group '{group_name}' deleted. All associated contacts remain in your directory.",
        )
        if _is_htmx(request):
            response = HttpResponse("", status=200)
            response["HX-Trigger"] = "groupDeleted"
            return response

        return redirect("groups:list")


@method_decorator(login_required, name="dispatch")
@method_decorator(require_POST, name="dispatch")
class GroupMemberAddView(View):
    """Assign an owned Contact to an owned Group without duplicate links."""

    members_partial_template = "groups/partials/group_member_section.html"

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        try:
            group = group_services.GroupMembershipService.get_group(book=book, group_id=pk)
        except group_services.GroupNotFoundError:
            return _not_found_response(request, group_services.ERR_GROUP_NOT_FOUND)

        form = group_forms.GroupMemberAddForm(request.POST, book=book)
        if not form.is_valid():
            contact_errors = form.errors.as_data().get("contact_id", [])
            if any(err.code == "contact_not_found" for err in contact_errors):
                return _not_found_response(request, group_services.ERR_CONTACT_NOT_FOUND)
            return HttpResponse(_extract_first_form_error(form), status=400)

        try:
            group_services.GroupMembershipService.add_member(
                book=book,
                group_id=group.pk,
                contact_id=form.cleaned_data["contact_id"],
            )
        except group_services.GroupMemberDuplicateError as exc:
            return HttpResponse(str(exc), status=400)
        except group_services.GroupNotFoundError as exc:
            return _not_found_response(request, str(exc))

        if _is_htmx(request):
            members_qs = group_services.GroupMembershipService.list_group_members(group=group)
            paginator = Paginator(members_qs, GROUP_MEMBERS_PER_PAGE)
            page_obj = paginator.get_page(1)
            available_contacts = list(
                group_services.GroupMembershipService.list_available_contacts(group=group)
            )
            return render(
                request,
                self.members_partial_template,
                {
                    "group": group,
                    "page_obj": page_obj,
                    "member_contacts": list(page_obj.object_list),
                    "available_contacts": available_contacts,
                    "search_query": "",
                    "total_members_count": paginator.count,
                    "matched_members_count": paginator.count,
                    "oob_member_count_badge": True,
                },
            )

        messages.success(request, "Contact added to group.")
        return redirect("groups:detail", pk=group.pk)


@method_decorator(login_required, name="dispatch")
@method_decorator(require_POST, name="dispatch")
class GroupMemberRemoveView(View):
    """Remove a ContactGroup membership link without deleting the underlying Contact."""

    members_partial_template = "groups/partials/group_member_section.html"

    def post(self, request: HttpRequest, pk: int, contact_id: int) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        try:
            group_services.GroupMembershipService.remove_member(
                book=book,
                group_id=pk,
                contact_id=contact_id,
            )
        except group_services.GroupNotFoundError as exc:
            return _not_found_response(request, str(exc))

        if _is_htmx(request):
            group = group_services.GroupMembershipService.get_group(book=book, group_id=pk)
            search_query = SearchOptimizationService.sanitize_query(
                request.POST.get("q") or request.GET.get("q")
            )
            members_qs = group_services.GroupMembershipService.list_group_members(
                group=group,
                query=search_query,
            )
            paginator = Paginator(members_qs, GROUP_MEMBERS_PER_PAGE)
            page_obj = paginator.get_page(request.POST.get("page") or request.GET.get("page"))
            available_contacts = list(
                group_services.GroupMembershipService.list_available_contacts(group=group)
            )
            total_members_count = ContactGroup.objects.filter(group=group).count()
            response = render(
                request,
                self.members_partial_template,
                {
                    "group": group,
                    "page_obj": page_obj,
                    "member_contacts": list(page_obj.object_list),
                    "available_contacts": available_contacts,
                    "search_query": search_query,
                    "total_members_count": total_members_count,
                    "matched_members_count": paginator.count,
                    "oob_member_count_badge": True,
                },
            )
            response["HX-Trigger"] = "groupMemberRemoved"
            return response

        messages.success(request, "Contact removed from group.")
        return redirect("groups:detail", pk=pk)
