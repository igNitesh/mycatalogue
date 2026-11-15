import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.merchants.choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.context import ACTIVE_MERCHANT_SESSION_KEY
from apps.merchants.models import Merchant, MerchantMembership

User = get_user_model()


@pytest.fixture
def member_user(db):
    return User.objects.create_user(
        email="multi.owner@example.com",
        password="ValidPassword123!",
        is_verified=True,
    )


@pytest.fixture
def merchant_one(db, member_user):
    m = Merchant.objects.create(
        name="Merchant One",
        email="one@example.com",
        contact_number="9876543210",
        address="1 First St",
        city="Mumbai",
        state="MH",
        pin_code="400001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )
    MerchantMembership.objects.create(
        user=member_user,
        merchant=m,
        role=MembershipRole.OWNER,
        status=MembershipStatus.ACTIVE,
    )
    return m


@pytest.fixture
def merchant_two(db, member_user):
    m = Merchant.objects.create(
        name="Merchant Two",
        email="two@example.com",
        contact_number="9876543211",
        address="2 Second St",
        city="Pune",
        state="MH",
        pin_code="411001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )
    MerchantMembership.objects.create(
        user=member_user,
        merchant=m,
        role=MembershipRole.ADMIN,
        status=MembershipStatus.ACTIVE,
    )
    return m


@pytest.fixture
def unassociated_merchant(db):
    return Merchant.objects.create(
        name="Unassociated Org",
        email="unassoc@example.com",
        contact_number="9876543219",
        address="9 Ninth St",
        city="Nagpur",
        state="MH",
        pin_code="440001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )


@pytest.mark.django_db
class TestSwitchMerchantView:
    def test_get_method_is_not_allowed(self, member_user):
        client = Client()
        client.force_login(member_user)

        url = reverse("merchants:switch")
        response = client.get(url)
        assert response.status_code == 405

    def test_csrf_enforcement_blocks_post_without_token(self, member_user, merchant_one):
        # Explicit CSRF enforcement
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(member_user)

        url = reverse("merchants:switch")
        # Direct POST without providing CSRF cookie/token
        response = csrf_client.post(url, {"merchant_id": str(merchant_one.id)})
        assert response.status_code == 403

    def test_successful_switch_with_csrf_token(self, member_user, merchant_one, merchant_two):
        client = Client(enforce_csrf_checks=True)
        client.force_login(member_user)

        # Establish initial session on merchant_one
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_one.id)
        session.save()

        url = reverse("merchants:switch")

        # Get CSRF token by accessing any page or using test client
        # In Django test client with enforce_csrf_checks=True, client.post with follow / csrf client
        # retrieves token
        client.get(reverse("core:index"))  # sets csrf cookie
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            url,
            {"merchant_id": str(merchant_two.id), "csrfmiddlewaretoken": csrf_token},
            follow=True,
        )

        assert response.status_code == 200
        assert client.session[ACTIVE_MERCHANT_SESSION_KEY] == str(merchant_two.id)
        # Check flash message
        messages = list(response.context["messages"])
        assert any("Merchant Two" in str(m) for m in messages)

    def test_switch_to_unauthorized_merchant_fails_and_preserves_previous_session(
        self, member_user, merchant_one, unassociated_merchant
    ):
        client = Client(enforce_csrf_checks=True)
        client.force_login(member_user)

        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_one.id)
        session.save()

        client.get(reverse("core:index"))
        csrf_token = client.cookies["csrftoken"].value

        url = reverse("merchants:switch")
        response = client.post(
            url,
            {"merchant_id": str(unassociated_merchant.id), "csrfmiddlewaretoken": csrf_token},
            follow=True,
        )

        assert response.status_code == 200
        # Invariant: session MUST preserve the original selection
        assert client.session[ACTIVE_MERCHANT_SESSION_KEY] == str(merchant_one.id)
        messages = list(response.context["messages"])
        assert any("do not have active access" in str(m) for m in messages)

    def test_switch_rejects_open_redirect_attempts(self, member_user, merchant_one, merchant_two):
        client = Client()
        client.force_login(member_user)

        url = reverse("merchants:switch")
        response = client.post(
            url,
            {
                "merchant_id": str(merchant_two.id),
                "next": "https://evil-phishing-site.com/steal-creds",
            },
        )
        assert response.status_code == 302
        # Must redirect safely to core:index instead of external malicious target
        assert response.url == reverse("core:index")
