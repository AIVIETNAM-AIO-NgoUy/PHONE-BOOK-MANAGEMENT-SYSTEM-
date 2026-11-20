"""URL routing for administrative user governance panel (T095)."""

from django.urls import path

from apps.admin_panel import views

app_name = "admin_panel"

urlpatterns = [
    path("", views.AdminDashboardView.as_view(), name="dashboard"),
    path("users/", views.AdminUserListView.as_view(), name="user_list"),
    path("users/create/", views.AdminUserCreateView.as_view(), name="user_create"),
    path("users/<int:user_id>/", views.AdminUserDetailView.as_view(), name="user_detail"),
    path("users/<int:user_id>/edit/", views.AdminUserEditView.as_view(), name="user_edit"),
    path("users/<int:user_id>/delete/", views.AdminUserDeleteView.as_view(), name="user_delete"),
    path("users/<int:user_id>/lock/", views.AdminAccountLockView.as_view(), name="user_lock"),
    path(
        "users/<int:user_id>/unlock/",
        views.AdminAccountUnlockView.as_view(),
        name="user_unlock",
    ),
]
