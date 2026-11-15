import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest

from apps.merchants.choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.context import (
    ACTIVE_MERCHANT_SESSION_KEY,
    clear_active_merchant,
    get_user_merchant_memberships,
    resolve_merchant_context,
    set_active_merchant,
)
from apps.merchants.exceptions import InvalidMerchantSelectionError
from apps.merchants.models import Merchant, MerchantMembership

User = get_user_model()


def create_mock_request(user=None, session_data=None):
    request = HttpRequest()
    request.user = user
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    if session_data:
        for k, v in session_data.items():
            request.session[k] = v
    return request


@pytest.fixture
def test_user(db):
    return User.objects.create_user(
        email="merchant.user@example.com",
        password="ValidPassword123!",
        is_verified=True,
    )


@pytest.fixture
def second_user(db):
    return User.objects.create_user(
        email="second.user@example.com",
        password="ValidPassword123!",
        is_verified=True,
    )


@pytest.fixture
def merchant_alpha(db):
    return Merchant.objects.create(
        name="Alpha Stores",
        email="alpha@example.com",
        contact_number="9876543210",
        address="Alpha Street",
        city="Mumbai",
        state="Maharashtra",
        pin_code="400001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )


@pytest.fixture
def merchant_beta(db):
    return Merchant.objects.create(
        name="Beta Outlets",
        email="beta@example.com",
        contact_number="9876543211",
        address="Beta Road",
        city="Pune",
        state="Maharashtra",
        pin_code="411001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )


@pytest.mark.django_db
class TestMerchantContextServices:
    def test_anonymous_and_inactive_user_resolution(self):
        # Anonymous
        req_anon = create_mock_request(user=None)
        merchant, membership = resolve_merchant_context(req_anon)
        assert merchant is None
        assert membership is None

        # Inactive user
        inactive_user = User(email="inactive@example.com", is_active=False)
        req_inactive = create_mock_request(user=inactive_user)
        merchant, membership = resolve_merchant_context(req_inactive)
        assert merchant is None
        assert membership is None

    def test_zero_active_memberships_returns_none(self, test_user):
        request = create_mock_request(user=test_user)
        merchant, membership = resolve_merchant_context(request)
        assert merchant is None
        assert membership is None
        assert ACTIVE_MERCHANT_SESSION_KEY not in request.session

    def test_single_active_membership_auto_selects(self, test_user, merchant_alpha):
        membership_record = MerchantMembership.objects.create(
            user=test_user,
            merchant=merchant_alpha,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )

        request = create_mock_request(user=test_user)
        merchant, membership = resolve_merchant_context(request)

        assert merchant == merchant_alpha
        assert membership == membership_record
        assert request.session[ACTIVE_MERCHANT_SESSION_KEY] == str(merchant_alpha.id)

    def test_multiple_active_memberships_without_session_returns_none(
        self, test_user, merchant_alpha, merchant_beta
    ):
        MerchantMembership.objects.create(
            user=test_user,
            merchant=merchant_alpha,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
        MerchantMembership.objects.create(
            user=test_user,
            merchant=merchant_beta,
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
        )

        request = create_mock_request(user=test_user)
        merchant, membership = resolve_merchant_context(request)

        # Invariant: Must NOT auto-select when multiple exist!
        assert merchant is None
        assert membership is None
        assert ACTIVE_MERCHANT_SESSION_KEY not in request.session

    def test_multiple_active_memberships_with_valid_session_resolves(
        self, test_user, merchant_alpha, merchant_beta
    ):
        m1 = MerchantMembership.objects.create(
            user=test_user,
            merchant=merchant_alpha,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
        MerchantMembership.objects.create(
            user=test_user,
            merchant=merchant_beta,
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
        )

        request = create_mock_request(
            user=test_user,
            session_data={ACTIVE_MERCHANT_SESSION_KEY: str(merchant_alpha.id)},
        )
        merchant, membership = resolve_merchant_context(request)

        assert merchant == merchant_alpha
        assert membership == m1

    def test_stale_session_membership_suspended_or_revoked_purges_session(
        self, test_user, merchant_alpha, merchant_beta
    ):
        MerchantMembership.objects.create(
            user=test_user,
            merchant=merchant_alpha,
            role=MembershipRole.OWNER,
            status=MembershipStatus.SUSPENDED,  # Suspended!
        )
        m_beta = MerchantMembership.objects.create(
            user=test_user,
            merchant=merchant_beta,
            role=MembershipRole.STAFF,
            status=MembershipStatus.ACTIVE,  # Exactly 1 active remaining!
        )

        request = create_mock_request(
            user=test_user,
            session_data={ACTIVE_MERCHANT_SESSION_KEY: str(merchant_alpha.id)},
        )
        merchant, membership = resolve_merchant_context(request)

        # Stale session for alpha purged, and because beta is now the only active membership, beta auto-selects!
        assert merchant == merchant_beta
        assert membership == m_beta
        assert request.session[ACTIVE_MERCHANT_SESSION_KEY] == str(merchant_beta.id)

    def test_stale_session_membership_deleted_purges_session(self, test_user, merchant_alpha):
        # Session references alpha, but user has NO active memberships
        request = create_mock_request(
            user=test_user,
            session_data={ACTIVE_MERCHANT_SESSION_KEY: str(merchant_alpha.id)},
        )
        merchant, membership = resolve_merchant_context(request)

        assert merchant is None
        assert membership is None
        assert ACTIVE_MERCHANT_SESSION_KEY not in request.session

    def test_set_active_merchant_success_and_idempotency(
        self, test_user, merchant_alpha, merchant_beta
    ):
        MerchantMembership.objects.create(
            user=test_user,
            merchant=merchant_alpha,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
        m_beta = MerchantMembership.objects.create(
            user=test_user,
            merchant=merchant_beta,
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
        )

        request = create_mock_request(
            user=test_user,
            session_data={ACTIVE_MERCHANT_SESSION_KEY: str(merchant_alpha.id)},
        )

        # Switch to Beta
        res_membership = set_active_merchant(request, merchant_beta.id)
        assert res_membership == m_beta
        assert request.session[ACTIVE_MERCHANT_SESSION_KEY] == str(merchant_beta.id)
        assert request.merchant == merchant_beta

        # Idempotent re-set does not dirty session
        request.session.modified = False
        set_active_merchant(request, merchant_beta.id)
        assert request.session.modified is False

    def test_set_active_merchant_failure_preserves_previous_session(
        self, test_user, second_user, merchant_alpha, merchant_beta
    ):
        # User belongs only to Alpha
        MerchantMembership.objects.create(
            user=test_user,
            merchant=merchant_alpha,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
        # Second user belongs to Beta
        MerchantMembership.objects.create(
            user=second_user,
            merchant=merchant_beta,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )

        request = create_mock_request(
            user=test_user,
            session_data={ACTIVE_MERCHANT_SESSION_KEY: str(merchant_alpha.id)},
        )

        # Attempt to switch to unauthorized merchant_beta
        with pytest.raises(InvalidMerchantSelectionError):
            set_active_merchant(request, merchant_beta.id)

        # Invariant: Previous session must be preserved intact!
        assert request.session[ACTIVE_MERCHANT_SESSION_KEY] == str(merchant_alpha.id)

        # Attempt with malformed UUID
        with pytest.raises(InvalidMerchantSelectionError):
            set_active_merchant(request, "not-a-valid-uuid")
        assert request.session[ACTIVE_MERCHANT_SESSION_KEY] == str(merchant_alpha.id)

    def test_set_active_merchant_unauthenticated_fails(self, merchant_alpha):
        req_anon = create_mock_request(user=None)
        with pytest.raises(PermissionDenied):
            set_active_merchant(req_anon, merchant_alpha.id)

    def test_clear_active_merchant(self, test_user, merchant_alpha):
        request = create_mock_request(
            user=test_user,
            session_data={ACTIVE_MERCHANT_SESSION_KEY: str(merchant_alpha.id)},
        )
        request.merchant = merchant_alpha
        clear_active_merchant(request)

        assert ACTIVE_MERCHANT_SESSION_KEY not in request.session
        assert request.merchant is None
        assert request.membership is None

    def test_get_user_merchant_memberships_selector(
        self, test_user, second_user, merchant_alpha, merchant_beta
    ):
        # Alpha active, Beta suspended
        m_alpha = MerchantMembership.objects.create(
            user=test_user,
            merchant=merchant_alpha,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
        MerchantMembership.objects.create(
            user=test_user,
            merchant=merchant_beta,
            role=MembershipRole.STAFF,
            status=MembershipStatus.SUSPENDED,
        )

        memberships = list(get_user_merchant_memberships(test_user))
        assert len(memberships) == 1
        assert memberships[0] == m_alpha

        # Anonymous or None user
        assert list(get_user_merchant_memberships(None)) == []
