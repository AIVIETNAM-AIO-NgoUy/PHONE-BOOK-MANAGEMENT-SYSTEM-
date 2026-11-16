"""Administrative governance views enforcing RBAC, credential masking, and privacy (T094)."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.functions import Lower
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

from apps.accounts.models import CustomUser
from apps.admin_panel.forms import AdminUserCreateForm, AdminUserEditForm
from apps.admin_panel.models import AuditLog
from apps.admin_panel.services import AccountGovernanceService, GovernanceError
from apps.contacts.models import Contact
from apps.core.decorators import admin_required

USERS_PER_PAGE = 25
SAFE_USER_FIELDS = (
    "id",
    "username",
    "email",
    "full_name",
    "role",
    "account_status",
    "created_at",
    "last_login",
)


def _is_htmx(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def _get_client_ip(request: HttpRequest) -> str | None:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()[:45] or None
    remote_addr = request.META.get("REMOTE_ADDR")
    return remote_addr[:45] if remote_addr else None


def _safe_user_queryset():
    return CustomUser.objects.only(*SAFE_USER_FIELDS)


def _get_safe_user_detail(user_id: int) -> CustomUser | None:
    target_user = _safe_user_queryset().filter(pk=user_id).first()
    if target_user is None:
        return None
    target_user.contact_count = Contact.objects.filter(book__user_id=target_user.pk).count()
    return target_user


def _handle_account_status_action(
    request: HttpRequest,
    user_id: int,
    *,
    lock: bool,
) -> HttpResponse:
    reason = request.POST.get("reason", "")
    ip_address = _get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")

    try:
        if lock:
            target_user = AccountGovernanceService.lock_user_account(
                actor=request.user,
                target_user_id=user_id,
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            success_msg = (
                f"Account for user '{target_user.username}' "
                "has been locked and active sessions revoked."
            )
        else:
            target_user = AccountGovernanceService.unlock_user_account(
                actor=request.user,
                target_user_id=user_id,
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            success_msg = (
                f"Account for user '{target_user.username}' has been restored to Active status."
            )
    except CustomUser.DoesNotExist:
        if _is_htmx(request):
            return HttpResponse("User not found.", status=404)
        return render(request, "404.html", status=404)
    except GovernanceError as exc:
        if _is_htmx(request):
            return HttpResponse(exc.message, status=exc.status_code)
        target_user = _get_safe_user_detail(user_id)
        if target_user is None:
            return HttpResponse(exc.message, status=exc.status_code)
        audit_logs = AuditLog.objects.filter(target_user_id=target_user.pk).order_by(
            "-timestamp", "-id"
        )[:20]
        return render(
            request,
            "admin_panel/user_detail.html",
            {
                "target_user": target_user,
                "audit_logs": audit_logs,
                "governance_error": exc.message,
                "governance_error_code": exc.code,
            },
            status=exc.status_code,
        )

    if _is_htmx(request):
        return render(
            request,
            "admin_panel/partials/account_status_actions.html",
            {
                "target_user": target_user,
                "status_message": success_msg,
            },
        )

    messages.success(request, success_msg)
    return redirect("admin_panel:user_detail", user_id=target_user.pk)


@method_decorator(admin_required, name="dispatch")
class AdminDashboardView(View):
    """Display platform KPIs, recent registrations, and recent governance audit logs."""

    template_name = "admin_panel/dashboard.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        total_users_count = CustomUser.objects.count()
        active_users_count = CustomUser.objects.filter(
            account_status=CustomUser.AccountStatus.ACTIVE
        ).count()
        locked_users_count = CustomUser.objects.filter(
            account_status=CustomUser.AccountStatus.LOCKED
        ).count()
        recent_registrations = list(_safe_user_queryset().order_by("-created_at", "-id")[:10])
        recent_audit_logs = list(AuditLog.objects.order_by("-timestamp", "-id")[:15])

        return render(
            request,
            self.template_name,
            {
                "total_users_count": total_users_count,
                "active_users_count": active_users_count,
                "locked_users_count": locked_users_count,
                "recent_registrations": recent_registrations,
                "recent_audit_logs": recent_audit_logs,
            },
        )


@method_decorator(admin_required, name="dispatch")
class AdminUserListView(View):
    """Paginated, searchable, and filterable roster of user account metadata."""

    template_name = "admin_panel/user_list.html"
    partial_template_name = "admin_panel/partials/user_table_rows.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        search_query = (request.GET.get("q") or "").strip()
        status_filter = (request.GET.get("status") or "all").strip()
        sort = (request.GET.get("sort") or "date_desc").strip()

        queryset = _safe_user_queryset()
        if search_query:
            queryset = queryset.filter(
                Q(username__icontains=search_query) | Q(email__icontains=search_query)
            )

        if status_filter in {
            CustomUser.AccountStatus.ACTIVE,
            CustomUser.AccountStatus.LOCKED,
        }:
            queryset = queryset.filter(account_status=status_filter)
        else:
            status_filter = "all"

        if sort == "date_asc":
            queryset = queryset.order_by("created_at", "id")
        elif sort == "username_asc":
            queryset = queryset.order_by(Lower("username"), "id")
        else:
            sort = "date_desc"
            queryset = queryset.order_by("-created_at", "-id")

        paginator = Paginator(queryset, USERS_PER_PAGE)
        page_obj = paginator.get_page(request.GET.get("page"))

        is_htmx = _is_htmx(request)
        context = {
            "page_obj": page_obj,
            "users": page_obj.object_list,
            "search_query": search_query,
            "status_filter": status_filter,
            "sort": sort,
            "total_matching_count": paginator.count,
            "is_htmx": is_htmx,
        }

        if is_htmx:
            return render(request, self.partial_template_name, context)
        return render(request, self.template_name, context)


@method_decorator(admin_required, name="dispatch")
class AdminUserCreateView(View):
    """Provision a new user account with role assignment and initial credentials."""

    template_name = "admin_panel/user_create.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        form = AdminUserCreateForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request: HttpRequest) -> HttpResponse:
        form = AdminUserCreateForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form}, status=400)

        ip_address = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        try:
            created_user = AccountGovernanceService.create_user_account(
                actor=request.user,
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                full_name=form.cleaned_data["full_name"],
                password=form.cleaned_data["password"],
                role=form.cleaned_data["role"],
                account_status=form.cleaned_data["account_status"],
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception as exc:
            form.add_error(None, str(exc))
            return render(request, self.template_name, {"form": form}, status=400)

        messages.success(request, f"User '{created_user.username}' created successfully.")
        detail_url = reverse("admin_panel:user_detail", kwargs={"user_id": created_user.pk})
        if _is_htmx(request):
            response = HttpResponse(status=200)
            response["HX-Redirect"] = detail_url
            return response
        return redirect(detail_url)


@method_decorator(admin_required, name="dispatch")
class AdminUserDetailView(View):
    """Display safe account metadata and aggregate contact count without personal contacts."""

    template_name = "admin_panel/user_detail.html"

    def get(self, request: HttpRequest, user_id: int) -> HttpResponse:
        target_user = _get_safe_user_detail(user_id)
        if target_user is None:
            return render(request, "404.html", status=404)

        audit_logs = list(
            AuditLog.objects.filter(target_user_id=target_user.pk).order_by("-timestamp", "-id")[
                :20
            ]
        )

        return render(
            request,
            self.template_name,
            {
                "target_user": target_user,
                "audit_logs": audit_logs,
            },
        )


@method_decorator(admin_required, name="dispatch")
class AdminUserEditView(View):
    """Edit account metadata, role, status, or reset credentials."""

    template_name = "admin_panel/user_edit.html"

    def get(self, request: HttpRequest, user_id: int) -> HttpResponse:
        target_user = CustomUser.objects.filter(pk=user_id).first()
        if target_user is None:
            return render(request, "404.html", status=404)

        form = AdminUserEditForm(
            actor=request.user,
            target_user=target_user,
            initial={
                "full_name": target_user.full_name,
                "email": target_user.email,
                "role": target_user.role,
                "account_status": target_user.account_status,
            },
        )
        return render(
            request,
            self.template_name,
            {"form": form, "target_user": target_user},
        )

    def post(self, request: HttpRequest, user_id: int) -> HttpResponse:
        target_user = CustomUser.objects.filter(pk=user_id).first()
        if target_user is None:
            return render(request, "404.html", status=404)

        form = AdminUserEditForm(
            request.POST,
            actor=request.user,
            target_user=target_user,
        )
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {"form": form, "target_user": target_user},
                status=400,
            )

        ip_address = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        try:
            AccountGovernanceService.update_user_account(
                actor=request.user,
                target_user_id=user_id,
                full_name=form.cleaned_data["full_name"],
                email=form.cleaned_data["email"],
                role=form.cleaned_data["role"],
                account_status=form.cleaned_data["account_status"],
                new_password=form.cleaned_data.get("new_password") or None,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except GovernanceError as exc:
            form.add_error(None, exc.message)
            return render(
                request,
                self.template_name,
                {"form": form, "target_user": target_user},
                status=exc.status_code,
            )

        messages.success(request, f"User '{target_user.username}' updated successfully.")
        detail_url = reverse("admin_panel:user_detail", kwargs={"user_id": target_user.pk})
        if _is_htmx(request):
            response = HttpResponse(status=200)
            response["HX-Redirect"] = detail_url
            return response
        return redirect(detail_url)


@method_decorator(admin_required, name="dispatch")
class AdminUserDeleteView(View):
    """Delete a user account with confirmation safeguard and self-delete protection."""

    def post(self, request: HttpRequest, user_id: int) -> HttpResponse:
        confirm = request.POST.get("confirm") == "true"
        if not confirm:
            if _is_htmx(request):
                return HttpResponse("Deletion confirmation is required.", status=400)
            target_user = _get_safe_user_detail(user_id)
            if target_user is None:
                return HttpResponse("Deletion confirmation is required.", status=400)
            audit_logs = list(
                AuditLog.objects.filter(target_user_id=target_user.pk).order_by(
                    "-timestamp", "-id"
                )[:20]
            )
            return render(
                request,
                "admin_panel/user_detail.html",
                {
                    "target_user": target_user,
                    "audit_logs": audit_logs,
                    "governance_error": "Deletion confirmation is required.",
                    "governance_error_code": "ERR_CONFIRMATION_REQUIRED",
                },
                status=400,
            )

        ip_address = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        try:
            AccountGovernanceService.delete_user_account(
                actor=request.user,
                target_user_id=user_id,
                confirm=confirm,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except CustomUser.DoesNotExist:
            if _is_htmx(request):
                return HttpResponse("User not found.", status=404)
            return render(request, "404.html", status=404)
        except GovernanceError as exc:
            if _is_htmx(request):
                return HttpResponse(exc.message, status=exc.status_code)
            target_user = _get_safe_user_detail(user_id)
            if target_user is None:
                return HttpResponse(exc.message, status=exc.status_code)
            audit_logs = list(
                AuditLog.objects.filter(target_user_id=target_user.pk).order_by(
                    "-timestamp", "-id"
                )[:20]
            )
            return render(
                request,
                "admin_panel/user_detail.html",
                {
                    "target_user": target_user,
                    "audit_logs": audit_logs,
                    "governance_error": exc.message,
                    "governance_error_code": exc.code,
                },
                status=exc.status_code,
            )

        messages.success(request, "User account has been permanently deleted.")
        if _is_htmx(request):
            response = HttpResponse(status=200)
            response["HX-Redirect"] = reverse("admin_panel:user_list")
            return response
        return redirect("admin_panel:user_list")


@method_decorator(admin_required, name="dispatch")
class AdminAccountLockView(View):
    """Lock a user account, evict sessions, and log the governance action."""

    def post(self, request: HttpRequest, user_id: int) -> HttpResponse:
        return _handle_account_status_action(request, user_id, lock=True)


@method_decorator(admin_required, name="dispatch")
class AdminAccountUnlockView(View):
    """Restore a locked user account to Active status and log the governance action."""

    def post(self, request: HttpRequest, user_id: int) -> HttpResponse:
        return _handle_account_status_action(request, user_id, lock=False)
