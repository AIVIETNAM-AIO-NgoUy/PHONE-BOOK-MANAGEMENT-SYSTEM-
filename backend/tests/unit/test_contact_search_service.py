"""Unit tests for SearchOptimizationService and PostgreSQL GIN trigram indexes (T054)."""

import pytest
from django.db import connection, transaction
from django.db.models import Exists, Q

from apps.contacts.models import Contact, PhoneNumber
from apps.contacts.services import SearchOptimizationService


@pytest.mark.django_db
class TestSearchOptimizationServiceUnit:
    """Unit tests for query sanitization, sorting keys, Q construction, and GIN indexes."""

    def test_sanitize_query_trims_whitespace_and_strips_nul_bytes(self):
        assert SearchOptimizationService.sanitize_query(None) == ""
        assert SearchOptimizationService.sanitize_query("") == ""
        assert SearchOptimizationService.sanitize_query("   \t\n  ") == ""
        assert SearchOptimizationService.sanitize_query("  Alice Smith  ") == "Alice Smith"
        assert SearchOptimizationService.sanitize_query("  bob\x00@mail.com  ") == "bob@mail.com"
        assert SearchOptimizationService.sanitize_query("  100% _test\\+  ") == "100% _test\\+"

    def test_resolve_sort_key_and_order_by_with_invalid_fallback(self):
        assert SearchOptimizationService.resolve_sort_key("name_asc") == "name_asc"
        assert SearchOptimizationService.resolve_sort_key("name_desc") == "name_desc"
        assert SearchOptimizationService.resolve_sort_key("recent") == "recent"
        assert SearchOptimizationService.resolve_sort_key("invalid") == "name_asc"
        assert SearchOptimizationService.resolve_sort_key(None) == "name_asc"

        assert SearchOptimizationService.get_order_by("name_asc") == ("full_name", "id")
        assert SearchOptimizationService.get_order_by("name_desc") == ("-full_name", "id")
        assert SearchOptimizationService.get_order_by("recent") == ("-updated_at", "-id")
        assert SearchOptimizationService.get_order_by("bad") == ("full_name", "id")

    def test_build_search_filter_targets_name_email_and_phone_number(self, user_factory):
        q_filter = SearchOptimizationService.build_search_filter("rob")
        assert isinstance(q_filter, Q)
        assert q_filter.connector == Q.OR
        assert ("full_name__ilike", "rob") in q_filter.children
        assert ("email__ilike", "rob") in q_filter.children
        exists_nodes = [child for child in q_filter.children if isinstance(child, Exists)]
        assert len(exists_nodes) == 1

        owner = user_factory(username="sql_chk_u", email="sqlchku@example.com")
        sql = str(
            SearchOptimizationService.search_contacts(book=owner.contact_book, query="rob").query
        )
        assert "ILIKE" in sql
        assert "EXISTS" in sql
        assert "UPPER(" not in sql
        assert "LEFT OUTER JOIN" not in sql
        assert "SELECT DISTINCT" not in sql

    def test_search_contacts_enforces_book_scope_dedup_sorting_and_ec007_safety(
        self, user_factory, django_assert_num_queries
    ):
        owner = user_factory(username="svc_owner", email="svcowner@example.com")
        other = user_factory(username="svc_other", email="svcother@example.com")

        c1 = Contact.objects.create(
            book=owner.contact_book,
            full_name="Alice 100% O'Connor",
            email="alice+work@example.com",
        )
        PhoneNumber.objects.create(
            contact=c1, phone_number="0901112222", phone_type="Mobile", is_primary=True
        )
        PhoneNumber.objects.create(
            contact=c1, phone_number="0901113333", phone_type="Work", is_primary=False
        )

        c2 = Contact.objects.create(
            book=owner.contact_book,
            full_name="Bob_Admin\\Two",
            email="bob@example.com",
        )
        PhoneNumber.objects.create(
            contact=c2, phone_number="0909888777", phone_type="Mobile", is_primary=True
        )

        # Foreign contact that matches all terms must never leak
        foreign = Contact.objects.create(
            book=other.contact_book,
            full_name="Alice Foreign",
            email="alice@foreign.com",
        )
        PhoneNumber.objects.create(
            contact=foreign, phone_number="0901119999", phone_type="Mobile", is_primary=True
        )

        # Distinct multi-phone match
        multi_phone_hits = list(
            SearchOptimizationService.search_contacts(book=owner.contact_book, query="090111")
        )
        assert [c.pk for c in multi_phone_hits] == [c1.pk]

        # Special wildcard characters are literal, not wildcards (EC-007)
        assert [
            c.pk
            for c in SearchOptimizationService.search_contacts(book=owner.contact_book, query=" % ")
        ] == [c1.pk]
        assert [
            c.pk
            for c in SearchOptimizationService.search_contacts(book=owner.contact_book, query=" _ ")
        ] == [c2.pk]
        assert [
            c.pk
            for c in SearchOptimizationService.search_contacts(book=owner.contact_book, query="\\")
        ] == [c2.pk]
        assert [
            c.pk
            for c in SearchOptimizationService.search_contacts(
                book=owner.contact_book, query="alice+work@"
            )
        ] == [c1.pk]

        # Deterministic sorting
        assert [
            c.pk
            for c in SearchOptimizationService.search_contacts(
                book=owner.contact_book, sort_key="name_desc"
            )
        ] == [c2.pk, c1.pk]

        # Prefetches phone_numbers without N+1 queries
        with django_assert_num_queries(2):
            results = list(
                SearchOptimizationService.search_contacts(book=owner.contact_book, query=None)
            )
            _ = [c.primary_phone.phone_number for c in results]

    def test_postgres_trigram_gin_indexes_exist(self):
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE indexname IN (
                    'idx_contacts_fullname_trgm',
                    'idx_contacts_email_trgm',
                    'idx_phonenumber_digits_trgm'
                )
                """)
            rows = dict(cursor.fetchall())

        assert set(rows.keys()) == {
            "idx_contacts_fullname_trgm",
            "idx_contacts_email_trgm",
            "idx_phonenumber_digits_trgm",
        }
        assert "USING gin (full_name gin_trgm_ops)" in rows["idx_contacts_fullname_trgm"]
        assert "USING gin (email gin_trgm_ops)" in rows["idx_contacts_email_trgm"]
        assert "USING gin (phone_number gin_trgm_ops)" in rows["idx_phonenumber_digits_trgm"]

    def test_postgres_explain_uses_pg_trgm_gin_indexes_for_ilike(self, user_factory):
        owner = user_factory(username="gin_u", email="ginu@example.com")
        c = Contact.objects.create(
            book=owner.contact_book,
            full_name="Alexander Graham",
            email="alexander.graham@example.org",
        )
        PhoneNumber.objects.create(
            contact=c,
            phone_number="0908887777",
            phone_type="Mobile",
            is_primary=True,
        )

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL enable_seqscan = off")

            name_plan = Contact.objects.filter(full_name__ilike="Alex").explain()
            email_plan = Contact.objects.filter(email__ilike="graham@").explain()
            phone_plan = PhoneNumber.objects.filter(phone_number__ilike="090888").explain()

        assert "idx_contacts_fullname_trgm" in name_plan
        assert "idx_contacts_email_trgm" in email_plan
        assert "idx_phonenumber_digits_trgm" in phone_plan
