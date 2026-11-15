import uuid

import pytest
from django.db import IntegrityError, models

from apps.merchants.choices import BusinessType, MerchantStatus
from apps.merchants.models import Merchant
from apps.stores.choices import StoreStatus
from apps.stores.models import Store


@pytest.fixture
def active_merchant(db):
    return Merchant.objects.create(
        name="Apex Mart",
        email="apex@example.com",
        contact_number="9876543210",
        address="123 High Street",
        city="Mumbai",
        state="Maharashtra",
        pin_code="400001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )


@pytest.fixture
def pending_merchant(db):
    return Merchant.objects.create(
        name="Pending Retail",
        email="pending@example.com",
        contact_number="9876543211",
        address="456 Low Street",
        city="Pune",
        state="Maharashtra",
        pin_code="411001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.PENDING,
    )


@pytest.mark.django_db
class TestStoreModel:
    def test_store_creation_defaults(self, active_merchant):
        store = Store.objects.create(
            merchant=active_merchant,
            name="Apex Store",
            slug="apex-store",
            description="Official store of Apex Mart",
        )
        assert isinstance(store.id, uuid.UUID)
        assert store.status == StoreStatus.DRAFT
        assert store.merchant == active_merchant
        assert str(store) == "Apex Store (apex-store)"
        assert store.get_absolute_url() == "/s/apex-store/"
        assert store.created_at is not None
        assert store.updated_at is not None

    def test_one_to_one_merchant_constraint(self, active_merchant):
        Store.objects.create(
            merchant=active_merchant,
            name="First Store",
            slug="first-store",
        )
        with pytest.raises(IntegrityError):
            Store.objects.create(
                merchant=active_merchant,
                name="Second Store",
                slug="second-store",
            )

    def test_merchant_protected_from_deletion_while_store_exists(self, active_merchant):
        Store.objects.create(
            merchant=active_merchant,
            name="Apex Store",
            slug="apex-store",
        )
        with pytest.raises(models.ProtectedError):
            active_merchant.delete()

    def test_case_insensitive_unique_slug_database_constraint(
        self, active_merchant, pending_merchant
    ):
        Store.objects.create(
            merchant=active_merchant,
            name="Apex Store",
            slug="unique-brand",
        )
        with pytest.raises(IntegrityError):
            Store.objects.create(
                merchant=pending_merchant,
                name="Another Store",
                slug="UNIQUE-BRAND",
            )

    def test_model_clean_normalizes_slug(self, active_merchant):
        store = Store(
            merchant=active_merchant,
            name="Apex Store",
            slug="  Apex-Shop  ",
        )
        store.clean()
        assert store.slug == "apex-shop"

    @pytest.mark.parametrize(
        ("store_status", "merchant_status", "expected_accessible"),
        [
            (StoreStatus.PUBLISHED, MerchantStatus.ACTIVE, True),
            (StoreStatus.DRAFT, MerchantStatus.ACTIVE, False),
            (StoreStatus.UNPUBLISHED, MerchantStatus.ACTIVE, False),
            (StoreStatus.SUSPENDED, MerchantStatus.ACTIVE, False),
            (StoreStatus.PUBLISHED, MerchantStatus.PENDING, False),
            (StoreStatus.PUBLISHED, MerchantStatus.SUSPENDED, False),
            (StoreStatus.PUBLISHED, MerchantStatus.INACTIVE, False),
            (StoreStatus.DRAFT, MerchantStatus.PENDING, False),
            (StoreStatus.SUSPENDED, MerchantStatus.SUSPENDED, False),
        ],
    )
    def test_is_publicly_accessible_property(
        self, active_merchant, store_status, merchant_status, expected_accessible
    ):
        active_merchant.status = merchant_status
        active_merchant.save(update_fields=["status"])

        store = Store(
            merchant=active_merchant,
            name="Test Store",
            slug="test-store",
            status=store_status,
        )
        assert store.is_publicly_accessible is expected_accessible
