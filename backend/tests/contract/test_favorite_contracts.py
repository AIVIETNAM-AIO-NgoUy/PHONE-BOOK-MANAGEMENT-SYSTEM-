"""Contract tests for favorite list, priority, and interaction endpoints (T065)."""

from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.messages import get_messages


def _create_contact(user, *, full_name="Alice Smith", phones=None, **kwargs):
    from apps.contacts.models import Contact, PhoneNumber

    contact = Contact.objects.create(book=user.contact_book, full_name=full_name, **kwargs)
    phone_specs = phones or [("0901234567", "Mobile", True)]
    for number, ptype, is_primary in phone_specs:
        PhoneNumber.objects.create(
            contact=contact,
            phone_number=number,
            phone_type=ptype,
            is_primary=is_primary,
        )
    return contact


def _add_favorite(user, contact, *, priority=5):
    from apps.favorites.models import FavoriteItem

    return FavoriteItem.objects.create(
        favorite_list=user.contact_book.favorite_list,
        contact=contact,
        priority=priority,
    )


@pytest.mark.django_db
class TestFavoriteListContract:
    """Contract tests for GET /favorites/ (favorite-contracts.md 2.1)."""

    def test_anonymous_user_redirected_to_login(self, client):
        response = client.get("/favorites/")
        assert response.status_code == 302
        assert response.url.startswith("/accounts/login/")

    def test_authenticated_list_scoped_and_defaults_to_priority_sort(
        self, authenticated_client, user_factory
    ):
        client, owner = authenticated_client(username="fav_owner", email="favowner@example.com")
        other = user_factory(username="fav_other", email="favother@example.com")

        c_low = _create_contact(owner, full_name="Zoe Low", phones=[("0901111111", "Mobile", True)])
        c_high_b = _create_contact(
            owner, full_name="Bob High", phones=[("0902222222", "Mobile", True)]
        )
        c_high_a = _create_contact(
            owner, full_name="Alice High", phones=[("0903333333", "Mobile", True)]
        )
        c_non_fav = _create_contact(
            owner, full_name="Non Favorite", phones=[("0904444444", "Mobile", True)]
        )
        foreign_contact = _create_contact(
            other, full_name="Foreign Secret Fav", phones=[("0999888777", "Mobile", True)]
        )

        _add_favorite(owner, c_low, priority=9)
        _add_favorite(owner, c_high_b, priority=1)
        _add_favorite(owner, c_high_a, priority=1)
        _add_favorite(other, foreign_contact, priority=1)

        response = client.get("/favorites/")
        assert response.status_code == 200
        template_names = [t.name for t in response.templates if t.name]
        assert "favorites/favorite_list.html" in template_names
        assert response.context["current_sort"] == "priority"
        assert response.context["total_favorites_count"] == 3

        ordered_names = [item.contact.full_name for item in response.context["favorite_items"]]
        assert ordered_names == ["Alice High", "Bob High", "Zoe Low"]
        assert c_non_fav.full_name not in ordered_names
        assert b"Foreign Secret Fav" not in response.content

        # Invalid sort parameter gracefully falls back to 'priority'
        fallback_resp = client.get("/favorites/?sort=invalid_sort")
        assert fallback_resp.status_code == 200
        assert fallback_resp.context["current_sort"] == "priority"
        assert [item.contact.full_name for item in fallback_resp.context["favorite_items"]] == [
            "Alice High",
            "Bob High",
            "Zoe Low",
        ]

    def test_frequency_and_name_sort_contracts(self, authenticated_client):
        client, owner = authenticated_client(username="fav_sort", email="favsort@example.com")
        now = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)

        c_never = _create_contact(
            owner,
            full_name="Charlie Never",
            interaction_count=5,
            last_contacted_at=None,
        )
        c_recent = _create_contact(
            owner,
            full_name="Diana Recent",
            interaction_count=5,
            last_contacted_at=now,
        )
        c_older = _create_contact(
            owner,
            full_name="Aaron Older",
            interaction_count=5,
            last_contacted_at=now - timedelta(days=2),
        )
        c_top = _create_contact(
            owner,
            full_name="Zed Top",
            interaction_count=12,
            last_contacted_at=now - timedelta(days=5),
        )

        _add_favorite(owner, c_never, priority=1)
        _add_favorite(owner, c_recent, priority=4)
        _add_favorite(owner, c_older, priority=3)
        _add_favorite(owner, c_top, priority=10)

        freq_resp = client.get("/favorites/?sort=frequency")
        assert freq_resp.status_code == 200
        assert freq_resp.context["current_sort"] == "frequency"
        assert [item.contact.full_name for item in freq_resp.context["favorite_items"]] == [
            "Zed Top",
            "Diana Recent",
            "Aaron Older",
            "Charlie Never",
        ]

        name_resp = client.get("/favorites/?sort=name")
        assert name_resp.status_code == 200
        assert name_resp.context["current_sort"] == "name"
        assert [item.contact.full_name for item in name_resp.context["favorite_items"]] == [
            "Aaron Older",
            "Charlie Never",
            "Diana Recent",
            "Zed Top",
        ]


