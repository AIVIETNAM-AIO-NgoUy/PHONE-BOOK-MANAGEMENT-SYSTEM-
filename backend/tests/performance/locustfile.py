"""Locust load test simulating 80% read / 20% write traffic (NFR-004)."""

import os
import random
import re
import uuid

from locust import HttpUser, between, task

_CSRF_INPUT_RE = re.compile(
    r'<input[^>]*name=["\']csrfmiddlewaretoken["\'][^>]*value=["\']([^"\']+)["\']'
)

SEARCH_TERMS = ("Smith", "090", "example", "John", "Alice")
PHONE_TYPES = ("Mobile", "Home", "Work", "Main", "Other")


class PhoneBookUser(HttpUser):
    """Authenticated user performing 80% read and 20% write operations."""

    wait_time = between(1, 3)

    def _extract_csrf_token(self, html_text: str = "") -> str:
        """Read csrftoken from session cookies or fall back to hidden form input."""
        cookie_token = self.client.cookies.get("csrftoken")
        if cookie_token:
            return cookie_token
        match = _CSRF_INPUT_RE.search(html_text or "")
        return match.group(1) if match else ""

    def _login_user(self, username: str, password: str) -> bool:
        """Attempt login via /accounts/login/ and return True when authenticated."""
        login_get = self.client.get("/accounts/login/", name="/accounts/login/ [GET]")
        csrf_token = self._extract_csrf_token(login_get.text)
        login_post = self.client.post(
            "/accounts/login/",
            data={
                "username_or_email": username,
                "password": password,
                "csrfmiddlewaretoken": csrf_token,
            },
            headers={"X-CSRFToken": csrf_token},
            allow_redirects=False,
            name="/accounts/login/ [POST]",
        )
        location = login_post.headers.get("Location", "")
        if login_post.status_code in (301, 302) and "/contacts" in location:
            # Fetch /contacts/ to capture the rotated csrftoken cookie post-login.
            contacts_resp = self.client.get("/contacts/", name="/contacts/ [post-login]")
            self.csrftoken = self._extract_csrf_token(contacts_resp.text)
            return True
        return False

    def _register_and_login(self) -> None:
        """Register a unique load-test user and sign in."""
        username = f"load_{uuid.uuid4().hex[:10]}"
        password = "LoadUser2026!"

        reg_get = self.client.get("/accounts/register/", name="/accounts/register/ [GET]")
        csrf_token = self._extract_csrf_token(reg_get.text)
        self.client.post(
            "/accounts/register/",
            data={
                "username": username,
                "email": f"{username}@example.com",
                "full_name": f"Load User {username}",
                "password": password,
                "password_confirm": password,
                "csrfmiddlewaretoken": csrf_token,
            },
            headers={"X-CSRFToken": csrf_token},
            name="/accounts/register/ [POST]",
        )
        self._login_user(username, password)

    def on_start(self) -> None:
        """Authenticate on VU startup, falling back to registration if needed."""
        self.csrftoken = ""
        username = os.environ.get("LOCUST_USER", "demo_user")
        password = os.environ.get("LOCUST_PASSWORD", "DemoUser2026!")
        if not self._login_user(username, password):
            self._register_and_login()

    @task(3)
    def browse_contacts(self) -> None:
        """Read task (30%): paginate contact directory."""
        page = random.randint(1, 5)
        self.client.get(f"/contacts/?page={page}", name="/contacts/")

    @task(3)
    def search_contacts_htmx(self) -> None:
        """Read task (30%): live HTMX partial search."""
        query = random.choice(SEARCH_TERMS)
        self.client.get(
            f"/contacts/search/?q={query}",
            headers={"HX-Request": "true"},
            name="/contacts/search/?q=[query]",
        )

    @task(1)
    def view_favorites_priority(self) -> None:
        """Read task (10%): view favorites sorted by priority."""
        self.client.get("/favorites/?sort=priority", name="/favorites/?sort=priority")

    @task(1)
    def view_groups(self) -> None:
        """Read task (10%): view custom contact groups."""
        self.client.get("/groups/", name="/groups/")

    @task(2)
    def create_contact(self) -> None:
        """Write task (20%): create a new contact with a primary phone number."""
        csrf_token = self._extract_csrf_token() or self.csrftoken
        suffix = uuid.uuid4().hex[:8]
        phone_digits = f"090{random.randint(0, 9_999_999):07d}"
        with self.client.post(
            "/contacts/create/",
            data={
                "full_name": f"Load Contact {suffix}",
                "primary_phone": phone_digits,
                "primary_phone_type": random.choice(PHONE_TYPES),
                "csrfmiddlewaretoken": csrf_token,
            },
            headers={"X-CSRFToken": csrf_token},
            catch_response=True,
            name="/contacts/create/",
        ) as response:
            if response.status_code >= 400:
                response.failure(f"Contact creation failed with status {response.status_code}")
            else:
                self.csrftoken = self._extract_csrf_token(response.text) or self.csrftoken
