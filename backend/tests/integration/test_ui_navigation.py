"""Integration tests for sliding dual-panel auth card and left sidebar navigation shell."""

import re

import pytest
from django.test import Client

from apps.contacts.models import Contact
from apps.favorites.models import FavoriteItem
from apps.groups.models import Group


@pytest.mark.django_db
class TestGuestAuthLayout:
    """Verify anonymous auth pages render centered sliding dual-panel card without top navbar."""

    def test_login_page_renders_sliding_card_without_top_navbar_or_demo_credentials(
        self, client: Client
    ):
        response = client.get("/accounts/login/")
        assert response.status_code == 200
        html = response.content.decode("utf-8")

        assert 'class="auth-stage"' in html
        assert 'class="auth-card"' in html
        assert "auth-card is-register" not in html
        assert "data-auth-card" in html
        assert 'class="auth-panel auth-panel-login"' in html
        assert 'class="auth-panel auth-panel-register"' in html
        assert 'class="auth-overlay-container"' in html
        assert 'class="auth-overlay"' in html
        assert 'class="auth-banner auth-banner-login"' in html
        assert 'class="auth-banner auth-banner-register"' in html
        assert 'class="guest-shell"' in html
        assert 'class="app-sidebar"' not in html
        assert 'class="navbar"' not in html
        assert 'class="navbar-actions"' not in html
        assert "A@123" not in html
        assert "Demo Credentials" not in html
        assert "styles.css?v=20261116_v1" in html
        assert "app.js?v=20261116_v1" in html

        # Distinct banner copy & no switch controls on the sliding overlay banners
        assert "Welcome back to PhoneBook" in html
        assert "Instant Trigram Search" in html
        assert "Start organizing your network today" in html
        assert "Dedicated Contact Book" in html

        overlay_html = html.split('class="auth-overlay"', 1)[1].split("</main>", 1)[0]
        assert "data-auth-switch" not in overlay_html
        assert "<button" not in overlay_html
        assert "<a " not in overlay_html

        # Footer links handle switching
        assert 'data-auth-switch="register"' in html
        assert 'data-auth-switch="login"' in html

    def test_register_page_renders_is_register_card_with_two_column_form(self, client: Client):
        response = client.get("/accounts/register/")
        assert response.status_code == 200
        html = response.content.decode("utf-8")

        assert 'class="auth-stage"' in html
        assert 'class="auth-card is-register"' in html
        assert 'class="auth-panel auth-panel-login"' in html
        assert 'class="auth-panel auth-panel-register"' in html
        assert 'class="auth-form-grid"' in html
        assert 'class="auth-overlay"' in html
        assert 'class="guest-shell"' in html
        assert 'class="app-sidebar"' not in html
        assert 'class="navbar"' not in html
        assert 'class="navbar-actions"' not in html
        assert "A@123" not in html
        assert "Demo Credentials" not in html
        assert "styles.css?v=20261116_v1" in html
        assert "app.js?v=20261116_v1" in html

        # Register panel active, login panel inert/hidden in SSR
        assert re.search(
            r'data-auth-panel="register"[^>]*aria-hidden="false"',
            html,
        )
        assert re.search(
            r'data-auth-panel="login"[^>]*aria-hidden="true"\s+inert',
            html,
        )


@pytest.mark.django_db
class TestAuthenticatedSidebarShell:
    """Verify authenticated pages render left sidebar navigation and role-scoped links."""

    def test_standard_user_sees_sidebar_links_active_state_and_no_admin_panel(
        self, authenticated_client
    ):
        client, user = authenticated_client(
            username="nav_user",
            email="navuser@example.com",
            full_name="Nav User",
        )

        contacts_resp = client.get("/contacts/")
        assert contacts_resp.status_code == 200
        html = contacts_resp.content.decode("utf-8")

        assert 'class="app-shell"' in html
        assert 'id="app-sidebar"' in html
        assert 'class="app-sidebar"' in html
        assert "data-sidebar-toggle" in html
        assert 'aria-controls="app-sidebar"' in html
        assert "data-sidebar-backdrop" in html

        for label in ("Contacts", "Favorites", "Groups", "Profile", "Change Password", "Logout"):
            assert label in html

        assert "@nav_user" in html
        assert "Nav User" in html
        assert "Admin Panel" not in html
        assert "/admin-panel/" not in html
        assert "Dashboard" not in html
        assert "User Management" not in html
        assert 'href="/contacts/" class="brand-link"' in html

        # Contacts link is active on /contacts/
        assert re.search(
            r'href="/contacts/"[^>]*class="sidebar-link is-active"',
            html,
        )

        # Profile link becomes active on /accounts/profile/
        profile_resp = client.get("/accounts/profile/")
        assert profile_resp.status_code == 200
        profile_html = profile_resp.content.decode("utf-8")
        assert re.search(
            r'href="/accounts/profile/"[^>]*class="sidebar-link is-active"',
            profile_html,
        )

        # Change Password link becomes active on /accounts/password/change/
        pw_resp = client.get("/accounts/password/change/")
        assert pw_resp.status_code == 200
        pw_html = pw_resp.content.decode("utf-8")
        assert re.search(
            r'href="/accounts/password/change/"[^>]*class="sidebar-link is-active"',
            pw_html,
        )

    def test_admin_user_sees_admin_panel_link_and_badge_in_sidebar(self, user_factory):
        admin_user = user_factory(
            username="nav_admin",
            email="navadmin@example.com",
            full_name="Nav Admin",
            role="Admin",
            is_staff=True,
            is_superuser=True,
        )
        admin_client = Client()
        admin_client.force_login(admin_user)

        admin_resp = admin_client.get("/admin-panel/")
        assert admin_resp.status_code == 200
        admin_html = admin_resp.content.decode("utf-8")
        assert 'href="/admin-panel/" class="brand-link"' in admin_html
        assert "Dashboard" in admin_html
        assert "User Management" in admin_html
        assert ">Admin<" in admin_html

        # Personal contacts workspace items hidden from admin sidebar
        assert 'href="/contacts/"' not in admin_html
        assert 'href="/favorites/"' not in admin_html
        assert 'href="/groups/"' not in admin_html

        # Dashboard link is active on /admin-panel/
        assert re.search(
            r'href="/admin-panel/"[^>]*class="sidebar-link is-active"',
            admin_html,
        )

        # User Management link becomes active on /admin-panel/users/
        users_resp = admin_client.get("/admin-panel/users/")
        assert users_resp.status_code == 200
        users_html = users_resp.content.decode("utf-8")
        assert re.search(
            r'href="/admin-panel/users/"[^>]*class="sidebar-link is-active"',
            users_html,
        )


