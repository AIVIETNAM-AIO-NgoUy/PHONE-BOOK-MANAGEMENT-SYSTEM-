"""Automated search latency benchmark script for NFR-002 (< 2s) and SC-002 (< 50ms)."""

import argparse
import os
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.test import Client  # noqa: E402

from apps.accounts.models import CustomUser  # noqa: E402
from apps.contacts.models import Contact, ContactBook  # noqa: E402
from apps.contacts.services import SearchOptimizationService  # noqa: E402
from apps.favorites.models import FavoriteList  # noqa: E402

BENCHMARK_QUERIES = ("Smith", "090", "example", "John")
NFR_002_MAX_SECONDS = 2.0
SC_002_TARGET_MS = 50.0


def _ensure_dataset(
    *,
    username: str,
    password: str,
    target_count: int,
) -> tuple[CustomUser, ContactBook, bool]:
    """Ensure the benchmark user exists and holds at least target_count contacts."""
    user = CustomUser.objects.filter(username__iexact=username).first()
    seeded_by_script = False

    if user is None:
        call_command(
            "seed_contacts",
            user=username,
            password=password,
            count=target_count,
        )
        user = CustomUser.objects.get(username__iexact=username)
        seeded_by_script = True
    else:
        book, _ = ContactBook.objects.get_or_create(user=user)
        FavoriteList.objects.get_or_create(book=book)
        existing_count = Contact.objects.filter(book=book).count()
        if existing_count < target_count:
            call_command(
                "seed_contacts",
                user=username,
                password=password,
                count=target_count,
                reset=True,
            )
            seeded_by_script = True

    book, _ = ContactBook.objects.get_or_create(user=user)
    return user, book, seeded_by_script


def _benchmark_service(book: ContactBook, queries: tuple[str, ...], iterations: int) -> bool:
    """Measure SearchOptimizationService latency across substring queries."""
    print("\n=== Service Benchmark: SearchOptimizationService.search_contacts ===")
    print(
        f"{'Query':<12} {'Matches':>10} {'Min (ms)':>10} "
        f"{'Avg (ms)':>10} {'Max (ms)':>10}  SC-002"
    )
    all_sc002_met = True

    # Warm up connection/query planner once before timing.
    _ = SearchOptimizationService.search_contacts(book=book, query=queries[0]).count()

    for query in queries:
        latencies_ms: list[float] = []
        match_count = 0

        for _ in range(iterations):
            start = time.perf_counter()
            qs = SearchOptimizationService.search_contacts(book=book, query=query)
            match_count = qs.count()
            _ = list(qs[:20])
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies_ms.append(elapsed_ms)

        min_ms = min(latencies_ms)
        avg_ms = statistics.mean(latencies_ms)
        max_ms = max(latencies_ms)

        if max_ms >= NFR_002_MAX_SECONDS * 1000.0:
            raise AssertionError(
                f"NFR-002 violated for service query '{query}': max {max_ms:.2f} ms >= 2000.0 ms"
            )

        sc002_ok = avg_ms < SC_002_TARGET_MS
        if not sc002_ok:
            all_sc002_met = False
        sc002_label = "PASS (<50ms)" if sc002_ok else "WARN (>=50ms)"
        print(
            f"{query:<12} {match_count:>10} {min_ms:>10.2f} {avg_ms:>10.2f} "
            f"{max_ms:>10.2f}  {sc002_label}"
        )

    return all_sc002_met


def _benchmark_http(user: CustomUser, queries: tuple[str, ...], iterations: int) -> None:
    """Measure Django HTTP GET /contacts/search/?q=... latency using test Client."""
    print("\n=== HTTP Benchmark: GET /contacts/search/?q=... ===")
    print(
        f"{'Query':<12} {'Status':>8} {'Min (ms)':>10} "
        f"{'Avg (ms)':>10} {'Max (ms)':>10}  NFR-002"
    )

    client = Client(HTTP_HOST="localhost")
    client.force_login(user)

    # Warm up view/template cache once before timing.
    warmup = client.get("/contacts/search/", {"q": queries[0]})
    if warmup.status_code != 200:
        raise AssertionError(f"Warmup HTTP search failed with status {warmup.status_code}")

    for query in queries:
        latencies_ms: list[float] = []
        status_code = 0

        for _ in range(iterations):
            start = time.perf_counter()
            response = client.get("/contacts/search/", {"q": query})
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            status_code = response.status_code
            if status_code != 200:
                raise AssertionError(
                    f"HTTP search for '{query}' returned unexpected status {status_code}"
                )
            latencies_ms.append(elapsed_ms)

        min_ms = min(latencies_ms)
        avg_ms = statistics.mean(latencies_ms)
        max_ms = max(latencies_ms)

        if max_ms >= NFR_002_MAX_SECONDS * 1000.0:
            raise AssertionError(
                f"NFR-002 violated for HTTP query '{query}': max {max_ms:.2f} ms >= 2000.0 ms"
            )

        print(
            f"{query:<12} {status_code:>8} {min_ms:>10.2f} {avg_ms:>10.2f} "
            f"{max_ms:>10.2f}  PASS (<2.0s)"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark PhoneBook contact search latency.")
    parser.add_argument("--user", default="demo_user", help="Target username (default: demo_user).")
    parser.add_argument(
        "--password",
        default="DemoUser2026!",
        help="Password if target user needs to be created.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10000,
        help="Minimum contact count required before benchmarking (default: 10000).",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=5,
        help="Timed runs per query (default: 5).",
    )
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="Keep synthetic contacts seeded during this run.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    user, book, seeded_by_script = _ensure_dataset(
        username=args.user,
        password=args.password,
        target_count=args.count,
    )
    total_contacts = Contact.objects.filter(book=book).count()
    print(f"Benchmarking search on user='{user.username}' with {total_contacts} contacts...")

    try:
        sc002_ok = _benchmark_service(book, BENCHMARK_QUERIES, args.iterations)
        _benchmark_http(user, BENCHMARK_QUERIES, args.iterations)
    finally:
        if seeded_by_script and not args.keep_data:
            deleted, _ = Contact.objects.filter(book=book).delete()
            print(f"\nCleaned up {deleted} benchmark objects (pass --keep-data to retain).")

    print(
        f"\nSummary: NFR-002 (< 2000 ms) PASSED. "
        f"SC-002 (< 50 ms service avg) {'PASSED' if sc002_ok else 'EXCEEDED TARGET'}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
