"""Views for favorite contacts listing, bookmark toggling, and priority updates (T071)."""

from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_POST

from apps.contacts.models import Contact, ContactBook
from apps.favorites import services as favorite_services
from apps.favorites.forms import ERR_FAVORITE_INVALID_PRIORITY, FavoritePriorityForm
from apps.favorites.models import FavoriteItem


def _get_user_contact_book(user) -> ContactBook:
    contact_book, _ = ContactBook.objects.get_or_create(user=user)
    return contact_book


def _resolve_safe_redirect(request: HttpRequest, fallback_url: str) -> str:
    """Validate optional next parameter against current host to prevent open redirects."""
    next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return fallback_url


def _resolve_toggle_next_url(request: HttpRequest, *, fallback_url: str) -> str:
    """Resolve a safe return URL for HTMX toggle partials without baking action URLs."""
    candidates = [
        (request.POST.get("next") or "").strip(),
        (request.headers.get("HX-Current-URL") or "").strip(),
        (request.headers.get("Referer") or "").strip(),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if not url_has_allowed_host_and_scheme(
            candidate,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            continue
        parsed = urlsplit(candidate)
        path_with_query = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        if path_with_query.startswith(("/favorites/add/", "/favorites/remove/")):
            continue
        if path_with_query:
            return path_with_query
    return fallback_url


@method_decorator(login_required, name="dispatch")
class FavoriteListView(View):
    """Render the user's isolated favorite contacts list with priority/frequency/name sorting."""

    template_name = "favorites/favorite_list.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        favorite_list = favorite_services.FavoriteService.get_or_create_favorite_list(request.user)
        sort_key = favorite_services.FavoriteService.resolve_sort_key(request.GET.get("sort"))
        favorite_items = list(
            favorite_services.FavoriteService.list_favorites(
                favorite_list=favorite_list,
                sort_key=sort_key,
            )
        )

        return render(
            request,
            self.template_name,
            {
                "favorite_items": favorite_items,
                "current_sort": sort_key,
                "total_favorites_count": len(favorite_items),
                "priority_choices": favorite_services.FavoriteService.PRIORITY_CHOICES,
            },
        )


@method_decorator(login_required, name="dispatch")
@method_decorator(require_POST, name="dispatch")
class FavoriteAddView(View):
    """Bookmark an existing contact into the user's FavoriteList."""

    toggle_partial_template = "contacts/partials/favorite_toggle_button.html"

    def post(self, request: HttpRequest, contact_id: int) -> HttpResponse:
        book = _get_user_contact_book(request.user)

        if "priority" in request.POST:
            form = FavoritePriorityForm({"priority": request.POST.get("priority")})
            if not form.is_valid():
                return HttpResponse(ERR_FAVORITE_INVALID_PRIORITY, status=400)
            priority = form.cleaned_data["priority"]
        else:
            priority = FavoriteItem.DEFAULT_PRIORITY

        try:
            item = favorite_services.FavoriteService.add_favorite(
                book=book,
                contact_id=contact_id,
                priority=priority,
            )
        except favorite_services.FavoriteNotFoundError:
            if request.headers.get("HX-Request") == "true":
                return HttpResponse(favorite_services.ERR_CONTACT_NOT_FOUND, status=404)
            return render(request, "404.html", status=404)
        except favorite_services.FavoriteDuplicateError:
            return HttpResponse(favorite_services.ERR_FAVORITE_ALREADY_EXISTS, status=400)

        if request.headers.get("HX-Request") == "true":
            next_url = _resolve_toggle_next_url(
                request,
                fallback_url=reverse("contacts:list"),
            )
            return render(
                request,
                self.toggle_partial_template,
                {
                    "contact": item.contact,
                    "is_favorite": True,
                    "favorite_item": item,
                    "show_label": request.POST.get("show_label") == "1",
                    "next_url": next_url,
                },
            )

        messages.success(request, "Contact added to favorites.")
        return redirect(_resolve_safe_redirect(request, reverse("favorites:list")))


@method_decorator(login_required, name="dispatch")
@method_decorator(require_POST, name="dispatch")
class FavoriteRemoveView(View):
    """Remove a FavoriteItem without deleting the underlying Contact record (FR-022)."""

    toggle_partial_template = "contacts/partials/favorite_toggle_button.html"

    def post(self, request: HttpRequest, contact_id: int) -> HttpResponse:
        book = _get_user_contact_book(request.user)
        try:
            favorite_services.FavoriteService.remove_favorite(book=book, contact_id=contact_id)
        except favorite_services.FavoriteNotFoundError:
            if request.headers.get("HX-Request") == "true":
                return HttpResponse(favorite_services.ERR_FAVORITE_NOT_FOUND, status=404)
            return render(request, "404.html", status=404)

        if request.headers.get("HX-Request") == "true":
            mode = (request.POST.get("mode") or request.GET.get("mode") or "").strip()
            if mode == "row":
                remaining_count = FavoriteItem.objects.filter(favorite_list__book=book).count()
                response = HttpResponse("", status=200)
                response["HX-Trigger"] = "favoriteRemoved"
                if remaining_count == 0:
                    response["HX-Refresh"] = "true"
                return response

            contact = Contact.objects.filter(pk=contact_id, book=book).first()
            next_url = _resolve_toggle_next_url(
                request,
                fallback_url=reverse("contacts:list"),
            )
            return render(
                request,
                self.toggle_partial_template,
                {
                    "contact": contact,
                    "is_favorite": False,
                    "show_label": request.POST.get("show_label") == "1",
                    "next_url": next_url,
                },
            )

        messages.success(request, "Contact removed from favorites.")
        return redirect(_resolve_safe_redirect(request, reverse("favorites:list")))


@method_decorator(login_required, name="dispatch")
@method_decorator(require_POST, name="dispatch")
class FavoritePriorityUpdateView(View):
    """Update the priority rank [1..10] of an owned FavoriteItem (FR-023)."""

    badge_partial_template = "favorites/partials/priority_badge.html"

    def post(self, request: HttpRequest, item_id: int) -> HttpResponse:
        form = FavoritePriorityForm(request.POST)
        if not form.is_valid():
            return HttpResponse(ERR_FAVORITE_INVALID_PRIORITY, status=400)

        book = _get_user_contact_book(request.user)
        try:
            item = favorite_services.FavoriteService.update_priority(
                book=book,
                item_id=item_id,
                priority=form.cleaned_data["priority"],
            )
        except favorite_services.FavoriteNotFoundError:
            if request.headers.get("HX-Request") == "true":
                return HttpResponse(favorite_services.ERR_FAVORITE_NOT_FOUND, status=404)
            return render(request, "404.html", status=404)

        if request.headers.get("HX-Request") == "true":
            return render(
                request,
                self.badge_partial_template,
                {
                    "item": item,
                    "priority_choices": favorite_services.FavoriteService.PRIORITY_CHOICES,
                },
            )

        messages.success(request, "Favorite priority updated.")
        return redirect(_resolve_safe_redirect(request, reverse("favorites:list")))
