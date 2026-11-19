"""Unit tests for AuditLog, AccountGovernanceService, @admin_required, and session flush (T099)."""

import logging
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory
from django.utils import timezone

from apps.accounts.services import flush_user_sessions
from apps.admin_panel import services as admin_services
from apps.admin_panel.models import AuditLog
from apps.core.decorators import admin_required


def _create_session_for_user(user) -> str:
    store = SessionStore()
    store["_auth_user_id"] = str(user.pk)
    store["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
    store.create()
    return store.session_key


@pytest.mark.django_db
class TestAuditLogModel:
    """Unit tests for AuditLog persistence, ordering, and SET_NULL snapshot invariant."""

    def test_audit_log_preserves_snapshots_when_actor_and_target_deleted(self, user_factory):
        actor = user_factory(username="deleted_admin", email="deladmin@example.com", role="Admin")
        target = user_factory(username="deleted_target", email="deltarget@example.com")

        log = AuditLog.objects.create(
            actor=actor,
            actor_username_snapshot=actor.username,
            target_user=target,
            target_username_snapshot=target.username,
            action=AuditLog.Action.ACCOUNT_LOCKED,
            details={"reason": "Compliance retention test"},
            ip_address="192.0.2.10",
            user_agent="pytest-agent/1.0",
        )

        actor.delete()
        target.delete()

        log.refresh_from_db()
        assert log.actor is None
        assert log.target_user is None
        assert log.actor_username_snapshot == "deleted_admin"
        assert log.target_username_snapshot == "deleted_target"
        assert log.details == {"reason": "Compliance retention test"}

    def test_audit_log_default_ordering_is_newest_first(self, user_factory):
        actor = user_factory(username="ord_admin", email="ordadmin@example.com", role="Admin")
        target = user_factory(username="ord_target", email="ordtarget@example.com")

        first = AuditLog.objects.create(
            actor=actor,
            actor_username_snapshot=actor.username,
            target_user=target,
            target_username_snapshot=target.username,
            action=AuditLog.Action.ACCOUNT_LOCKED,
        )
        second = AuditLog.objects.create(
            actor=actor,
            actor_username_snapshot=actor.username,
            target_user=target,
            target_username_snapshot=target.username,
            action=AuditLog.Action.ACCOUNT_UNLOCKED,
        )
        AuditLog.objects.filter(pk=first.pk).update(timestamp=timezone.now() - timedelta(minutes=5))

        logs = list(AuditLog.objects.filter(pk__in=[first.pk, second.pk]))
        assert [entry.pk for entry in logs] == [second.pk, first.pk]


@pytest.mark.django_db
class TestAccountGovernanceService:
    """Unit tests for AccountGovernanceService lock/unlock and session eviction."""

    def test_lock_user_account_updates_status_flushes_sessions_and_logs(self, user_factory):
        admin_user = user_factory(username="svc_admin", email="svcadmin@example.com", role="Admin")
        target = user_factory(username="svc_target", email="svctarget@example.com")
        other = user_factory(username="svc_other", email="svcother@example.com")

        target_key_1 = _create_session_for_user(target)
        target_key_2 = _create_session_for_user(target)
        other_key = _create_session_for_user(other)

        long_ua = "Mozilla/5.0 " + ("X" * 300)
        locked = admin_services.AccountGovernanceService.lock_user_account(
            actor=admin_user,
            target_user_id=target.pk,
            reason="  Policy breach  ",
            ip_address="203.0.113.5",
            user_agent=long_ua,
        )

        assert locked.account_status == "Locked"
        assert not Session.objects.filter(session_key__in=[target_key_1, target_key_2]).exists()
        assert Session.objects.filter(session_key=other_key).exists()

        log = AuditLog.objects.get(target_user=target, action=AuditLog.Action.ACCOUNT_LOCKED)
        assert log.actor == admin_user
        assert log.actor_username_snapshot == "svc_admin"
        assert log.target_username_snapshot == "svc_target"
        assert log.details == {"reason": "Policy breach"}
        assert log.ip_address == "203.0.113.5"
        assert len(log.user_agent) == 255

    def test_lock_prevents_self_lock_and_duplicate_lock(self, user_factory):
        admin_user = user_factory(
            username="self_lock_admin", email="selflock@example.com", role="Admin"
        )
        already_locked = user_factory(
            username="already_locked",
            email="alreadylocked@example.com",
            account_status="Locked",
        )

        with pytest.raises(admin_services.SelfLockError) as self_exc:
            admin_services.AccountGovernanceService.lock_user_account(
                actor=admin_user,
                target_user_id=admin_user.pk,
            )
        assert self_exc.value.code == "ERR_ADMIN_SELF_LOCK"
        assert self_exc.value.message == "You cannot lock your own administrative account."
        admin_user.refresh_from_db()
        assert admin_user.account_status == "Active"

        with pytest.raises(admin_services.InvalidAccountStateError) as dup_exc:
            admin_services.AccountGovernanceService.lock_user_account(
                actor=admin_user,
                target_user_id=already_locked.pk,
            )
        assert dup_exc.value.code == "ERR_ACCOUNT_ALREADY_LOCKED"
        assert dup_exc.value.message == "This account is already in Locked status."

        assert AuditLog.objects.count() == 0

    def test_lock_missing_user_raises_does_not_exist(self, user_factory):
        admin_user = user_factory(
            username="miss_admin", email="missadmin@example.com", role="Admin"
        )
        user_model = get_user_model()

        with pytest.raises(user_model.DoesNotExist):
            admin_services.AccountGovernanceService.lock_user_account(
                actor=admin_user, target_user_id=999999
            )

    def test_unlock_user_account_restores_active_and_rejects_already_active(self, user_factory):
        admin_user = user_factory(username="unl_admin", email="unladmin@example.com", role="Admin")
        locked = user_factory(
            username="unl_target",
            email="unltarget@example.com",
            account_status="Locked",
        )

        restored = admin_services.AccountGovernanceService.unlock_user_account(
            actor=admin_user,
            target_user_id=locked.pk,
            reason="Verified identity",
            ip_address="198.51.100.7",
        )
        assert restored.account_status == "Active"

        log = AuditLog.objects.get(target_user=locked, action=AuditLog.Action.ACCOUNT_UNLOCKED)
        assert log.details == {"reason": "Verified identity"}
        assert log.ip_address == "198.51.100.7"

        with pytest.raises(admin_services.InvalidAccountStateError) as active_exc:
            admin_services.AccountGovernanceService.unlock_user_account(
                actor=admin_user,
                target_user_id=locked.pk,
            )
        assert active_exc.value.code == "ERR_ACCOUNT_ALREADY_ACTIVE"
        assert active_exc.value.message == "Account is already active."

    def test_create_user_account_creates_user_containers_and_audit_log(self, user_factory):
        from apps.contacts.models import ContactBook
        from apps.favorites.models import FavoriteList

        admin_user = user_factory(
            username="creator_admin", email="creator@example.com", role="Admin"
        )

        created_user = admin_services.AccountGovernanceService.create_user_account(
            actor=admin_user,
            username="new_citizen",
            email="citizen@example.com",
            full_name="New Citizen",
            password="StrongPass123!",
            role="User",
            account_status="Active",
            ip_address="192.0.2.55",
            user_agent="pytest-client",
        )

        assert created_user.username == "new_citizen"
        assert created_user.email == "citizen@example.com"
        assert created_user.full_name == "New Citizen"
        assert created_user.role == "User"
        assert created_user.is_staff is False
        assert created_user.check_password("StrongPass123!")

        assert ContactBook.objects.filter(user=created_user).exists()
        book = ContactBook.objects.get(user=created_user)
        assert FavoriteList.objects.filter(book=book).exists()

        log = AuditLog.objects.get(target_user=created_user, action=AuditLog.Action.USER_CREATED)
        assert log.actor == admin_user
        assert log.actor_username_snapshot == "creator_admin"
        assert log.target_username_snapshot == "new_citizen"
        assert log.details["role"] == "User"
        assert log.ip_address == "192.0.2.55"

        # Create admin user sets is_staff=True
        admin_created = admin_services.AccountGovernanceService.create_user_account(
            actor=admin_user,
            username="second_admin",
            email="secondadmin@example.com",
            full_name="Second Admin",
            password="AdminPass123!",
            role="Admin",
            account_status="Active",
        )
        assert admin_created.role == "Admin"
        assert admin_created.is_staff is True

    def test_update_user_account_updates_fields_and_protects_self(self, user_factory):
        admin_user = user_factory(username="editor_admin", email="editor@example.com", role="Admin")
        target = user_factory(
            username="edit_victim", email="victim@example.com", full_name="Victim"
        )

        session_key = _create_session_for_user(target)
        assert Session.objects.filter(session_key=session_key).exists()

        updated = admin_services.AccountGovernanceService.update_user_account(
            actor=admin_user,
            target_user_id=target.pk,
            full_name="Updated Name",
            email="updatedvictim@example.com",
            role="Admin",
            account_status="Locked",
            new_password="NewSecretPass123!",
        )

        assert updated.full_name == "Updated Name"
        assert updated.email == "updatedvictim@example.com"
        assert updated.role == "Admin"
        assert updated.is_staff is True
        assert updated.account_status == "Locked"
        assert updated.check_password("NewSecretPass123!")

        # Session was evicted because status transitioned to Locked
        assert not Session.objects.filter(session_key=session_key).exists()

        log = AuditLog.objects.get(target_user=target, action=AuditLog.Action.USER_UPDATED)
        assert log.actor == admin_user
        assert "full_name" in log.details
        assert "password" in log.details

        # Self-demotion protection
        with pytest.raises(admin_services.SelfDemoteError) as demote_exc:
            admin_services.AccountGovernanceService.update_user_account(
                actor=admin_user,
                target_user_id=admin_user.pk,
                role="User",
            )
        assert demote_exc.value.code == "ERR_ADMIN_SELF_DEMOTE"

        # Self-lockout protection
        with pytest.raises(admin_services.SelfLockError) as lock_exc:
            admin_services.AccountGovernanceService.update_user_account(
                actor=admin_user,
                target_user_id=admin_user.pk,
                account_status="Locked",
            )
        assert lock_exc.value.code == "ERR_ADMIN_SELF_LOCK"

    def test_delete_user_account_requires_confirm_protects_self_evicts_sessions_and_cascades(
        self, user_factory
    ):
        from apps.contacts.models import Contact, PhoneNumber

        admin_user = user_factory(username="del_admin", email="deladmin@example.com", role="Admin")
        target = user_factory(username="del_target", email="deltarget@example.com")

        contact = Contact.objects.create(
            book=target.contact_book, full_name="Target Contact", email="c@test.com"
        )
        phone = PhoneNumber.objects.create(
            contact=contact, phone_number="0988776655", phone_type="Mobile", is_primary=True
        )

        target_session = _create_session_for_user(target)
        assert Session.objects.filter(session_key=target_session).exists()

        # Missing confirmation safeguard
        with pytest.raises(admin_services.ConfirmationRequiredError) as conf_exc:
            admin_services.AccountGovernanceService.delete_user_account(
                actor=admin_user,
                target_user_id=target.pk,
                confirm=False,
            )
        assert conf_exc.value.code == "ERR_CONFIRMATION_REQUIRED"

        # Self-delete protection
        with pytest.raises(admin_services.SelfDeleteError) as self_del_exc:
            admin_services.AccountGovernanceService.delete_user_account(
                actor=admin_user,
                target_user_id=admin_user.pk,
                confirm=True,
            )
        assert self_del_exc.value.code == "ERR_ADMIN_SELF_DELETE"

        # Successful deletion
        target_id = target.pk
        admin_services.AccountGovernanceService.delete_user_account(
            actor=admin_user,
            target_user_id=target_id,
            confirm=True,
            ip_address="192.0.2.99",
        )

        # Target user deleted from DB
        user_model = get_user_model()
        assert not user_model.objects.filter(pk=target_id).exists()

        # Session evicted
        assert not Session.objects.filter(session_key=target_session).exists()

        # Cascading deletion of contacts & phone numbers
        assert not Contact.objects.filter(pk=contact.pk).exists()
        assert not PhoneNumber.objects.filter(pk=phone.pk).exists()

        # AuditLog written with target_user=None and target_username_snapshot preserved
        log = AuditLog.objects.get(action=AuditLog.Action.USER_DELETED)
        assert log.target_user is None
        assert log.target_username_snapshot == "del_target"
        assert log.actor == admin_user
        assert log.actor_username_snapshot == "del_admin"
        assert log.details["deleted_user_id"] == target_id


@pytest.mark.django_db
class TestFlushUserSessionsUtility:
    """Unit tests for flush_user_sessions selective session eviction."""

    def test_flush_user_sessions_supports_exclude_session_key(self, user_factory):
        user = user_factory(username="flush_u", email="flushu@example.com")
        other = user_factory(username="flush_o", email="flusho@example.com")

        keep_key = _create_session_for_user(user)
        evict_key = _create_session_for_user(user)
        other_key = _create_session_for_user(other)

        deleted = flush_user_sessions(user, exclude_session_key=keep_key)
        assert deleted == 1
        assert Session.objects.filter(session_key=keep_key).exists()
        assert not Session.objects.filter(session_key=evict_key).exists()
        assert Session.objects.filter(session_key=other_key).exists()


class TestAdminRequiredDecorator:
    """Unit tests for @admin_required RBAC decorator."""

    def test_allows_admin_and_staff_and_blocks_anonymous_and_standard_users(
        self, mock_user_factory, caplog
    ):
        rf = RequestFactory()

        @admin_required
        def protected_view(request):
            return HttpResponse("ok", status=200)

        anon_req = rf.get("/admin-panel/")
        anon_req.user = mock_user_factory(is_authenticated=False, role="User")
        with caplog.at_level(logging.WARNING):
            with pytest.raises(PermissionDenied):
                protected_view(anon_req)
        assert "Unauthorized admin access blocked" in caplog.text

        std_req = rf.get("/admin-panel/")
        std_req.user = mock_user_factory(is_authenticated=True, role="User")
        with pytest.raises(PermissionDenied):
            protected_view(std_req)

        admin_req = rf.get("/admin-panel/")
        admin_req.user = mock_user_factory(is_authenticated=True, role="Admin")
        assert protected_view(admin_req).status_code == 200

        staff_req = rf.get("/admin-panel/")
        staff_user = mock_user_factory(is_authenticated=True, role="User")
        staff_user.is_staff = True
        staff_req.user = staff_user
        assert protected_view(staff_req).status_code == 200


class TestAuditLogAdminReadOnly:
    """Unit tests ensuring AuditLogAdmin forbids add, change, and delete."""

    def test_audit_log_admin_denies_add_change_and_delete(self, mock_user_factory):
        from django.contrib.admin.sites import AdminSite

        from apps.admin_panel.admin import AuditLogAdmin

        model_admin = AuditLogAdmin(AuditLog, AdminSite())
        req = RequestFactory().get("/admin/admin_panel/auditlog/")
        req.user = mock_user_factory(is_authenticated=True, role="Admin")
        req.user.is_superuser = True

        assert model_admin.has_add_permission(req) is False
        assert model_admin.has_change_permission(req) is False
        assert model_admin.has_delete_permission(req) is False