@pytest.mark.django_db
class TestFavoriteAddContract:
    """Contract tests for POST /favorites/add/<int:contact_id>/ (favorite-contracts.md 2.2)."""

    def test_add_requires_auth_and_post(self, client, authenticated_client):
        anon_resp = client.post("/favorites/add/1/")
        assert anon_resp.status_code == 302
        assert anon_resp.url.startswith("/accounts/login/")

        auth_client, user = authenticated_client(username="fav_add_m", email="favaddm@example.com")
        contact = _create_contact(user)
        get_resp = auth_client.get(f"/favorites/add/{contact.pk}/")
        assert get_resp.status_code == 405

    def test_standard_and_htmx_add_with_default_and_custom_priority(self, authenticated_client):
        from apps.favorites.models import FavoriteItem

        client, user = authenticated_client(username="fav_add", email="favadd@example.com")
        c1 = _create_contact(user, full_name="Default Priority Contact")
        c2 = _create_contact(user, full_name="Custom Priority Contact")

        # Standard POST with default priority=5
        resp_std = client.post(f"/favorites/add/{c1.pk}/")
        assert resp_std.status_code == 302
        assert resp_std.url == "/favorites/"
        item1 = FavoriteItem.objects.get(favorite_list=user.contact_book.favorite_list, contact=c1)
        assert item1.priority == 5

        # Safe same-host next redirect honored; external open redirect ignored
        c3 = _create_contact(user, full_name="Safe Redirect Contact")
        resp_safe_next = client.post(
            f"/favorites/add/{c3.pk}/",
            {"next": f"/contacts/{c3.pk}/"},
        )
        assert resp_safe_next.status_code == 302
        assert resp_safe_next.url == f"/contacts/{c3.pk}/"

        c4 = _create_contact(user, full_name="Unsafe Redirect Contact")
        resp_evil_next = client.post(
            f"/favorites/add/{c4.pk}/",
            {"next": "https://evil.example/phish"},
        )
        assert resp_evil_next.status_code == 302
        assert resp_evil_next.url == "/favorites/"

        # HTMX POST with custom priority=2
        resp_htmx = client.post(
            f"/favorites/add/{c2.pk}/",
            {"priority": "2", "next": "/contacts/?sort=name_asc"},
            HTTP_HX_REQUEST="true",
        )
        assert resp_htmx.status_code == 200
        template_names = [t.name for t in resp_htmx.templates if t.name]
        assert "contacts/partials/favorite_toggle_button.html" in template_names
        assert f"/favorites/remove/{c2.pk}/".encode() in resp_htmx.content
        assert b'name="next" value="/contacts/?sort=name_asc"' in resp_htmx.content
        assert f"/favorites/add/{c2.pk}/".encode() not in resp_htmx.content
        item2 = FavoriteItem.objects.get(favorite_list=user.contact_book.favorite_list, contact=c2)
        assert item2.priority == 2

    def test_duplicate_invalid_priority_and_cross_tenant_errors(
        self, authenticated_client, user_factory
    ):
        from apps.favorites.models import FavoriteItem

        client, user = authenticated_client(username="fav_err", email="faverr@example.com")
        other = user_factory(username="fav_victim", email="favvictim@example.com")

        own_contact = _create_contact(user, full_name="Own Contact")
        other_contact = _create_contact(other, full_name="Other Contact")
        _add_favorite(user, own_contact, priority=3)

        # Duplicate favorite -> 400 ERR_FAVORITE_ALREADY_EXISTS
        dup_resp = client.post(f"/favorites/add/{own_contact.pk}/")
        assert dup_resp.status_code == 400
        assert b"This contact is already in your favorites list." in dup_resp.content
        assert (
            FavoriteItem.objects.filter(
                favorite_list=user.contact_book.favorite_list,
                contact=own_contact,
            ).count()
            == 1
        )

        # Out-of-range / non-integer priority -> 400 ERR_FAVORITE_INVALID_PRIORITY
        new_contact = _create_contact(user, full_name="New Contact")
        for bad_priority in ("0", "11", "-3", "high"):
            bad_resp = client.post(
                f"/favorites/add/{new_contact.pk}/",
                {"priority": bad_priority},
            )
            assert bad_resp.status_code == 400
            assert b"Priority must be an integer between 1 and 10." in bad_resp.content
        assert not FavoriteItem.objects.filter(contact=new_contact).exists()

        # Cross-tenant and missing contact -> 404
        assert client.post(f"/favorites/add/{other_contact.pk}/").status_code == 404
        assert client.post("/favorites/add/999999/").status_code == 404


