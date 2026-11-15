import pytest
from django.contrib.auth import get_user_model

from apps.merchants.choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.models import Merchant, MerchantMembership
from apps.merchants.permissions import MerchantPermission, has_merchant_permission
from apps.stores.choices import StoreStatus
from apps.stores.exceptions import StorePermissionDeniedError, StorePublishError
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
def users(db):
    return {
        "owner": User.objects.create_user(
            email="owner@org.com", password="Pass123!Valid", is_verified=True
        ),
        "admin": User.objects.create_user(
            email="admin@org.com", password="Pass123!Valid", is_verified=True
        ),
        "manager": User.objects.create_user(
            email="manager@org.com", password="Pass123!Valid", is_verified=True
        ),
        "staff": User.objects.create_user(
            email="staff@org.com", password="Pass123!Valid", is_verified=True
        ),
        "suspended_owner": User.objects.create_user(
            email="susp_owner@org.com", password="Pass123!Valid", is_verified=True
        ),
        "stranger": User.objects.create_user(
            email="stranger@org.com", password="Pass123!Valid", is_verified=True
        ),
    }


@pytest.fixture
def merchant(db, users):
    m = Merchant.objects.create(
        name="Test Merchant Org",
        email="test@org.com",
        contact_number="9876543210",
        address="100 Org St",
        city="Mumbai",
        state="MH",
        pin_code="400001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )
    MerchantMembership.objects.create(
        user=users["owner"], merchant=m, role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE
    )
    MerchantMembership.objects.create(
        user=users["admin"], merchant=m, role=MembershipRole.ADMIN, status=MembershipStatus.ACTIVE
    )
    MerchantMembership.objects.create(
        user=users["manager"],
        merchant=m,
        role=MembershipRole.MANAGER,
        status=MembershipStatus.ACTIVE,
    )
    MerchantMembership.objects.create(
        user=users["staff"], merchant=m, role=MembershipRole.STAFF, status=MembershipStatus.ACTIVE
    )
    MerchantMembership.objects.create(
        user=users["suspended_owner"],
        merchant=m,
        role=MembershipRole.OWNER,
        status=MembershipStatus.SUSPENDED,
    )
    return m


@pytest.mark.django_db
class TestStoreAuthorizationMatrix:
    def test_has_merchant_permission_helper(self, merchant, users):
        # OWNER grants
        assert has_merchant_permission(users["owner"], merchant, MerchantPermission.MANAGE_STORE)
        assert has_merchant_permission(
            users["owner"], merchant, MerchantPermission.CHANGE_STORE_SLUG
        )
        assert has_merchant_permission(users["owner"], merchant, MerchantPermission.PUBLISH_STORE)

        # ADMIN grants
        assert has_merchant_permission(users["admin"], merchant, MerchantPermission.MANAGE_STORE)
        assert has_merchant_permission(
            users["admin"], merchant, MerchantPermission.CHANGE_STORE_SLUG
        )
        assert has_merchant_permission(users["admin"], merchant, MerchantPermission.PUBLISH_STORE)

        # MANAGER denied
        assert not has_merchant_permission(
            users["manager"], merchant, MerchantPermission.MANAGE_STORE
        )
        assert not has_merchant_permission(
            users["manager"], merchant, MerchantPermission.CHANGE_STORE_SLUG
        )
        assert not has_merchant_permission(
            users["manager"], merchant, MerchantPermission.PUBLISH_STORE
        )

        # STAFF denied
        assert not has_merchant_permission(
            users["staff"], merchant, MerchantPermission.MANAGE_STORE
        )
        assert not has_merchant_permission(
            users["staff"], merchant, MerchantPermission.CHANGE_STORE_SLUG
        )
        assert not has_merchant_permission(
            users["staff"], merchant, MerchantPermission.PUBLISH_STORE
        )

        # SUSPENDED membership denied
        assert not has_merchant_permission(
            users["suspended_owner"], merchant, MerchantPermission.MANAGE_STORE
        )
        assert not has_merchant_permission(
            users["suspended_owner"], merchant, MerchantPermission.PUBLISH_STORE
        )

        # UNAFFILIATED user denied
        assert not has_merchant_permission(
            users["stranger"], merchant, MerchantPermission.MANAGE_STORE
        )

    def test_owner_and_admin_can_perform_all_store_operations(self, merchant, users):
        for authorized_user in [users["owner"], users["admin"]]:
            # Clean up store if exists from previous loop iteration
            Store.objects.filter(merchant=merchant).delete()

            # 1. Create
            store = create_store(
                merchant_id=merchant.id,
                actor=authorized_user,
                name="Auth Store",
                slug=f"auth-store-{authorized_user.id}",
            )
            assert store.status == StoreStatus.DRAFT

            # 2. Update Profile
            update_store_profile(
                store_id=store.id,
                actor=authorized_user,
                name="Updated Auth Store",
            )

            # 3. Change Slug
            change_store_slug(
                store_id=store.id,
                actor=authorized_user,
                new_slug=f"new-slug-{authorized_user.id}",
            )

            # 4. Publish
            publish_store(store_id=store.id, actor=authorized_user)
            store.refresh_from_db()
            assert store.status == StoreStatus.PUBLISHED

            # 5. Unpublish
            unpublish_store(store_id=store.id, actor=authorized_user)
            store.refresh_from_db()
            assert store.status == StoreStatus.UNPUBLISHED

    def test_manager_and_staff_denied_all_store_mutations(self, merchant, users):
        store = Store.objects.create(
            merchant=merchant,
            name="Existing Store",
            slug="existing-store",
            status=StoreStatus.DRAFT,
        )

        for unauthorized_user in [
            users["manager"],
            users["staff"],
            users["suspended_owner"],
            users["stranger"],
        ]:
            # Update denied
            with pytest.raises(StorePermissionDeniedError):
                update_store_profile(store_id=store.id, actor=unauthorized_user, name="Hacked Name")

            # Change slug denied
            with pytest.raises(StorePermissionDeniedError):
                change_store_slug(
                    store_id=store.id, actor=unauthorized_user, new_slug="hacked-slug"
                )

            # Publish denied
            with pytest.raises(StorePermissionDeniedError):
                publish_store(store_id=store.id, actor=unauthorized_user)

            # Unpublish denied
            with pytest.raises(StorePermissionDeniedError):
                unpublish_store(store_id=store.id, actor=unauthorized_user)

    def test_pending_merchant_allows_setup_but_blocks_publishing(self, merchant, users):
        merchant.status = MerchantStatus.PENDING
        merchant.save(update_fields=["status"])

        # Create store in draft during onboarding is permitted
        store = create_store(
            merchant_id=merchant.id,
            actor=users["owner"],
            name="Onboarding Store",
            slug="onboarding-store",
        )
        assert store.status == StoreStatus.DRAFT

        # Update profile during onboarding is permitted
        update_store_profile(
            store_id=store.id,
            actor=users["owner"],
            description="Setting up my storefront before launch",
        )

        # Change slug during onboarding is permitted
        change_store_slug(
            store_id=store.id,
            actor=users["owner"],
            new_slug="onboarding-final-slug",
        )

        # But publishing is strictly blocked until merchant account is ACTIVE
        with pytest.raises(StorePublishError, match="must be in ACTIVE status"):
            publish_store(store_id=store.id, actor=users["owner"])

    def test_suspended_merchant_blocks_all_store_mutations(self, merchant, users):
        store = Store.objects.create(
            merchant=merchant,
            name="Frozen Store",
            slug="frozen-store",
            status=StoreStatus.DRAFT,
        )

        merchant.status = MerchantStatus.SUSPENDED
        merchant.save(update_fields=["status"])

        with pytest.raises(StorePermissionDeniedError):
            update_store_profile(store_id=store.id, actor=users["owner"], name="Suspended Name")

        with pytest.raises(StorePermissionDeniedError):
            change_store_slug(store_id=store.id, actor=users["owner"], new_slug="suspended-slug")

        with pytest.raises(StorePublishError, match="must be in ACTIVE status"):
            publish_store(store_id=store.id, actor=users["owner"])

    def test_inactive_merchant_blocks_all_store_mutations(self, merchant, users):
        store = Store.objects.create(
            merchant=merchant,
            name="Deactivated Store",
            slug="deactivated-store",
            status=StoreStatus.DRAFT,
        )

        merchant.status = MerchantStatus.INACTIVE
        merchant.save(update_fields=["status"])

        with pytest.raises(StorePermissionDeniedError):
            update_store_profile(store_id=store.id, actor=users["owner"], name="Inactive Name")

        with pytest.raises(StorePermissionDeniedError):
            change_store_slug(store_id=store.id, actor=users["owner"], new_slug="inactive-slug")

        with pytest.raises(StorePublishError, match="must be in ACTIVE status"):
            publish_store(store_id=store.id, actor=users["owner"])
