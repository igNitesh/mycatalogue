import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from apps.merchants.admin import MerchantMembershipAdmin
from apps.merchants.choices import MembershipRole
from apps.merchants.models import MerchantMembership
from apps.merchants.services import add_member_to_merchant, create_merchant

User = get_user_model()


@pytest.mark.django_db
class TestAdminProtection:
    """Test suite ensuring Django Admin cannot bypass sole owner protection rules."""

    @pytest.fixture
    def site(self):
        return AdminSite()

    @pytest.fixture
    def admin_class(self, site):
        return MerchantMembershipAdmin(MerchantMembership, site)

    @pytest.fixture
    def owner_user(self):
        return User.objects.create_user(email="admin.owner@example.com", password="Password123!")

    @pytest.fixture
    def second_user(self):
        return User.objects.create_user(email="admin.second@example.com", password="Password123!")

    @pytest.fixture
    def staff_user(self):
        return User.objects.create_user(
            email="staff.admin@example.com",
            password="StaffPassword123!",
            is_staff=True,
            is_superuser=True,
            is_verified=True,
        )

    @pytest.fixture
    def merchant_and_owner(self, owner_user):
        return create_merchant(
            owner_user=owner_user,
            name="Admin Protected Store",
            email="adminstore@example.com",
            contact_number="1234567890",
            address="Street",
            city="City",
            state="State",
            pin_code="100000",
        )

    def test_bulk_actions_are_disabled(self, admin_class):
        """MerchantMembershipAdmin disables bulk actions to prevent bypassing protected services."""
        assert admin_class.actions is None

    def test_admin_delete_model_blocks_sole_owner_deletion(
        self, admin_class, merchant_and_owner, staff_user
    ):
        """Admin delete_model raises ValidationError when attempting to delete the sole active owner."""
        _, membership = merchant_and_owner
        rf = RequestFactory()
        request = rf.post("/")
        request.user = staff_user
        # Add messages support to mock request
        from django.contrib.messages.storage.fallback import FallbackStorage

        request.session = {}
        request._messages = FallbackStorage(request)

        with pytest.raises(ValidationError, match="Cannot delete the sole active owner"):
            admin_class.delete_model(request, membership)

        assert MerchantMembership.objects.filter(pk=membership.pk).exists()

    def test_admin_delete_queryset_blocks_sole_owner_deletion(
        self, admin_class, merchant_and_owner, staff_user
    ):
        """Admin delete_queryset protects the sole active owner from deletion."""
        _, membership = merchant_and_owner
        rf = RequestFactory()
        request = rf.post("/")
        request.user = staff_user
        from django.contrib.messages.storage.fallback import FallbackStorage

        request.session = {}
        request._messages = FallbackStorage(request)

        qs = MerchantMembership.objects.filter(pk=membership.pk)
        admin_class.delete_queryset(request, qs)

        # Verification: membership was NOT deleted
        assert MerchantMembership.objects.filter(pk=membership.pk).exists()

    def test_admin_delete_model_allows_non_sole_owner_deletion(
        self, admin_class, merchant_and_owner, owner_user, second_user, staff_user
    ):
        """Admin delete_model allows deleting a staff member while keeping sole owner intact."""
        merchant, _ = merchant_and_owner
        staff_m = add_member_to_merchant(
            merchant_id=merchant.id,
            actor_user=owner_user,
            target_user=second_user,
            role=MembershipRole.STAFF,
        )

        rf = RequestFactory()
        request = rf.post("/")
        request.user = staff_user
        from django.contrib.messages.storage.fallback import FallbackStorage

        request.session = {}
        request._messages = FallbackStorage(request)

        admin_class.delete_model(request, staff_m)
        assert not MerchantMembership.objects.filter(pk=staff_m.pk).exists()