@pytest.mark.django_db
class TestFavoriteRemoveContract:
    """Contract tests for POST /favorites/remove/<int:contact_id>/ (favorite-contracts.md 2.3)."""

    def test_remove_requires_auth_and_post(self, client, authenticated_client):
        anon_resp = client.post("/favorites/remove/1/")
        assert anon_resp.status_code == 302
        assert anon_resp.url.startswith("/accounts/login/")

        auth_client, user = authenticated_client(username="fav_rem_m", email="favremm@example.com")
        contact = _create_contact(user)
        assert auth_client.get(f"/favorites/remove/{contact.pk}/").status_code == 405

    def test_standard_and_htmx_remove_preserves_base_contact(
        self, authenticated_client, user_factory
    ):
        from apps.contacts.models import Contact
        from apps.favorites.models import FavoriteItem

        client, user = authenticated_client(username="fav_rem", email="favrem@example.com")
        other = user_factory(username="fav_rem_other", email="favremother@example.com")

        c1 = _create_contact(user, full_name="Keep Base Contact 1")
        c2 = _create_contact(user, full_name="Keep Base Contact 2")
        c_not_fav = _create_contact(user, full_name="Not Favorited")
        foreign_fav_contact = _create_contact(other, full_name="Foreign Fav")

        _add_favorite(user, c1)
        _add_favorite(user, c2)
        _add_favorite(other, foreign_fav_contact)

        # Standard POST removal
        resp_std = client.post(f"/favorites/remove/{c1.pk}/")
        assert resp_std.status_code == 302
        assert resp_std.url == "/favorites/"
        msgs = [str(m) for m in get_messages(resp_std.wsgi_request)]
        assert "Contact removed from favorites." in msgs
        assert not FavoriteItem.objects.filter(contact=c1).exists()
        assert Contact.objects.filter(pk=c1.pk).exists()

        # HTMX toggle removal (without explicit next does not bake /favorites/remove/ into next)
        resp_htmx = client.post(f"/favorites/remove/{c2.pk}/", HTTP_HX_REQUEST="true")
        assert resp_htmx.status_code == 200
        template_names = [t.name for t in resp_htmx.templates if t.name]
        assert "contacts/partials/favorite_toggle_button.html" in template_names
        assert f"/favorites/add/{c2.pk}/".encode() in resp_htmx.content
        assert f"/favorites/remove/{c2.pk}/".encode() not in resp_htmx.content
        assert not FavoriteItem.objects.filter(contact=c2).exists()
        assert Contact.objects.filter(pk=c2.pk).exists()

        # HTMX row removal mode when another favorite still remains -> no HX-Refresh
        _add_favorite(user, c1)
        _add_favorite(user, c2)
        resp_row_partial = client.post(
            f"/favorites/remove/{c1.pk}/",
            {"mode": "row"},
            HTTP_HX_REQUEST="true",
        )
        assert resp_row_partial.status_code == 200
        assert resp_row_partial.content == b""
        assert resp_row_partial["HX-Trigger"] == "favoriteRemoved"
        assert "HX-Refresh" not in resp_row_partial.headers

        # HTMX row removal mode removing the LAST favorite -> sets HX-Refresh: true
        resp_row = client.post(
            f"/favorites/remove/{c2.pk}/",
            {"mode": "row"},
            HTTP_HX_REQUEST="true",
        )
        assert resp_row.status_code == 200
        assert resp_row.content == b""
        assert resp_row["HX-Trigger"] == "favoriteRemoved"
        assert resp_row["HX-Refresh"] == "true"
        assert not FavoriteItem.objects.filter(contact=c2).exists()

        # Not in favorites or cross-tenant -> 404
        assert client.post(f"/favorites/remove/{c_not_fav.pk}/").status_code == 404
        assert client.post(f"/favorites/remove/{foreign_fav_contact.pk}/").status_code == 404
        assert FavoriteItem.objects.filter(contact=foreign_fav_contact).exists()