@pytest.mark.django_db
class TestResponsiveLayoutMarkup:
    """Verify responsive table card markup, hidden secondary columns, and profile layout."""

    def test_user_tables_and_profile_render_responsive_markup(self, authenticated_client):
        client, user = authenticated_client(
            username="resp_user",
            email="respuser@example.com",
            full_name="Responsive User",
        )
        contact = Contact.objects.create(
            book=user.contact_book,
            full_name="Alice Responsive",
            email="alice@example.com",
        )
        FavoriteItem.objects.create(
            favorite_list=user.contact_book.favorite_list,
            contact=contact,
            priority=2,
        )
        Group.objects.create(
            book=user.contact_book,
            group_name="Engineering",
            description="Platform engineering team",
        )

        # Contacts list
        contacts_resp = client.get("/contacts/")
        assert contacts_resp.status_code == 200
        contacts_html = contacts_resp.content.decode("utf-8")
        assert '<table class="table table-responsive-cards"' in contacts_html
        for label in ("Name", "Primary Phone", "Email", "Actions"):
            assert f'data-label="{label}"' in contacts_html

        # Favorites list
        favorites_resp = client.get("/favorites/")
        assert favorites_resp.status_code == 200
        favorites_html = favorites_resp.content.decode("utf-8")
        assert '<table class="table table-responsive-cards"' in favorites_html
        for label in ("Contact", "Primary Phone", "Priority", "Interactions", "Actions"):
            assert f'data-label="{label}"' in favorites_html

        # Groups list
        groups_resp = client.get("/groups/")
        assert groups_resp.status_code == 200
        groups_html = groups_resp.content.decode("utf-8")
        assert '<table class="table table-responsive-cards"' in groups_html
        for label in ("Group Name", "Description", "Members", "Actions"):
            assert f'data-label="{label}"' in groups_html

        # Profile card uses .profile-card-layout without legacy min-width: 220px inline style
        profile_resp = client.get("/accounts/profile/")
        assert profile_resp.status_code == 200
        profile_html = profile_resp.content.decode("utf-8")
        assert 'class="profile-card-layout"' in profile_html
        assert "min-width: 220px" not in profile_html

    def test_admin_user_list_renders_responsive_cards_and_col_hide_md(self, user_factory):
        admin_user = user_factory(
            username="resp_admin",
            email="respadmin@example.com",
            full_name="Responsive Admin",
            role="Admin",
            is_staff=True,
            is_superuser=True,
        )
        admin_client = Client()
        admin_client.force_login(admin_user)

        users_resp = admin_client.get("/admin-panel/users/")
        assert users_resp.status_code == 200
        users_html = users_resp.content.decode("utf-8")

        assert '<table class="table table-responsive-cards"' in users_html
        for label in (
            "Username",
            "Email",
            "Full Name",
            "Role",
            "Status",
            "Registered",
            "Last Login",
            "Actions",
        ):
            assert f'data-label="{label}"' in users_html

        assert '<th class="col-hide-md">Registered</th>' in users_html
        assert '<th class="col-hide-md">Last Login</th>' in users_html
        assert re.search(
            r'<td[^>]*class="[^"]*\bcol-hide-md\b[^"]*"[^>]*data-label="Registered"',
            users_html,
        )
        assert re.search(
            r'<td[^>]*class="[^"]*\bcol-hide-md\b[^"]*"[^>]*data-label="Last Login"',
            users_html,
        )
