"""Root URL configuration for Phone Book Management System."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.core.views import healthz, root_redirect_view

urlpatterns = [
    path("", root_redirect_view, name="root"),
    path("admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
    path("accounts/", include("apps.accounts.urls")),
    path("contacts/", include("apps.contacts.urls")),
    path("favorites/", include("apps.favorites.urls")),
    path("groups/", include("apps.groups.urls")),
    path("admin-panel/", include("apps.admin_panel.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = "apps.core.views.custom_403_view"
handler404 = "apps.core.views.custom_404_view"
handler500 = "apps.core.views.custom_500_view"
