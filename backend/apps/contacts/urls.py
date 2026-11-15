"""URL routing for core contact lifecycle endpoints."""

from django.urls import path

from apps.contacts import views

app_name = "contacts"

urlpatterns = [
    path("", views.ContactListView.as_view(), name="list"),
    path("search/", views.ContactSearchView.as_view(), name="search"),
    path("create/", views.ContactCreateView.as_view(), name="create"),
    path("check-duplicate/", views.DuplicateCheckView.as_view(), name="check_duplicate"),
    path("merge/", views.SmartMergeView.as_view(), name="merge"),
    path("batch-delete/", views.ContactBatchDeleteView.as_view(), name="batch_delete"),
    path("<int:pk>/", views.ContactDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.ContactEditView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.ContactDeleteView.as_view(), name="delete"),
    path("<int:pk>/interact/", views.ContactInteractView.as_view(), name="interact"),
]
