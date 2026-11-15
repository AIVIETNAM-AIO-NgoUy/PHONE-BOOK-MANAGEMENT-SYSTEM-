"""URL routing for custom contact group management endpoints (T083)."""

from django.urls import path

from apps.groups import views

app_name = "groups"

urlpatterns = [
    path("", views.GroupListView.as_view(), name="list"),
    path("create/", views.GroupCreateView.as_view(), name="create"),
    path("<int:pk>/", views.GroupDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.GroupEditView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.GroupDeleteView.as_view(), name="delete"),
    path("<int:pk>/members/add/", views.GroupMemberAddView.as_view(), name="member_add"),
    path(
        "<int:pk>/members/<int:contact_id>/remove/",
        views.GroupMemberRemoveView.as_view(),
        name="member_remove",
    ),
]
