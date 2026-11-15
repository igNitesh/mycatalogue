import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest

from apps.merchants.choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.context import (
    ACTIVE_MERCHANT_SESSION_KEY,
    resolve_merchant_context,
    set_active_merchant,
)
from apps.merchants.decorators import merchant_required
from apps.merchants.exceptions import InvalidMerchantSelectionError, NoActiveMerchantError
from apps.merchants.models import Merchant, MerchantMembership

User = get_user_model()


def protected_tenant_view(request):
    return f"Accessed {request.merchant.name}"


@pytest.fixture
def platform_staff_user(db):
    return User.objects.create_user(
        email="platform.admin@mycatalogue.internal",
        password="StaffPassword123!",
        is_staff=True,
        is_superuser=True,
        is_verified=True,
    )


@pytest.fixture
def tenant_a_owner(db):
    return User.objects.create_user(
        email="owner.a@example.com",
        password="TenantPassword123!",
        is_verified=True,
    )


@pytest.fixture
def tenant_b_owner(db):
    return User.objects.create_user(
        email="owner.b@example.com",
        password="TenantPassword123!",
        is_verified=True,
    )


@pytest.fixture
def merchant_a(db, tenant_a_owner):
    m = Merchant.objects.create(
        name="Merchant A Org",
        email="merch.a@example.com",
        contact_number="9876543210",
        address="100 Tenant A Road",
        city="Mumbai",
        state="MH",
        pin_code="400001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )
    MerchantMembership.objects.create(
        user=tenant_a_owner,
        merchant=m,
        role=MembershipRole.OWNER,
        status=MembershipStatus.ACTIVE,
    )
    return m


@pytest.fixture
def merchant_b(db, tenant_b_owner):
    m = Merchant.objects.create(
        name="Merchant B Org",
        email="merch.b@example.com",
        contact_number="9876543211",
        address="200 Tenant B Road",
        city="Pune",
        state="MH",
        pin_code="411001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )
    MerchantMembership.objects.create(
        user=tenant_b_owner,
        merchant=m,
        role=MembershipRole.OWNER,
        status=MembershipStatus.ACTIVE,
    )
    return m


@pytest.mark.django_db
class TestTenantIsolation:
    def test_platform_staff_without_membership_cannot_resolve_merchant_context(
        self, platform_staff_user, merchant_a
    ):
        request = HttpRequest()
        request.user = platform_staff_user

        session_mw = SessionMiddleware(lambda r: None)
        session_mw.process_request(request)
        # Attempt to inject merchant_a into platform staff session
        request.session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_a.id)
        request.session.save()

        merchant, membership = resolve_merchant_context(request)

        # Invariant: Platform staff without membership must NOT resolve tenant context
        assert merchant is None
        assert membership is None
        # Stale/unauthorized session key must be purged
        assert ACTIVE_MERCHANT_SESSION_KEY not in request.session

    def test_cross_tenant_session_tampering_is_blocked_and_purged(
        self, tenant_b_owner, merchant_a, merchant_b
    ):
        request = HttpRequest()
        request.user = tenant_b_owner

        session_mw = SessionMiddleware(lambda r: None)
        session_mw.process_request(request)
        # Tenant B owner tampers session to pretend to be in Merchant A
        request.session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_a.id)
        request.session.save()

        merchant, membership = resolve_merchant_context(request)

        # Tenant B owner has 1 valid membership (Merchant B), so tampered A is rejected and B is resolved!
        assert merchant == merchant_b
        assert membership.merchant == merchant_b
        assert request.session[ACTIVE_MERCHANT_SESSION_KEY] == str(merchant_b.id)

    def test_cross_tenant_explicit_switch_is_rejected(self, tenant_b_owner, merchant_a, merchant_b):
        request = HttpRequest()
        request.user = tenant_b_owner

        session_mw = SessionMiddleware(lambda r: None)
        session_mw.process_request(request)
        request.session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_b.id)
        request.session.save()

        # Tenant B attempts to set active merchant to A
        with pytest.raises(InvalidMerchantSelectionError):
            set_active_merchant(request, merchant_a.id)

        # Previous session preserved
        assert request.session[ACTIVE_MERCHANT_SESSION_KEY] == str(merchant_b.id)

    def test_merchant_required_blocks_user_without_tenant_membership(self, platform_staff_user):
        decorated = merchant_required(protected_tenant_view, raise_exception=True)
        request = HttpRequest()
        request.user = platform_staff_user
        request.merchant = None
        request.membership = None

        with pytest.raises(NoActiveMerchantError):
            decorated(request)
