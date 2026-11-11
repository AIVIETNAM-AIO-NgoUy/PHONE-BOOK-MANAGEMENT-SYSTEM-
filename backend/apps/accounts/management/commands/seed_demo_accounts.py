"""Management command to idempotently seed demo and admin accounts with sample data."""

from dataclasses import dataclass
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.contacts.models import Contact, ContactBook, PhoneNumber
from apps.favorites.models import FavoriteItem, FavoriteList
from apps.groups.models import ContactGroup, Group

DEMO_USERNAME = "demo"
DEMO_EMAIL = "demo@phonebook.local"
DEMO_FULL_NAME = "Demo User"

ADMIN_USERNAME = "admin"
ADMIN_EMAIL = "admin@phonebook.local"
ADMIN_FULL_NAME = "System Administrator"

DEFAULT_PASSWORD = "A@123"

GROUP_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("Work Colleagues", "Engineering, product, and cross-functional teammates."),
    ("Family", "Immediate and extended family members."),
    ("VIP Clients", "Key enterprise accounts and priority partners."),
    ("Emergency", "24/7 urgent contacts, medical, and support lines."),
)


@dataclass(frozen=True)
class ContactSeedSpec:
    """Immutable specification for a single seeded demo contact."""

    full_name: str
    phones: tuple[tuple[str, str], ...]
    email: str | None = None
    address: str | None = None
    work_address: str | None = None
    birthday: date | None = None
    notes: str | None = None
    interaction_count: int = 0
    days_since_last_contact: int | None = None
    groups: tuple[str, ...] = ()
    favorite_priority: int | None = None


PhoneType = PhoneNumber.PhoneType

