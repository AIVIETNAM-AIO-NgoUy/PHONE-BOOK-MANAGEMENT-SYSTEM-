"""Management command to seed synthetic contacts and phone numbers for benchmarking."""

import random
import time
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.contacts.models import Contact, ContactBook, PhoneNumber
from apps.contacts.services import SearchOptimizationService
from apps.favorites.models import FavoriteList

FIRST_NAMES = (
    "Alice",
    "Bob",
    "Charlie",
    "David",
    "Emma",
    "Frank",
    "Grace",
    "Hannah",
    "Ivan",
    "John",
    "Katherine",
    "Liam",
    "Mia",
    "Noah",
    "Olivia",
    "Peter",
    "Quinn",
    "Rachel",
    "Sophia",
    "Thomas",
)

LAST_NAMES = (
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Rodriguez",
    "Martinez",
    "Hernandez",
    "Lopez",
    "Gonzalez",
    "Wilson",
    "Anderson",
    "Thomas",
    "Taylor",
    "Moore",
    "Jackson",
    "Martin",
)

STREET_NAMES = (
    "Oak Street",
    "Maple Avenue",
    "Nguyen Hue Boulevard",
    "Le Loi Street",
    "Cedar Lane",
    "Pine Road",
    "Elm Court",
    "Sunset Boulevard",
)

CITIES = (
    "Ho Chi Minh City",
    "Hanoi",
    "Da Nang",
    "San Francisco",
    "Austin",
    "Seattle",
)

PHONE_PREFIXES = ("090", "091", "098", "032", "+8490", "+8491")
PHONE_TYPES = (
    PhoneNumber.PhoneType.MOBILE,
    PhoneNumber.PhoneType.HOME,
    PhoneNumber.PhoneType.WORK,
    PhoneNumber.PhoneType.MAIN,
    PhoneNumber.PhoneType.OTHER,
)


def _get_or_create_target_user(
    username: str,
    password: str,
) -> tuple[CustomUser, ContactBook, bool]:
    """Resolve or create the target user along with ContactBook and FavoriteList."""
    user = CustomUser.objects.filter(username__iexact=username).first()
    created = False
    if user is None:
        user = CustomUser.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password=password,
            full_name=f"{username} Demo",
        )
        created = True

    book, _ = ContactBook.objects.get_or_create(user=user)
    FavoriteList.objects.get_or_create(book=book)
    return user, book, created


def _build_phone_number(rng: random.Random) -> str:
    """Generate a valid normalized phone number between 10 and 12 characters."""
    prefix = rng.choice(PHONE_PREFIXES)
    suffix = f"{rng.randint(0, 9_999_999):07d}"
    return f"{prefix}{suffix}"


class Command(BaseCommand):
    """Seed synthetic contacts and proportional 2.5x phone numbers in batched transactions."""

    help = "Seed synthetic Contact and PhoneNumber records for search and load benchmarking."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--user",
            type=str,
            default="demo_user",
            help="Target username to seed contacts for (default: demo_user).",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="DemoUser2026!",
            help="Password used when creating the target user if it does not exist.",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=10000,
            help="Number of synthetic Contact records to generate (default: 10000).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=2000,
            help="Batch size for bulk_create operations (default: 2000).",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing contacts for the target user before seeding.",
        )

    def handle(self, *args, **options) -> None:
        username = (options["user"] or "").strip()
        password = options["password"]
        count = options["count"]
        batch_size = options["batch_size"]
        reset = options["reset"]

        if not username:
            raise CommandError("--user must be a non-empty username.")
        if count < 0:
            raise CommandError("--count must be >= 0.")
        if batch_size < 1:
            raise CommandError("--batch-size must be >= 1.")

        user, book, created = _get_or_create_target_user(username, password)
        user_status = "Created" if created else "Using existing"
        self.stdout.write(f"{user_status} user '{user.username}' (book_id={book.pk}).")

        if reset:
            deleted_count, _ = Contact.objects.filter(book=book).delete()
            self.stdout.write(
                f"Reset enabled: cleared {deleted_count} existing objects for '{user.username}'."
            )

        rng = random.Random(42)
        now = timezone.now()
        total_contacts_created = 0
        total_phones_created = 0
        start_time = time.perf_counter()

        for batch_start in range(0, count, batch_size):
            batch_end = min(batch_start + batch_size, count)
            contact_batch: list[Contact] = []
            phone_counts: list[int] = []

            for idx in range(batch_start, batch_end):
                first_name = FIRST_NAMES[idx % len(FIRST_NAMES)]
                last_name = LAST_NAMES[(idx // len(FIRST_NAMES)) % len(LAST_NAMES)]
                full_name = f"{first_name} {last_name} #{idx + 1}"
                email = f"{first_name.lower()}.{last_name.lower()}.{idx + 1}@example.com"
                address = f"{rng.randint(10, 999)} {rng.choice(STREET_NAMES)}, {rng.choice(CITIES)}"
                work_address = (
                    f"Suite {rng.randint(100, 900)}, {rng.choice(STREET_NAMES)}, "
                    f"{rng.choice(CITIES)}"
                )
                birthday = date(1965, 1, 1) + timedelta(days=rng.randint(0, 15000))
                interaction_count = rng.randint(0, 50)
                last_contacted_at = (
                    now - timedelta(days=rng.randint(0, 365)) if interaction_count > 0 else None
                )
                notes = (
                    f"Synthetic contact {idx + 1} for performance benchmarking "
                    f"({first_name} {last_name})."
                )[:1000]

                contact_batch.append(
                    Contact(
                        book=book,
                        full_name=full_name,
                        email=email,
                        address=address,
                        work_address=work_address,
                        birthday=birthday,
                        notes=notes,
                        interaction_count=interaction_count,
                        last_contacted_at=last_contacted_at,
                    )
                )
                phone_counts.append(2 if idx % 2 == 0 else 3)

            with transaction.atomic():
                created_contacts = Contact.objects.bulk_create(
                    contact_batch,
                    batch_size=batch_size,
                )
                phone_batch: list[PhoneNumber] = []
                for contact, phone_total in zip(created_contacts, phone_counts):
                    for phone_idx in range(phone_total):
                        is_primary = phone_idx == 0
                        phone_type = (
                            PhoneNumber.PhoneType.MOBILE if is_primary else rng.choice(PHONE_TYPES)
                        )
                        phone_batch.append(
                            PhoneNumber(
                                contact=contact,
                                phone_number=_build_phone_number(rng),
                                phone_type=phone_type,
                                is_primary=is_primary,
                            )
                        )
                PhoneNumber.objects.bulk_create(phone_batch, batch_size=batch_size)

            total_contacts_created += len(created_contacts)
            total_phones_created += len(phone_batch)

        seed_elapsed = time.perf_counter() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {total_contacts_created} contacts and {total_phones_created} "
                f"phone numbers for '{user.username}' in {seed_elapsed:.2f}s."
            )
        )

        verify_start = time.perf_counter()
        smith_qs = SearchOptimizationService.search_contacts(book=book, query="Smith")
        smith_count = smith_qs.count()
        _ = list(smith_qs[:20])
        verify_ms = (time.perf_counter() - verify_start) * 1000.0
        self.stdout.write(
            f"Verification query 'Smith': {smith_count} matches in {verify_ms:.2f} ms."
        )
