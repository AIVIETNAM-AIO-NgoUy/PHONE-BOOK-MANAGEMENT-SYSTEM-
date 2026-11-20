"""URL routing for favorite list and priority management endpoints (T072)."""

from django.urls import path

from apps.favorites import views

app_name = "favorites"

urlpatterns = [
    path("", views.FavoriteListView.as_view(), name="list"),
    path("add/<int:contact_id>/", views.FavoriteAddView.as_view(), name="add"),
    path("remove/<int:contact_id>/", views.FavoriteRemoveView.as_view(), name="remove"),
    path("<int:item_id>/priority/", views.FavoritePriorityUpdateView.as_view(), name="priority"),
]
