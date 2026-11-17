import pytest
from django.contrib.auth import get_user_model

from apps.merchants.choices import MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.permissions import (
    MerchantPermission,
    can_perform_merchant_action,
    has_role_permission,
)
from apps.merchants.services import add_member_to_merchant, create_merchant

User = get_user_model()


@pytest.mark.django_db
class TestAuthorizationMatrix:
    """Test suite verifying role permission mapping and decoupled operational status."""

    @pytest.fixture
    def users(self):
        return {
            "owner": User.objects.create_user(email="owner@test.com", password="Password123!"),
            "admin": User.objects.create_user(email="admin@test.com", password="Password123!"),
            "manager": User.objects.create_user(email="manager@test.com", password="Password123!"),
            "staff": User.objects.create_user(email="staff@test.com", password="Password123!"),
        }

    @pytest.fixture
    def memberships(self, users):
        merchant, owner_m = create_merchant(
            owner_user=users["owner"],
            name="Matrix Store",
            email="matrix@test.com",
            contact_number="1234567890",
            address="Addr",
            city="City",
            state="State",
            pin_code="100000",
        )
        merchant.status = MerchantStatus.ACTIVE
        merchant.save(update_fields=["status"])

        admin_m = add_member_to_merchant(
            merchant.id, users["owner"], users["admin"], MembershipRole.ADMIN
        )
        manager_m = add_member_to_merchant(
            merchant.id, users["owner"], users["manager"], MembershipRole.MANAGER
        )
        staff_m = add_member_to_merchant(
            merchant.id, users["owner"], users["staff"], MembershipRole.STAFF
        )

        return {
            "merchant": merchant,
            "owner": owner_m,
            "admin": admin_m,
            "manager": manager_m,
            "staff": staff_m,
        }

    def test_role_permission_hierarchy(self):
        """Verifies explicit permission assignments per role."""
        # OWNER
        assert has_role_permission(MembershipRole.OWNER, MerchantPermission.TRANSFER_OWNERSHIP)
        assert has_role_permission(MembershipRole.OWNER, MerchantPermission.MANAGE_BILLING)
        assert has_role_permission(MembershipRole.OWNER, MerchantPermission.VIEW_FULL_FINANCIALS)
        assert has_role_permission(MembershipRole.OWNER, MerchantPermission.MANAGE_CATALOGUE)

        # ADMIN
        assert not has_role_permission(MembershipRole.ADMIN, MerchantPermission.TRANSFER_OWNERSHIP)
        assert not has_role_permission(MembershipRole.ADMIN, MerchantPermission.MANAGE_BILLING)
        assert has_role_permission(MembershipRole.ADMIN, MerchantPermission.VIEW_FULL_FINANCIALS)
        assert has_role_permission(MembershipRole.ADMIN, MerchantPermission.MANAGE_MANAGERS)
        assert has_role_permission(MembershipRole.ADMIN, MerchantPermission.MANAGE_CATALOGUE)

        # MANAGER - limited financials (shift totals only)
        assert has_role_permission(
            MembershipRole.MANAGER, MerchantPermission.VIEW_OPERATIONAL_SALES
        )
        assert not has_role_permission(
            MembershipRole.MANAGER, MerchantPermission.VIEW_FULL_FINANCIALS
        )
        assert not has_role_permission(MembershipRole.MANAGER, MerchantPermission.MANAGE_MANAGERS)
        assert has_role_permission(MembershipRole.MANAGER, MerchantPermission.MANAGE_STAFF)
        assert has_role_permission(MembershipRole.MANAGER, MerchantPermission.MANAGE_CATALOGUE)

        # STAFF - storefront operations only
        assert has_role_permission(MembershipRole.STAFF, MerchantPermission.OPERATE_STOREFRONT)
        assert not has_role_permission(MembershipRole.STAFF, MerchantPermission.MANAGE_CATALOGUE)
        assert not has_role_permission(
            MembershipRole.STAFF, MerchantPermission.VIEW_OPERATIONAL_SALES
        )
        assert not has_role_permission(
            MembershipRole.STAFF, MerchantPermission.VIEW_FULL_FINANCIALS
        )

    def test_suspended_membership_denies_all_actions(self, memberships):
        """A member whose membership status is SUSPENDED cannot perform any action."""
        staff_m = memberships["staff"]
        staff_m.status = MembershipStatus.SUSPENDED
        staff_m.save(update_fields=["status"])

        assert not can_perform_merchant_action(staff_m, MerchantPermission.OPERATE_STOREFRONT)

    def test_suspended_merchant_blocks_storefront_but_permits_owner_billing(self, memberships):
        """When merchant is SUSPENDED, storefront operations are blocked, but OWNER can manage billing/transfer."""
        merchant = memberships["merchant"]
        merchant.status = MerchantStatus.SUSPENDED
        merchant.save(update_fields=["status"])

        memberships["staff"].refresh_from_db()
        memberships["owner"].refresh_from_db()

        # Operational storefront is blocked for all
        assert not can_perform_merchant_action(
            memberships["staff"], MerchantPermission.OPERATE_STOREFRONT
        )
        assert not can_perform_merchant_action(
            memberships["owner"], MerchantPermission.OPERATE_STOREFRONT
        )

        # Owner administrative resolution is allowed
        assert can_perform_merchant_action(memberships["owner"], MerchantPermission.MANAGE_BILLING)
        assert can_perform_merchant_action(
            memberships["owner"], MerchantPermission.TRANSFER_OWNERSHIP
        )

    def test_inactive_merchant_permits_only_owner_historical_review(self, memberships):
        """When merchant is INACTIVE, all operations are blocked except OWNER viewing historical financials."""
        merchant = memberships["merchant"]
        merchant.status = MerchantStatus.INACTIVE
        merchant.save(update_fields=["status"])

        memberships["owner"].refresh_from_db()

        assert not can_perform_merchant_action(
            memberships["owner"], MerchantPermission.OPERATE_STOREFRONT
        )
        assert not can_perform_merchant_action(
            memberships["owner"], MerchantPermission.MANAGE_BILLING
        )
        assert can_perform_merchant_action(
            memberships["owner"], MerchantPermission.VIEW_FULL_FINANCIALS
        )
