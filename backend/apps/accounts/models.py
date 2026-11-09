"""Custom user model and manager for the Phone Book Management System."""

from django.apps import apps
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import IntegrityError, models, transaction
from django.db.models.functions import Lower

from apps.core.models import TimeStampedModel


class CustomUserManager(BaseUserManager):
    """Manager for CustomUser supporting normalized email and admin creation."""

    use_in_migrations = True

    @transaction.atomic
    def create_user(self, username: str, email: str, password: str | None = None, **extra_fields):
        """Create and persist a standard active user with normalized email and containers."""
        if not username or not username.strip():
            raise ValueError("The username field must be set.")
        if not email or not email.strip():
            raise ValueError("The email field must be set.")

        normalized_username = username.strip()
        normalized_email = self.normalize_email(email).strip().lower()

        extra_fields.setdefault("role", CustomUser.Role.USER)
        extra_fields.setdefault("account_status", CustomUser.AccountStatus.ACTIVE)
        extra_fields.setdefault("is_active", True)

        user = self.model(
            username=normalized_username,
            email=normalized_email,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)

        try:
            contact_book_model = apps.get_model("contacts", "ContactBook")
        except LookupError:
            contact_book_model = None

        if contact_book_model is not None:
            try:
                book = contact_book_model.objects.get(user=user)
            except contact_book_model.DoesNotExist:
                try:
                    with transaction.atomic(using=self._db):
                        book = contact_book_model.objects.create(user=user)
                except IntegrityError:
                    book = contact_book_model.objects.get(user=user)
            try:
                favorite_list_model = apps.get_model("favorites", "FavoriteList")
            except LookupError:
                favorite_list_model = None
            if favorite_list_model is not None:
                try:
                    favorite_list_model.objects.get(book=book)
                except favorite_list_model.DoesNotExist:
                    try:
                        with transaction.atomic(using=self._db):
                            favorite_list_model.objects.create(book=book)
                    except IntegrityError:
                        favorite_list_model.objects.get(book=book)

        return user

    def create_superuser(
        self, username: str, email: str, password: str | None = None, **extra_fields
    ):
        """Create and persist an administrative superuser."""
        extra_fields.setdefault("role", CustomUser.Role.ADMIN)
        extra_fields.setdefault("account_status", CustomUser.AccountStatus.ACTIVE)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        if extra_fields.get("role") != CustomUser.Role.ADMIN:
            raise ValueError("Superuser must have role='Admin'.")

        return self.create_user(username, email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """Platform identity model for standard Users and System Administrators."""

    class Role(models.TextChoices):
        USER = "User", "User"
        ADMIN = "Admin", "Admin"

    class AccountStatus(models.TextChoices):
        ACTIVE = "Active", "Active"
        LOCKED = "Locked", "Locked"

    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(max_length=254, unique=True)
    password = models.CharField("password", max_length=255)
    full_name = models.CharField(max_length=150, default="", blank=True)
    avatar_url = models.CharField(max_length=255, null=True, blank=True, default=None)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.USER,
    )
    account_status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.ACTIVE,
    )
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email", "full_name"]

    class Meta:
        db_table = "users_customuser"
        constraints = [
            models.UniqueConstraint(Lower("username"), name="uq_users_username_lower"),
            models.UniqueConstraint(Lower("email"), name="uq_users_email_lower"),
            models.CheckConstraint(
                condition=models.Q(role__in=["User", "Admin"]),
                name="chk_user_role_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(account_status__in=["Active", "Locked"]),
                name="chk_user_account_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["account_status"], name="idx_users_account_status"),
        ]

    def save(self, *args, **kwargs):
        """Normalize username whitespace and lowercase email before saving."""
        if self.username:
            self.username = self.username.strip()
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def is_admin(self) -> bool:
        """Return True when the user holds the Admin role."""
        return self.role == self.Role.ADMIN

    def __str__(self) -> str:
        return f"{self.username} ({self.role})"
