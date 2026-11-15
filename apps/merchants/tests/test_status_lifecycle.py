import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from apps.merchants.choices import MembershipRole, MerchantStatus
from apps.merchants.services import (
    add_member_to_merchant,
    create_merchant,
    deactivate_merchant,
)

User = get_user_model()


@pytest.mark.django_db
class TestMerchantStatusLifecycle:
    """Test suite for Merchant lifecycle states and operational checks."""

    @pytest.fixture
    def owner(self):
        return User.objects.create_user(email="founder@example.com", password="Password123!")

    @pytest.fixture
    def staff(self):
        return User.objects.create_user(email="staff@example.com", password="Password123!")

    def test_default_status_is_pending(self, owner):
        """New merchants are created in PENDING status by default."""
        merchant, _ = create_merchant(
            owner_user=owner,
            name="Lifecycle Store",
            email="life@example.com",
            contact_number="1234567890",
            address="Road 1",
            city="City",
            state="State",
            pin_code="100000",
        )
        assert merchant.status == MerchantStatus.PENDING
        assert merchant.is_operational() is False

    def test_is_operational_only_when_active(self, owner):
        """is_operational is True only when status is strictly ACTIVE."""
        merchant, _ = create_merchant(
            owner_user=owner,
            name="Status Check Store",
            email="status@example.com",
            contact_number="1234567890",
            address="Road 2",
            city="City",
            state="State",
            pin_code="100000",
        )

        merchant.status = MerchantStatus.ACTIVE
        assert merchant.is_operational() is True

        merchant.status = MerchantStatus.SUSPENDED
        assert merchant.is_operational() is False

        merchant.status = MerchantStatus.INACTIVE
        assert merchant.is_operational() is False

    def test_deactivate_merchant(self, owner, staff):
        """Owner can soft-deactivate merchant to INACTIVE; non-owner cannot."""
        merchant, _ = create_merchant(
            owner_user=owner,
            name="Deactivate Store",
            email="deact@example.com",
            contact_number="1234567890",
            address="Road 3",
            city="City",
            state="State",
            pin_code="100000",
        )
        merchant.status = MerchantStatus.ACTIVE
        merchant.save(update_fields=["status"])

        add_member_to_merchant(
            merchant_id=merchant.id,
            actor_user=owner,
            target_user=staff,
            role=MembershipRole.STAFF,
        )

        # Staff attempt fails
        with pytest.raises(PermissionDenied):
            deactivate_merchant(merchant_id=merchant.id, actor_user=staff)

        # Owner succeeds
        updated_merchant = deactivate_merchant(merchant_id=merchant.id, actor_user=owner)
        assert updated_merchant.status == MerchantStatus.INACTIVE
        assert updated_merchant.is_operational() is False
