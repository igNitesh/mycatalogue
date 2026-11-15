import pytest
from django.contrib.auth import get_user_model

from apps.merchants.choices import MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.exceptions import SoleOwnerProtectionError
from apps.merchants.services import (
    add_member_to_merchant,
    change_membership_role,
    create_merchant,
    delete_membership,
    update_membership_status,
)

User = get_user_model()


@pytest.mark.django_db
class TestConcurrencyAndOwnershipProtection:
    """Test suite ensuring merchants cannot be stripped of their last active owner."""

    @pytest.fixture
    def owner_user(self):
        return User.objects.create_user(email="owner@example.com", password="Password123!")

    @pytest.fixture
    def second_user(self):
        return User.objects.create_user(email="second@example.com", password="Password123!")

    @pytest.fixture
    def merchant_and_owner(self, owner_user):
        merchant, membership = create_merchant(
            owner_user=owner_user,
            name="Sole Owner Store",
            email="sole@example.com",
            contact_number="9876543210",
            address="123 Street",
            city="Metropolis",
            state="Central",
            pin_code="110001",
        )
        return merchant, membership

    def test_merchant_creation_defaults(self, merchant_and_owner, owner_user):
        """Merchant is created in PENDING status, while initial owner is ACTIVE."""
        merchant, membership = merchant_and_owner
        assert merchant.status == MerchantStatus.PENDING
        assert membership.role == MembershipRole.OWNER
        assert membership.status == MembershipStatus.ACTIVE
        assert membership.user == owner_user

    def test_sole_owner_demotion_is_blocked(self, merchant_and_owner, owner_user):
        """Demoting the sole active owner raises SoleOwnerProtectionError."""
        merchant, _ = merchant_and_owner

        with pytest.raises(
            SoleOwnerProtectionError,
            match="Cannot demote the sole active owner",
        ):
            change_membership_role(
                merchant_id=merchant.id,
                actor_user=owner_user,
                target_user=owner_user,
                new_role=MembershipRole.ADMIN,
            )

    def test_sole_owner_suspension_and_revocation_is_blocked(self, merchant_and_owner, owner_user):
        """Suspending or revoking the sole active owner raises SoleOwnerProtectionError."""
        merchant, _ = merchant_and_owner

        with pytest.raises(
            SoleOwnerProtectionError,
            match="Cannot suspend or revoke the sole active owner",
        ):
            update_membership_status(
                merchant_id=merchant.id,
                actor_user=owner_user,
                target_user=owner_user,
                new_status=MembershipStatus.SUSPENDED,
            )

        with pytest.raises(
            SoleOwnerProtectionError,
            match="Cannot suspend or revoke the sole active owner",
        ):
            update_membership_status(
                merchant_id=merchant.id,
                actor_user=owner_user,
                target_user=owner_user,
                new_status=MembershipStatus.REVOKED,
            )

    def test_sole_owner_deletion_is_blocked(self, merchant_and_owner, owner_user):
        """Deleting the sole active owner raises SoleOwnerProtectionError."""
        merchant, _ = merchant_and_owner

        with pytest.raises(
            SoleOwnerProtectionError,
            match="Cannot delete the sole active owner",
        ):
            delete_membership(
                merchant_id=merchant.id,
                target_user=owner_user,
            )

    def test_mutation_allowed_when_multiple_active_owners_exist(
        self, merchant_and_owner, owner_user, second_user
    ):
        """When 2 active owners exist, 1 can be demoted or deleted, leaving 1 active owner."""
        merchant, _ = merchant_and_owner

        # Add second owner
        m2 = add_member_to_merchant(
            merchant_id=merchant.id,
            actor_user=owner_user,
            target_user=second_user,
            role=MembershipRole.OWNER,
        )
        assert m2.role == MembershipRole.OWNER

        # Demote first owner to Admin - succeeds because second_user remains active owner
        updated_m1 = change_membership_role(
            merchant_id=merchant.id,
            actor_user=second_user,
            target_user=owner_user,
            new_role=MembershipRole.ADMIN,
        )
        assert updated_m1.role == MembershipRole.ADMIN

        # Now second_user is the sole active owner; demoting them must fail
        with pytest.raises(SoleOwnerProtectionError):
            change_membership_role(
                merchant_id=merchant.id,
                actor_user=second_user,
                target_user=second_user,
                new_role=MembershipRole.MANAGER,
            )
