import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import ProtectedError

from apps.merchants.choices import MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.models import (
    Merchant,
    MerchantMembership,
    MerchantOwnershipTransferLog,
)

User = get_user_model()


@pytest.mark.django_db
class TestMerchantModels:
    """Test suite for Merchant and MerchantMembership model layer."""

    @pytest.fixture
    def user_a(self):
        return User.objects.create_user(email="usera@example.com", password="Password123!")

    @pytest.fixture
    def user_b(self):
        return User.objects.create_user(email="userb@example.com", password="Password123!")

    def test_uuid_primary_keys(self, user_a):
        """Verifies UUID primary keys are generated for Merchant, Membership, and AuditLog."""
        merchant = Merchant.objects.create(
            name="Alpha Retailers",
            email="alpha@example.com",
            contact_number="9876543210",
            address="123 High Street",
            city="Metropolis",
            state="Central",
            pin_code="110001",
        )
        assert isinstance(merchant.id, uuid.UUID)
        assert merchant.status == MerchantStatus.PENDING

        membership = MerchantMembership.objects.create(
            user=user_a,
            merchant=merchant,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
        assert isinstance(membership.id, uuid.UUID)

        log = MerchantOwnershipTransferLog.objects.create(
            merchant=merchant,
            previous_owner=user_a,
            new_owner=user_a,
            transferred_by=user_a,
        )
        assert isinstance(log.id, uuid.UUID)

    def test_duplicate_membership_rejected_by_database_constraint(self, user_a):
        """A user cannot hold duplicate memberships in the same merchant."""
        merchant = Merchant.objects.create(
            name="Beta Mart",
            email="beta@example.com",
            contact_number="1234567890",
            address="456 Market Road",
            city="Metropolis",
            state="Central",
            pin_code="110002",
        )

        MerchantMembership.objects.create(
            user=user_a,
            merchant=merchant,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )

        with pytest.raises(IntegrityError):
            MerchantMembership.objects.create(
                user=user_a,
                merchant=merchant,
                role=MembershipRole.STAFF,
                status=MembershipStatus.ACTIVE,
            )

    def test_many_to_many_relationships(self, user_a, user_b):
        """One user can belong to multiple merchants; one merchant can have multiple users."""
        merchant_1 = Merchant.objects.create(
            name="Store 1",
            email="store1@example.com",
            contact_number="1111111111",
            address="Addr 1",
            city="City",
            state="State",
            pin_code="100001",
        )
        merchant_2 = Merchant.objects.create(
            name="Store 2",
            email="store2@example.com",
            contact_number="2222222222",
            address="Addr 2",
            city="City",
            state="State",
            pin_code="100002",
        )

        # User A belongs to both merchants
        m1 = MerchantMembership.objects.create(
            user=user_a,
            merchant=merchant_1,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
        m2 = MerchantMembership.objects.create(
            user=user_a,
            merchant=merchant_2,
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
        )

        # Merchant 1 has both User A and User B
        m3 = MerchantMembership.objects.create(
            user=user_b,
            merchant=merchant_1,
            role=MembershipRole.STAFF,
            status=MembershipStatus.ACTIVE,
        )

        assert user_a.merchant_memberships.count() == 2
        assert merchant_1.memberships.count() == 2
        assert set(merchant_1.memberships.all()) == {m1, m3}
        assert set(user_a.merchant_memberships.all()) == {m1, m2}

    def test_protect_on_delete_user_prevents_cascading_membership_destruction(self, user_a):
        """Deleting a User directly raises ProtectedError if they hold memberships."""
        merchant = Merchant.objects.create(
            name="Protected Store",
            email="protect@example.com",
            contact_number="9999999999",
            address="Main St",
            city="City",
            state="State",
            pin_code="100000",
        )
        MerchantMembership.objects.create(
            user=user_a,
            merchant=merchant,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )

        with pytest.raises(ProtectedError):
            user_a.delete()
