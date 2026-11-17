import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.merchants.choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.models import MerchantMembership
from apps.merchants.services import create_merchant
from apps.stores.choices import StoreStatus
from apps.stores.models import Store

User = get_user_model()


def make_test_image(
    format_name: str = "PNG",
    size: tuple[int, int] = (100, 100),
    color: str = "blue",
) -> SimpleUploadedFile:
    """Generates an in-memory test image using Pillow."""
    buffer = io.BytesIO()
    image = Image.new("RGB", size, color=color)
    image.save(buffer, format=format_name)
    buffer.seek(0)
    ext = "jpg" if format_name.upper() == "JPEG" else format_name.lower()
    return SimpleUploadedFile(
        f"test.{ext}",
        buffer.read(),
        content_type=f"image/{ext}",
    )


@pytest.fixture
def owner_user(db):
    return User.objects.create_user(
        email="owner@alpha.com",
        password="ValidPassword123!",
        is_verified=True,
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="admin@alpha.com",
        password="ValidPassword123!",
        is_verified=True,
    )


@pytest.fixture
def manager_user(db):
    return User.objects.create_user(
        email="manager@alpha.com",
        password="ValidPassword123!",
        is_verified=True,
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        email="staff@alpha.com",
        password="ValidPassword123!",
        is_verified=True,
    )


@pytest.fixture
def merchant_alpha(db, owner_user, admin_user, manager_user, staff_user):
    merchant, _ = create_merchant(
        owner_user=owner_user,
        name="Alpha Store Corp",
        business_type=BusinessType.RETAIL,
        contact_number="+91 9876543210",
        email="alpha@example.com",
        address="100 Market St",
        city="Mumbai",
        state="Maharashtra",
        pin_code="400001",
    )
    merchant.status = MerchantStatus.ACTIVE
    merchant.save()

    MerchantMembership.objects.create(
        user=admin_user,
        merchant=merchant,
        role=MembershipRole.ADMIN,
        status=MembershipStatus.ACTIVE,
    )
    MerchantMembership.objects.create(
        user=manager_user,
        merchant=merchant,
        role=MembershipRole.MANAGER,
        status=MembershipStatus.ACTIVE,
    )
    MerchantMembership.objects.create(
        user=staff_user,
        merchant=merchant,
        role=MembershipRole.STAFF,
        status=MembershipStatus.ACTIVE,
    )
    merchant.owner_user = owner_user
    return merchant


@pytest.fixture
def store_alpha(db, merchant_alpha):
    return Store.objects.create(
        merchant=merchant_alpha,
        name="Alpha Goods",
        slug="alpha-goods",
        status=StoreStatus.PUBLISHED,
    )


@pytest.fixture
def merchant_beta(db):
    user = User.objects.create_user(
        email="owner@beta.com",
        password="ValidPassword123!",
        is_verified=True,
    )
    merchant, _ = create_merchant(
        owner_user=user,
        name="Beta Logistics",
        business_type=BusinessType.WHOLESALE,
        contact_number="+91 9876543211",
        email="beta@example.com",
        address="200 Freight Rd",
        city="Pune",
        state="Maharashtra",
        pin_code="411001",
    )
    merchant.status = MerchantStatus.ACTIVE
    merchant.save()
    merchant.owner_user = user
    return merchant


@pytest.fixture
def store_beta(db, merchant_beta):
    return Store.objects.create(
        merchant=merchant_beta,
        name="Beta Wholesale",
        slug="beta-wholesale",
        status=StoreStatus.PUBLISHED,
    )
