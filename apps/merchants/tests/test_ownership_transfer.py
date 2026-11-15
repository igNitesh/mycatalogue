import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError

from apps.merchants.choices import MembershipRole, MembershipStatus
from apps.merchants.models import MerchantOwnershipTransferLog
from apps.merchants.services import (
    add_member_to_merchant,
    create_merchant,
    transfer_ownership,
    update_membership_status,
)

User = get_user_model()


@pytest.mark.django_db
class TestOwnershipTransfer:
    """Test suite for atomic merchant ownership transfer and audit trail logging."""

    @pytest.fixture
    def owner_user(self):
        return User.objects.create_user(email="original.owner@example.com", password="Password123!")

    @pytest.fixture
    def target_user(self):
        return User.objects.create_user(email="successor@example.com", password="Password123!")

    @pytest.fixture
    def unrelated_user(self):
        return User.objects.create_user(email="unrelated@example.com", password="Password123!")

    @pytest.fixture
    def merchant(self, owner_user, target_user):
        merchant, _ = create_merchant(
            owner_user=owner_user,
            name="Transfer Test Store",
            email="transfer@example.com",
            contact_number="9876543210",
            address="100 Grand Way",
            city="Metropolis",
            state="Central",
            pin_code="110001",
        )
        add_member_to_merchant(
            merchant_id=merchant.id,
            actor_user=owner_user,
            target_user=target_user,
            role=MembershipRole.ADMIN,
        )
        return merchant

    def test_successful_ownership_transfer(self, merchant, owner_user, target_user):
        """Owner transfers ownership to target user; target becomes OWNER, owner demoted to ADMIN."""
        target_m, actor_m, log_entry = transfer_ownership(
            merchant_id=merchant.id,
            actor_user=owner_user,
            target_user=target_user,
            demote_actor_to=MembershipRole.ADMIN,
        )

        assert target_m.role == MembershipRole.OWNER
        assert actor_m.role == MembershipRole.ADMIN

        # Verify audit record
        assert isinstance(log_entry, MerchantOwnershipTransferLog)
        assert log_entry.merchant == merchant
        assert log_entry.previous_owner == owner_user
        assert log_entry.new_owner == target_user
        assert log_entry.transferred_by == owner_user
        assert log_entry.transferred_at is not None

        # Verify in DB
        assert MerchantOwnershipTransferLog.objects.filter(merchant=merchant).count() == 1

    def test_non_owner_cannot_initiate_transfer(self, merchant, target_user, unrelated_user):
        """A user who is not an active owner cannot initiate an ownership transfer."""
        with pytest.raises(
            PermissionDenied,
            match="Requesting user is not an active owner",
        ):
            transfer_ownership(
                merchant_id=merchant.id,
                actor_user=target_user,  # target_user is ADMIN, not OWNER
                target_user=unrelated_user,
            )

    def test_transfer_to_non_member_fails(self, merchant, owner_user, unrelated_user):
        """Attempting to transfer ownership to a user without membership fails."""
        with pytest.raises(
            ValidationError,
            match="Target user does not have a membership",
        ):
            transfer_ownership(
                merchant_id=merchant.id,
                actor_user=owner_user,
                target_user=unrelated_user,
            )

    def test_transfer_to_suspended_member_fails(self, merchant, owner_user, target_user):
        """Target user must have an active membership to receive ownership."""
        update_membership_status(
            merchant_id=merchant.id,
            actor_user=owner_user,
            target_user=target_user,
            new_status=MembershipStatus.SUSPENDED,
        )

        with pytest.raises(
            ValidationError,
            match="Target user must have an active membership",
        ):
            transfer_ownership(
                merchant_id=merchant.id,
                actor_user=owner_user,
                target_user=target_user,
            )

    def test_transfer_to_self_fails(self, merchant, owner_user):
        """Owner cannot transfer ownership to themselves."""
        with pytest.raises(ValidationError, match="Cannot transfer ownership to yourself"):
            transfer_ownership(
                merchant_id=merchant.id,
                actor_user=owner_user,
                target_user=owner_user,
            )