@pytest.mark.django_db
class TestFavoritePriorityUpdateContract:
    """Contract tests for POST /favorites/<int:item_id>/priority/ (favorite-contracts.md 2.4)."""

    def test_priority_update_auth_htmx_standard_validation_and_scoping(
        self, client, authenticated_client, user_factory
    ):
        anon_resp = client.post("/favorites/1/priority/", {"priority": "2"})
        assert anon_resp.status_code == 302
        assert anon_resp.url.startswith("/accounts/login/")

        auth_client, owner = authenticated_client(username="fav_prio", email="favprio@example.com")
        other = user_factory(username="fav_prio_other", email="favprioother@example.com")

        c_own = _create_contact(owner, full_name="Priority Contact")
        c_other = _create_contact(other, full_name="Other Contact")
        own_item = _add_favorite(owner, c_own, priority=5)
        other_item = _add_favorite(other, c_other, priority=5)

        assert auth_client.get(f"/favorites/{own_item.pk}/priority/").status_code == 405

        # Standard POST update
        resp_std = auth_client.post(f"/favorites/{own_item.pk}/priority/", {"priority": "1"})
        assert resp_std.status_code == 302
        assert resp_std.url == "/favorites/"
        own_item.refresh_from_db()
        assert own_item.priority == 1

        # HTMX POST update
        resp_htmx = auth_client.post(
            f"/favorites/{own_item.pk}/priority/",
            {"priority": "10"},
            HTTP_HX_REQUEST="true",
        )
        assert resp_htmx.status_code == 200
        template_names = [t.name for t in resp_htmx.templates if t.name]
        assert "favorites/partials/priority_badge.html" in template_names
        assert b"10" in resp_htmx.content
        own_item.refresh_from_db()
        assert own_item.priority == 10

        # Out-of-range / invalid priority -> 400
        for bad_val in ("0", "11", "bad", ""):
            bad_resp = auth_client.post(
                f"/favorites/{own_item.pk}/priority/",
                {"priority": bad_val},
            )
            assert bad_resp.status_code == 400
        own_item.refresh_from_db()
        assert own_item.priority == 10

        # Cross-tenant or missing item -> 404
        assert (
            auth_client.post(f"/favorites/{other_item.pk}/priority/", {"priority": "2"}).status_code
            == 404
        )
        assert auth_client.post("/favorites/999999/priority/", {"priority": "2"}).status_code == 404
        other_item.refresh_from_db()
        assert other_item.priority == 5


@pytest.mark.django_db
class TestContactInteractContract:
    """Contract tests for POST /contacts/<int:pk>/interact/ (favorite-contracts.md 2.5)."""

    def test_interact_auth_json_increment_and_cross_tenant_404(
        self, client, authenticated_client, user_factory
    ):
        anon_resp = client.post("/contacts/1/interact/")
        assert anon_resp.status_code == 302
        assert anon_resp.url.startswith("/accounts/login/")

        auth_client, owner = authenticated_client(
            username="inter_own", email="interown@example.com"
        )
        other = user_factory(username="inter_other", email="interother@example.com")

        own_contact = _create_contact(owner, full_name="Call Me")
        other_contact = _create_contact(other, full_name="Foreign Call")
        assert own_contact.interaction_count == 0
        assert own_contact.last_contacted_at is None

        assert auth_client.get(f"/contacts/{own_contact.pk}/interact/").status_code == 405

        resp1 = auth_client.post(f"/contacts/{own_contact.pk}/interact/")
        assert resp1.status_code == 200
        assert resp1.json() == {"status": "ok", "interaction_count": 1}

        own_contact.refresh_from_db()
        first_ts = own_contact.last_contacted_at
        assert own_contact.interaction_count == 1
        assert first_ts is not None

        resp2 = auth_client.post(f"/contacts/{own_contact.pk}/interact/")
        assert resp2.status_code == 200
        assert resp2.json() == {"status": "ok", "interaction_count": 2}

        own_contact.refresh_from_db()
        assert own_contact.interaction_count == 2
        assert own_contact.last_contacted_at >= first_ts

        # Cross-tenant / missing -> 404
        assert auth_client.post(f"/contacts/{other_contact.pk}/interact/").status_code == 404
        assert auth_client.post("/contacts/999999/interact/").status_code == 404
        other_contact.refresh_from_db()
        assert other_contact.interaction_count == 0