DEMO_CONTACTS: tuple[ContactSeedSpec, ...] = (
    ContactSeedSpec(
        full_name="An Nguyen",
        email="an.nguyen@techviet.vn",
        address="42 Le Loi Street, District 1, Ho Chi Minh City",
        work_address="Floor 14, Bitexco Tower, District 1, Ho Chi Minh City",
        birthday=date(1991, 4, 18),
        notes="Engineering lead on the core platform migration project.",
        interaction_count=42,
        days_since_last_contact=1,
        phones=(
            ("+84901234567", PhoneType.MOBILE),
            ("02838221100", PhoneType.WORK),
        ),
        groups=("Work Colleagues",),
        favorite_priority=1,
    ),
    ContactSeedSpec(
        full_name="Minh Tran",
        email="minh.tran@familymail.vn",
        address="18 Nguyen Hue Boulevard, District 1, Ho Chi Minh City",
        birthday=date(1988, 9, 3),
        notes="Older brother. Call on Sunday evenings.",
        interaction_count=35,
        days_since_last_contact=2,
        phones=(
            ("0912345678", PhoneType.MOBILE),
            ("02839104455", PhoneType.HOME),
        ),
        groups=("Family", "Emergency"),
        favorite_priority=1,
    ),
    ContactSeedSpec(
        full_name="Sarah Jenkins",
        email="s.jenkins@pacificventures.com",
        address="740 Howard Street, San Francisco, CA",
        work_address="550 Market Street, Suite 1200, San Francisco, CA",
        birthday=date(1985, 11, 22),
        notes="VP of Operations at Pacific Ventures. Prefers morning briefings.",
        interaction_count=28,
        days_since_last_contact=3,
        phones=(
            ("+14155550142", PhoneType.WORK),
            ("+14155550199", PhoneType.MOBILE),
            ("+14155550100", PhoneType.MAIN),
        ),
        groups=("VIP Clients",),
        favorite_priority=2,
    ),
    ContactSeedSpec(
        full_name="Dr. Hoang Pham",
        email="hoang.pham@cityclinic.vn",
        address="115 Pasteur Street, District 3, Ho Chi Minh City",
        work_address="City General Clinic, 200 Hai Ba Trung, Ho Chi Minh City",
        notes="Primary family physician. Emergency direct line available.",
        interaction_count=12,
        days_since_last_contact=14,
        phones=(
            ("0908765432", PhoneType.WORK),
            ("02838299911", PhoneType.MAIN),
        ),
        groups=("Emergency",),
        favorite_priority=3,
    ),
    ContactSeedSpec(
        full_name="Linh Vu",
        email="linh.vu@studioflow.io",
        address="27 Tran Hung Dao, Hoan Kiem, Hanoi",
        work_address="88 Ly Thuong Kiet, Hoan Kiem, Hanoi",
        birthday=date(1994, 7, 12),
        notes="Product designer collaborating on Q4 mobile redesign.",
        interaction_count=24,
        days_since_last_contact=4,
        phones=(
            ("0987654321", PhoneType.MOBILE),
            ("02439421188", PhoneType.WORK),
        ),
        groups=("Work Colleagues",),
        favorite_priority=4,
    ),
    ContactSeedSpec(
        full_name="David Chen",
        email="dchen@apexlogistics.sg",
        work_address="10 Marina Boulevard, Tower 2, Singapore",
        birthday=date(1982, 2, 9),
        notes="Enterprise account sponsor for APAC distribution.",
        interaction_count=19,
        days_since_last_contact=6,
        phones=(
            ("+6591234567", PhoneType.MOBILE),
            ("+6565550188", PhoneType.WORK),
        ),
        groups=("VIP Clients",),
        favorite_priority=5,
    ),
    ContactSeedSpec(
        full_name="Lan Nguyen",
        email="lan.nguyen@familymail.vn",
        address="18 Nguyen Hue Boulevard, District 1, Ho Chi Minh City",
        birthday=date(1962, 5, 29),
        notes="Mom. Prefers voice calls over text messages.",
        interaction_count=31,
        days_since_last_contact=1,
        phones=(
            ("0903112233", PhoneType.MOBILE),
            ("02838210077", PhoneType.HOME),
        ),
        groups=("Family", "Emergency"),
    ),
    ContactSeedSpec(
        full_name="Marcus Vance",
        email="mvance@northstarcloud.com",
        address="210 Pine Street, Seattle, WA",
        work_address="400 Broad Street, Floor 8, Seattle, WA",
        notes="Cloud infrastructure advisor. Quarterly architecture reviews.",
        interaction_count=15,
        days_since_last_contact=10,
        phones=(
            ("+12065550134", PhoneType.WORK),
            ("+12065550177", PhoneType.MOBILE),
        ),
        groups=("VIP Clients",),
    ),
    ContactSeedSpec(
        full_name="Thao Le",
        email="thao.le@techviet.vn",
        work_address="Floor 14, Bitexco Tower, District 1, Ho Chi Minh City",
        birthday=date(1993, 12, 1),
        notes="QA lead managing automated regression suites.",
        interaction_count=21,
        days_since_last_contact=5,
        phones=(("0934567890", PhoneType.MOBILE),),
        groups=("Work Colleagues",),
    ),
    ContactSeedSpec(
        full_name="Elena Rostova",
        email="elena@auroracapital.eu",
        address="14 Bahnhofstrasse, Zurich",
        work_address="22 Paradeplatz, Zurich",
        birthday=date(1987, 8, 15),
        notes="Financial controller for European partner accounts.",
        interaction_count=9,
        days_since_last_contact=20,
        phones=(
            ("+41445550120", PhoneType.WORK),
            ("+41795550188", PhoneType.MOBILE),
        ),
        groups=("VIP Clients",),
    ),
    ContactSeedSpec(
        full_name="Khang Do",
        email="khang.do@techviet.vn",
        address="95 Vo Van Tan, District 3, Ho Chi Minh City",
        work_address="Floor 12, Bitexco Tower, District 1, Ho Chi Minh City",
        notes="DevOps engineer handling Kubernetes and CI pipelines.",
        interaction_count=18,
        days_since_last_contact=2,
        phones=(
            ("0977112244", PhoneType.MOBILE),
            ("02838229944", PhoneType.WORK),
            ("0909887766", PhoneType.OTHER),
        ),
        groups=("Work Colleagues", "Emergency"),
    ),
    ContactSeedSpec(
        full_name="Hoa Dang",
        email="hoa.dang@familymail.vn",
        address="64 Bach Dang Street, Hai Chau, Da Nang",
        birthday=date(1995, 1, 25),
        notes="Cousin living in Da Nang.",
        interaction_count=7,
        days_since_last_contact=30,
        phones=(("0914556677", PhoneType.MOBILE),),
        groups=("Family",),
    ),
    ContactSeedSpec(
        full_name="James O'Connor",
        email="james.oconnor@dublinlegal.ie",
        work_address="19 St Stephen's Green, Dublin",
        notes="External legal counsel for data protection compliance.",
        interaction_count=6,
        days_since_last_contact=45,
        phones=(
            ("+35315550192", PhoneType.WORK),
            ("+353875550114", PhoneType.MOBILE),
        ),
        groups=("VIP Clients",),
    ),
    ContactSeedSpec(
        full_name="Building Security Desk",
        work_address="Lobby Reception, Bitexco Tower, District 1",
        notes="24/7 after-hours access and badge assistance.",
        interaction_count=4,
        days_since_last_contact=18,
        phones=(
            ("02838220001", PhoneType.MAIN),
            ("0902000113", PhoneType.OTHER),
        ),
        groups=("Emergency",),
    ),
    ContactSeedSpec(
        full_name="Phuong Bui",
        email="phuong.bui@techviet.vn",
        work_address="Floor 15, Bitexco Tower, District 1, Ho Chi Minh City",
        birthday=date(1990, 6, 7),
        notes="Engineering manager for search and indexing services.",
        interaction_count=16,
        days_since_last_contact=7,
        phones=(("0905667788", PhoneType.MOBILE),),
        groups=("Work Colleagues",),
    ),
    ContactSeedSpec(
        full_name="Kenji Takahashi",
        email="k.takahashi@kuroda-tech.jp",
        address="3-14-2 Minami-Aoyama, Minato-ku, Tokyo",
        work_address="Roppongi Hills Mori Tower 28F, Tokyo",
        birthday=date(1984, 10, 11),
        notes="Hardware integration partner in Tokyo.",
        interaction_count=11,
        days_since_last_contact=12,
        phones=(
            ("+81355501442", PhoneType.WORK),
            ("+81905550112", PhoneType.MOBILE),
        ),
        groups=("VIP Clients",),
    ),
    ContactSeedSpec(
        full_name="Tuan Ngo",
        email="tuan.ngo@familymail.vn",
        address="102 Phan Dinh Phung, Phu Nhuan, Ho Chi Minh City",
        birthday=date(1960, 3, 14),
        notes="Uncle Tuan. Enjoys morning coffee meetups.",
        interaction_count=5,
        days_since_last_contact=25,
        phones=(
            ("0906443322", PhoneType.MOBILE),
            ("02838445566", PhoneType.HOME),
        ),
        groups=("Family",),
    ),
    ContactSeedSpec(
        full_name="Priya Nair",
        email="priya.nair@techviet.vn",
        work_address="Floor 14, Bitexco Tower, District 1, Ho Chi Minh City",
        birthday=date(1996, 2, 20),
        notes="Backend engineer working on billing webhooks.",
        interaction_count=13,
        days_since_last_contact=8,
        phones=(
            ("0328889900", PhoneType.MOBILE),
            ("02838221199", PhoneType.WORK),
        ),
        groups=("Work Colleagues",),
    ),
    ContactSeedSpec(
        full_name="24/7 Roadside Assistance",
        notes="National vehicle recovery and towing dispatch hotline.",
        interaction_count=1,
        days_since_last_contact=90,
        phones=(
            ("1900123456", PhoneType.MAIN),
            ("0901999888", PhoneType.OTHER),
        ),
        groups=("Emergency",),
    ),
    ContactSeedSpec(
        full_name="Claire Moreau",
        email="claire.moreau@atelier-lyon.fr",
        address="8 Rue de la Republique, Lyon",
        birthday=date(1989, 12, 19),
        notes="Met at Web Summit; exploring design partnership.",
        interaction_count=3,
        days_since_last_contact=40,
        phones=(("+33612345678", PhoneType.MOBILE),),
    ),
    ContactSeedSpec(
        full_name="Duc Hoang",
        email="duc.hoang@techviet.vn",
        work_address="Floor 13, Bitexco Tower, District 1, Ho Chi Minh City",
        notes="Data analyst supporting weekly KPI dashboards.",
        interaction_count=8,
        days_since_last_contact=9,
        phones=(("0981122334", PhoneType.MOBILE),),
        groups=("Work Colleagues",),
    ),
    ContactSeedSpec(
        full_name="Hannah Abbott",
        email="hannah@greenleafstudio.co.uk",
        address="24 King Street, Manchester",
        birthday=date(1992, 8, 4),
        interaction_count=2,
        days_since_last_contact=60,
        phones=(
            ("+447700900123", PhoneType.MOBILE),
            ("+441614960444", PhoneType.HOME),
        ),
    ),
    ContactSeedSpec(
        full_name="Vy Truong",
        email="vy.truong@familymail.vn",
        address="55 Dien Bien Phu, Binh Thanh, Ho Chi Minh City",
        birthday=date(1998, 10, 30),
        notes="Younger sister studying architecture.",
        interaction_count=20,
        days_since_last_contact=3,
        phones=(("0945678901", PhoneType.MOBILE),),
        groups=("Family",),
    ),
    ContactSeedSpec(
        full_name="Carlos Mendez",
        email="cmendez@solarisenergy.es",
        work_address="Paseo de la Castellana 95, Madrid",
        notes="Requested product roadmap deck for next quarter.",
        interaction_count=0,
        phones=(
            ("+34915550178", PhoneType.WORK),
            ("+34600555123", PhoneType.MOBILE),
        ),
        groups=("VIP Clients",),
    ),
    ContactSeedSpec(
        full_name="Local Pharmacy Express",
        address="120 Nguyen Dinh Chieu, District 3, Ho Chi Minh City",
        notes="Late-night prescription delivery service.",
        interaction_count=0,
        phones=(("02839301122", PhoneType.MAIN),),
    ),
)


