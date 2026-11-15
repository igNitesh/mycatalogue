import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.views.generic import View

from apps.merchants.choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.decorators import merchant_permission_required, merchant_required
from apps.merchants.exceptions import NoActiveMerchantError
from apps.merchants.mixins import MerchantPermissionRequiredMixin
from apps.merchants.models import Merchant, MerchantMembership
from apps.merchants.permissions import MerchantPermission

User = get_user_model()


def dummy_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse(f"Allowed for {request.merchant.name}")


@pytest.fixture
def users(db):
    return {
        "owner": User.objects.create_user(
            email="owner@test.com", password="Pass123!Valid", is_verified=True
        ),
        "admin": User.objects.create_user(
            email="admin@test.com", password="Pass123!Valid", is_verified=True
        ),
        "manager": User.objects.create_user(
            email="manager@test.com", password="Pass123!Valid", is_verified=True
        ),
        "staff": User.objects.create_user(
            email="staff@test.com", password="Pass123!Valid", is_verified=True
        ),
        "stranger": User.objects.create_user(
            email="stranger@test.com", password="Pass123!Valid", is_verified=True
        ),
    }


@pytest.fixture
def merchant(db, users):
    m = Merchant.objects.create(
        name="Horizon Enterprises",
        email="horizon@example.com",
        contact_number="9876543210",
        address="1 Horizon Way",
        city="Mumbai",
        state="Maharashtra",
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
    return m


@pytest.mark.django_db
class TestMerchantDecoratorsAndMixins:
    def test_merchant_required_unauthenticated_redirects_to_login(self):
        decorated = merchant_required(dummy_view)
        request = HttpRequest()
        request.user = AnonymousUser()
        request.path = "/dashboard/protected/"

        response = decorated(request)
        assert response.status_code == 302
        assert "/auth/login/" in response.url
        assert "next=/dashboard/protected/" in response.url

    def test_merchant_required_no_merchant_context_raises_or_redirects(self, users):
        decorated_redirect = merchant_required(dummy_view, redirect_url="/merchants/select/")
        request = HttpRequest()
        request.user = users["stranger"]
        request.merchant = None
        request.membership = None

        response = decorated_redirect(request)
        assert response.status_code == 302
        assert response.url == "/merchants/select/"

        # Raise exception version
        decorated_raise = merchant_required(dummy_view, raise_exception=True)
        with pytest.raises(NoActiveMerchantError):
            decorated_raise(request)

    def test_merchant_required_allows_access_regardless_of_merchant_lifecycle_status(
        self, users, merchant
    ):
        membership = merchant.memberships.get(user=users["owner"])
        decorated = merchant_required(dummy_view)

        for status in [
            MerchantStatus.ACTIVE,
            MerchantStatus.PENDING,
            MerchantStatus.SUSPENDED,
            MerchantStatus.INACTIVE,
        ]:
            merchant.status = status
            merchant.save(update_fields=["status"])

            request = HttpRequest()
            request.user = users["owner"]
            request.merchant = merchant
            request.membership = membership

            response = decorated(request)
            assert response.status_code == 200
            assert "Horizon Enterprises" in response.content.decode()

    def test_merchant_permission_required_role_enforcement(self, users, merchant):
        store_view = merchant_permission_required(MerchantPermission.MANAGE_STORE)(dummy_view)

        # OWNER and ADMIN allowed
        for authorized_role in ["owner", "admin"]:
            request = HttpRequest()
            request.user = users[authorized_role]
            request.merchant = merchant
            request.membership = merchant.memberships.get(user=users[authorized_role])

            response = store_view(request)
            assert response.status_code == 200

        # MANAGER and STAFF denied
        for denied_role in ["manager", "staff"]:
            request = HttpRequest()
            request.user = users[denied_role]
            request.merchant = merchant
            request.membership = merchant.memberships.get(user=users[denied_role])

            with pytest.raises(PermissionDenied):
                store_view(request)

    def test_merchant_permission_required_lifecycle_enforcement(self, users, merchant):
        # 1. PENDING merchant: MANAGE_STORE allowed, but PUBLISH_STORE denied
        merchant.status = MerchantStatus.PENDING
        merchant.save(update_fields=["status"])

        owner_req = HttpRequest()
        owner_req.user = users["owner"]
        owner_req.merchant = merchant
        owner_req.membership = merchant.memberships.get(user=users["owner"])

        manage_view = merchant_permission_required(MerchantPermission.MANAGE_STORE)(dummy_view)
        assert manage_view(owner_req).status_code == 200

        publish_view = merchant_permission_required(MerchantPermission.PUBLISH_STORE)(dummy_view)
        with pytest.raises(PermissionDenied):
            publish_view(owner_req)

        # 2. SUSPENDED merchant: MANAGE_STORE denied, MANAGE_BILLING allowed for owner
        merchant.status = MerchantStatus.SUSPENDED
        merchant.save(update_fields=["status"])

        with pytest.raises(PermissionDenied):
            manage_view(owner_req)

        billing_view = merchant_permission_required(MerchantPermission.MANAGE_BILLING)(dummy_view)
        assert billing_view(owner_req).status_code == 200

        # 3. INACTIVE merchant: MANAGE_BILLING denied, VIEW_FULL_FINANCIALS allowed for owner
        merchant.status = MerchantStatus.INACTIVE
        merchant.save(update_fields=["status"])

        with pytest.raises(PermissionDenied):
            billing_view(owner_req)

        tax_view = merchant_permission_required(MerchantPermission.VIEW_FULL_FINANCIALS)(dummy_view)
        assert tax_view(owner_req).status_code == 200

    def test_class_based_view_mixins(self, users, merchant):
        class SecureView(MerchantPermissionRequiredMixin, View):
            required_permission = MerchantPermission.MANAGE_STORE

            def get(self, request, *args, **kwargs):
                ctx = self.get_context_data()
                return HttpResponse(f"Context: {ctx['active_merchant'].name}")

        view = SecureView.as_view()

        # Valid Owner
        req = HttpRequest()
        req.method = "GET"
        req.user = users["owner"]
        req.merchant = merchant
        req.membership = merchant.memberships.get(user=users["owner"])
        response = view(req)
        assert response.status_code == 200
        assert "Horizon Enterprises" in response.content.decode()

        # Denied Staff
        req_staff = HttpRequest()
        req_staff.method = "GET"
        req_staff.user = users["staff"]
        req_staff.merchant = merchant
        req_staff.membership = merchant.memberships.get(user=users["staff"])
        with pytest.raises(PermissionDenied):
            view(req_staff)
