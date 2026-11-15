import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.merchants.choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.models import Merchant, MerchantMembership
from apps.stores.choices import StoreStatus
from apps.stores.exceptions import (
    DuplicateStoreError,
    SlugAlreadyTakenError,
    SlugValidationError,
    StorePermissionDeniedError,
    StorePublishError,
)
from apps.stores.models import Store
from apps.stores.services import (
    change_store_slug,
    create_store,
    publish_store,
    unpublish_store,
    update_store_profile,
)

User = get_user_model()


@pytest.fixture
def owner_user(db):
    return User.objects.create_user(
        email="owner@example.com",
        password="ValidPassword123!",
        is_verified=True,
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="admin@example.com",
        password="ValidPassword123!",
        is_verified=True,
    )


@pytest.fixture
def manager_user(db):
    return User.objects.create_user(
        email="manager@example.com",
        password="ValidPassword123!",
        is_verified=True,
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        email="staff@example.com",
        password="ValidPassword123!",
        is_verified=True,
    )


@pytest.fixture
def unaffiliated_user(db):
    return User.objects.create_user(
        email="stranger@example.com",
        password="ValidPassword123!",
        is_verified=True,
    )


@pytest.fixture
def active_merchant(db, owner_user, admin_user, manager_user, staff_user):
    merchant = Merchant.objects.create(
        name="Global Mart",
        email="global@example.com",
        contact_number="9876543210",
        address="100 Commercial Road",
        city="Bengaluru",
        state="Karnataka",
        pin_code="560001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )
    MerchantMembership.objects.create(
        user=owner_user,
        merchant=merchant,
        role=MembershipRole.OWNER,
        status=MembershipStatus.ACTIVE,
    )
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
    return merchant


@pytest.mark.django_db
class TestStoreServices:
    def test_actor_is_mandatory_in_mutation_services(self, active_merchant):
        with pytest.raises(TypeError, match="actor is required"):
            create_store(
                merchant_id=active_merchant.id,
                actor=None,
                name="Store Without Actor",
                slug="no-actor-store",
            )

        store = Store.objects.create(
            merchant=active_merchant,
            name="Existing Store",
            slug="existing-store",
        )

        with pytest.raises(TypeError, match="actor is required"):
            update_store_profile(store_id=store.id, actor=None, name="New Name")

        with pytest.raises(TypeError, match="actor is required"):
            change_store_slug(store_id=store.id, actor=None, new_slug="new-slug")

        with pytest.raises(TypeError, match="actor is required"):
            publish_store(store_id=store.id, actor=None)

        with pytest.raises(TypeError, match="actor is required"):
            unpublish_store(store_id=store.id, actor=None)

    def test_create_store_success(self, active_merchant, owner_user):
        store = create_store(
            merchant_id=active_merchant.id,
            actor=owner_user,
            name="  Global Store  ",
            slug="  Global-Store  ",
            description="The flagship digital store.",
        )
        assert store.name == "Global Store"
        assert store.slug == "global-store"
        assert store.status == StoreStatus.DRAFT
        assert store.description == "The flagship digital store."
        assert store.merchant == active_merchant

    def test_create_store_server_side_merchant_resolution(self, owner_user):
        invalid_id = uuid.uuid4()
        with pytest.raises(ValidationError, match="does not exist"):
            create_store(
                merchant_id=invalid_id,
                actor=owner_user,
                name="Ghost Store",
                slug="ghost-store",
            )

    def test_create_store_rejects_unauthorized_actor(
        self, active_merchant, manager_user, staff_user, unaffiliated_user
    ):
        for unauthorized_actor in [manager_user, staff_user, unaffiliated_user]:
            with pytest.raises(StorePermissionDeniedError):
                create_store(
                    merchant_id=active_merchant.id,
                    actor=unauthorized_actor,
                    name="Unauthorized Store",
                    slug=f"unauthorized-store-{unauthorized_actor.id}",
                )

    def test_create_store_duplicate_prevention(self, active_merchant, owner_user):
        create_store(
            merchant_id=active_merchant.id,
            actor=owner_user,
            name="First Store",
            slug="first-store",
        )
        with pytest.raises(DuplicateStoreError, match="already has an associated store"):
            create_store(
                merchant_id=active_merchant.id,
                actor=owner_user,
                name="Second Store",
                slug="second-store",
            )

    def test_create_store_slug_already_taken(self, active_merchant, owner_user, db):
        other_merchant = Merchant.objects.create(
            name="Other Mart",
            email="other@example.com",
            contact_number="9876543212",
            address="Other St",
            city="Pune",
            state="Maharashtra",
            pin_code="411001",
            status=MerchantStatus.ACTIVE,
        )
        MerchantMembership.objects.create(
            user=owner_user,
            merchant=other_merchant,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )

        create_store(
            merchant_id=active_merchant.id,
            actor=owner_user,
            name="First Store",
            slug="popular-shop",
        )

        # Case-insensitive collision
        with pytest.raises(SlugAlreadyTakenError, match="already taken"):
            create_store(
                merchant_id=other_merchant.id,
                actor=owner_user,
                name="Other Store",
                slug="POPULAR-SHOP",
            )

    def test_create_store_reserved_slug_rejected(self, active_merchant, owner_user):
        with pytest.raises(SlugValidationError, match="reserved"):
            create_store(
                merchant_id=active_merchant.id,
                actor=owner_user,
                name="Admin Store",
                slug="admin",
            )

    def test_update_store_profile_success(self, active_merchant, owner_user):
        store = create_store(
            merchant_id=active_merchant.id,
            actor=owner_user,
            name="Original Name",
            slug="original-slug",
            description="Old description",
        )

        updated_store = update_store_profile(
            store_id=store.id,
            actor=owner_user,
            name="Updated Name",
            description="New description",
        )
        assert updated_store.name == "Updated Name"
        assert updated_store.description == "New description"
        assert updated_store.slug == "original-slug"
        assert updated_store.status == StoreStatus.DRAFT

    def test_update_store_profile_rejects_empty_name(self, active_merchant, owner_user):
        store = create_store(
            merchant_id=active_merchant.id,
            actor=owner_user,
            name="Valid Name",
            slug="valid-name",
        )
        with pytest.raises(ValidationError, match="cannot be empty"):
            update_store_profile(store_id=store.id, actor=owner_user, name="   ")

    def test_change_store_slug_success(self, active_merchant, owner_user):
        store = create_store(
            merchant_id=active_merchant.id,
            actor=owner_user,
            name="My Store",
            slug="old-slug",
        )

        changed_store = change_store_slug(
            store_id=store.id,
            actor=owner_user,
            new_slug="  Brand-New-Slug  ",
        )
        assert changed_store.slug == "brand-new-slug"

    def test_change_store_slug_rejects_collision_and_reserved(
        self, active_merchant, owner_user, db
    ):
        other_merchant = Merchant.objects.create(
            name="Other Mart",
            email="other@example.com",
            contact_number="9876543212",
            address="Other St",
            city="Pune",
            state="Maharashtra",
            pin_code="411001",
            status=MerchantStatus.ACTIVE,
        )
        Store.objects.create(
            merchant=other_merchant,
            name="Taken Store",
            slug="taken-slug",
        )

        store = create_store(
            merchant_id=active_merchant.id,
            actor=owner_user,
            name="My Store",
            slug="my-own-slug",
        )

        with pytest.raises(SlugAlreadyTakenError):
            change_store_slug(store_id=store.id, actor=owner_user, new_slug="TAKEN-SLUG")

        with pytest.raises(SlugValidationError):
            change_store_slug(store_id=store.id, actor=owner_user, new_slug="dashboard")

    def test_publish_store_fails_when_merchant_not_active(self, owner_user, db):
        pending_merchant = Merchant.objects.create(
            name="Pending Mart",
            email="pending@example.com",
            contact_number="9876543210",
            address="123 Street",
            city="City",
            state="State",
            pin_code="400001",
            status=MerchantStatus.PENDING,
        )
        MerchantMembership.objects.create(
            user=owner_user,
            merchant=pending_merchant,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
        store = create_store(
            merchant_id=pending_merchant.id,
            actor=owner_user,
            name="Pending Store",
            slug="pending-store",
        )

        with pytest.raises(StorePublishError, match="must be in ACTIVE status"):
            publish_store(store_id=store.id, actor=owner_user)

    def test_publish_and_unpublish_store_lifecycle(self, active_merchant, owner_user):
        store = create_store(
            merchant_id=active_merchant.id,
            actor=owner_user,
            name="Active Store",
            slug="active-store",
        )
        assert store.status == StoreStatus.DRAFT

        published_store = publish_store(store_id=store.id, actor=owner_user)
        assert published_store.status == StoreStatus.PUBLISHED

        unpublished_store = unpublish_store(store_id=store.id, actor=owner_user)
        assert unpublished_store.status == StoreStatus.UNPUBLISHED