class Command(BaseCommand):
    """Idempotently seed demo and admin accounts along with sample demo data."""

    help = (
        "Seed 'demo' and 'admin' accounts with sample contacts, groups, and favorites "
        "(idempotent; pass --reset to restore defaults)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--reset",
            action="store_true",
            help=(
                "Reset passwords/status for 'demo' and 'admin' and rebuild 'demo' "
                "contacts, groups, and favorites."
            ),
        )

    def handle(self, *args, **options) -> None:
        reset: bool = bool(options["reset"])

        with transaction.atomic():
            demo_user, demo_book, demo_favorites, demo_created = self._ensure_demo_user(reset=reset)
            admin_user, admin_created = self._ensure_admin_user(reset=reset)

            if reset:
                self._clear_demo_data(demo_book, demo_favorites)

            seeded_counts = None
            if Contact.objects.filter(book=demo_book).count() == 0:
                seeded_counts = self._seed_demo_data(demo_book, demo_favorites)

        demo_action = "Created" if demo_created else ("Reset" if reset else "Verified")
        admin_action = "Created" if admin_created else ("Reset" if reset else "Verified")
        self.stdout.write(f"{demo_action} account '{demo_user.username}' (id={demo_user.pk}).")
        self.stdout.write(f"{admin_action} account '{admin_user.username}' (id={admin_user.pk}).")

        if seeded_counts is not None:
            contacts_n, phones_n, groups_n, memberships_n, favorites_n = seeded_counts
            self.stdout.write(
                self.style.SUCCESS(
                    f"Seeded {contacts_n} contacts, {phones_n} phone numbers, "
                    f"{groups_n} groups ({memberships_n} memberships), and "
                    f"{favorites_n} favorites for '{demo_user.username}'."
                )
            )
        else:
            self.stdout.write(
                f"Skipped sample data seeding for '{demo_user.username}' "
                "(existing contacts preserved)."
            )

    def _ensure_demo_user(
        self, *, reset: bool
    ) -> tuple[CustomUser, ContactBook, FavoriteList, bool]:
        user = CustomUser.objects.filter(username__iexact=DEMO_USERNAME).first()
        created = False

        if user is None:
            user = CustomUser.objects.create_user(
                username=DEMO_USERNAME,
                email=DEMO_EMAIL,
                full_name=DEMO_FULL_NAME,
                password=DEFAULT_PASSWORD,
                role=CustomUser.Role.USER,
                account_status=CustomUser.AccountStatus.ACTIVE,
                is_active=True,
            )
            created = True
        elif reset:
            user.email = DEMO_EMAIL
            user.full_name = DEMO_FULL_NAME
            user.role = CustomUser.Role.USER
            user.account_status = CustomUser.AccountStatus.ACTIVE
            user.is_active = True
            user.set_password(DEFAULT_PASSWORD)
            user.save()

        book, _ = ContactBook.objects.get_or_create(user=user)
        favorite_list, _ = FavoriteList.objects.get_or_create(book=book)
        return user, book, favorite_list, created

    def _ensure_admin_user(self, *, reset: bool) -> tuple[CustomUser, bool]:
        user = CustomUser.objects.filter(username__iexact=ADMIN_USERNAME).first()
        created = False

        if user is None:
            user = CustomUser.objects.create_superuser(
                username=ADMIN_USERNAME,
                email=ADMIN_EMAIL,
                full_name=ADMIN_FULL_NAME,
                password=DEFAULT_PASSWORD,
                role=CustomUser.Role.ADMIN,
                account_status=CustomUser.AccountStatus.ACTIVE,
                is_staff=True,
                is_superuser=True,
                is_active=True,
            )
            created = True
        elif reset:
            user.email = ADMIN_EMAIL
            user.full_name = ADMIN_FULL_NAME
            user.role = CustomUser.Role.ADMIN
            user.account_status = CustomUser.AccountStatus.ACTIVE
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.set_password(DEFAULT_PASSWORD)
            user.save()

        book, _ = ContactBook.objects.get_or_create(user=user)
        FavoriteList.objects.get_or_create(book=book)
        return user, created

    def _clear_demo_data(self, book: ContactBook, favorite_list: FavoriteList) -> None:
        FavoriteItem.objects.filter(favorite_list=favorite_list).delete()
        ContactGroup.objects.filter(group__book=book).delete()
        Group.objects.filter(book=book).delete()
        Contact.objects.filter(book=book).delete()

    def _seed_demo_data(
        self, book: ContactBook, favorite_list: FavoriteList
    ) -> tuple[int, int, int, int, int]:
        now = timezone.now()

        groups_by_name: dict[str, Group] = {}
        for group_name, description in GROUP_DEFINITIONS:
            existing_group = Group.objects.filter(book=book, group_name__iexact=group_name).first()
            if existing_group is None:
                existing_group = Group.objects.create(
                    book=book,
                    group_name=group_name,
                    description=description,
                )
            groups_by_name[group_name] = existing_group

        contact_objects: list[Contact] = []
        for spec in DEMO_CONTACTS:
            last_contacted_at = (
                now - timedelta(days=spec.days_since_last_contact)
                if spec.days_since_last_contact is not None and spec.interaction_count > 0
                else None
            )
            contact_objects.append(
                Contact(
                    book=book,
                    full_name=spec.full_name,
                    email=spec.email,
                    address=spec.address,
                    work_address=spec.work_address,
                    birthday=spec.birthday,
                    notes=spec.notes,
                    interaction_count=spec.interaction_count,
                    last_contacted_at=last_contacted_at,
                )
            )

        created_contacts = Contact.objects.bulk_create(contact_objects)

        phone_objects: list[PhoneNumber] = []
        membership_objects: list[ContactGroup] = []
        favorite_objects: list[FavoriteItem] = []

        for contact, spec in zip(created_contacts, DEMO_CONTACTS):
            for idx, (number, phone_type) in enumerate(spec.phones):
                phone_objects.append(
                    PhoneNumber(
                        contact=contact,
                        phone_number=number,
                        phone_type=phone_type,
                        is_primary=(idx == 0),
                    )
                )
            for group_name in spec.groups:
                membership_objects.append(
                    ContactGroup(
                        contact=contact,
                        group=groups_by_name[group_name],
                    )
                )
            if spec.favorite_priority is not None:
                favorite_objects.append(
                    FavoriteItem(
                        favorite_list=favorite_list,
                        contact=contact,
                        priority=spec.favorite_priority,
                    )
                )

        PhoneNumber.objects.bulk_create(phone_objects)
        ContactGroup.objects.bulk_create(membership_objects, ignore_conflicts=True)
        FavoriteItem.objects.bulk_create(favorite_objects, ignore_conflicts=True)

        return (
            len(created_contacts),
            len(phone_objects),
            len(groups_by_name),
            len(membership_objects),
            len(favorite_objects),
        )
