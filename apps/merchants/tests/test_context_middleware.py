import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest, HttpResponse

from apps.merchants.choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.context import ACTIVE_MERCHANT_SESSION_KEY
from apps.merchants.middleware import MerchantContextMiddleware
from apps.merchants.models import Merchant, MerchantMembership

User = get_user_model()


def get_response_ok(request: HttpRequest) -> HttpResponse:
    return HttpResponse("OK")


@pytest.fixture
def merchant_user(db):
    return User.objects.create_user(
        email="merchant.owner@example.com",
        password="ValidPassword123!",
        is_verified=True,
    )


@pytest.fixture
def merchant(db, merchant_user):
    m = Merchant.objects.create(
        name="Zenith Stores",
        email="zenith@example.com",
        contact_number="9876543210",
        address="100 Zenith Way",
        city="Mumbai",
        state="Maharashtra",
        pin_code="400001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )
    MerchantMembership.objects.create(
        user=merchant_user,
        merchant=m,
        role=MembershipRole.OWNER,
        status=MembershipStatus.ACTIVE,
    )
    return m


@pytest.mark.django_db
class TestMerchantContextMiddleware:
    def test_middleware_attaches_merchant_and_membership_for_authenticated_member(
        self, merchant_user, merchant
    ):
        request = HttpRequest()
        request.user = merchant_user

        # Add session
        session_mw = SessionMiddleware(lambda r: None)
        session_mw.process_request(request)
        request.session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant.id)
        request.session.save()

        middleware = MerchantContextMiddleware(get_response_ok)
        response = middleware(request)

        assert response.status_code == 200
        assert request.merchant == merchant
        assert request.membership.user == merchant_user
        assert request.membership.merchant == merchant

    def test_middleware_handles_anonymous_user(self):
        request = HttpRequest()
        request.user = None

        session_mw = SessionMiddleware(lambda r: None)
        session_mw.process_request(request)
        request.session.save()

        middleware = MerchantContextMiddleware(get_response_ok)
        response = middleware(request)

        assert response.status_code == 200
        assert request.merchant is None
        assert request.membership is None
