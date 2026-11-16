from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.merchants.choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.context import ACTIVE_MERCHANT_SESSION_KEY
from apps.merchants.models import Merchant, MerchantMembership
from apps.merchants.services import create_merchant

User = get_user_model()


@pytest.fixture
def verified_user(db):
    return User.objects.create_user(
        email="verified.founder@example.com",
        password="Password123!",
        is_verified=True,
        is_active=True,
    )


@pytest.fixture
def unverified_user(db):
    return User.objects.create_user(
        email="unverified.founder@example.com",
        password="Password123!",
        is_verified=False,
        is_active=True,
    )


@pytest.fixture
def inactive_user(db):
    return User.objects.create_user(
        email="inactive.founder@example.com",
        password="Password123!",
        is_verified=True,
        is_active=False,
    )


@pytest.fixture
def second_verified_user(db):
    return User.objects.create_user(
        email="other.founder@example.com",
        password="Password123!",
        is_verified=True,
        is_active=True,
    )


@pytest.fixture
def valid_onboarding_payload():
    return {
        "name": "Apex Global Ventures",
        "business_type": BusinessType.RETAIL,
        "description": "High quality curated consumer lifestyle goods.",
        "email": "contact@apexventures.com",
        "contact_number": "+91 9876543210",
        "address": "404 Innovation Tower, Tech District",
        "city": "Bengaluru",
        "state": "Karnataka",
        "pin_code": "560001",
    }


@pytest.mark.django_db
class TestMerchantOnboardingAccessControl:
    """Verifies authentication, verification, and active account access requirements."""

    def test_anonymous_user_redirected_to_login(self, client):
        url = reverse("merchants:onboarding")
        response = client.get(url)
        assert response.status_code == 302
        assert f"/auth/login/?next={url}" in response.url

    def test_anonymous_user_post_redirected_to_login(self, client, valid_onboarding_payload):
        url = reverse("merchants:onboarding")
        response = client.post(url, data=valid_onboarding_payload)
        assert response.status_code == 302
        assert f"/auth/login/?next={url}" in response.url

    def test_unverified_user_redirected_to_verification_required(self, client, unverified_user):
        client.force_login(unverified_user)
        url = reverse("merchants:onboarding")
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse("users:verification_required")

    def test_unverified_user_post_redirected_to_verification_required(
        self, client, unverified_user, valid_onboarding_payload
    ):
        client.force_login(unverified_user)
        url = reverse("merchants:onboarding")
        response = client.post(url, data=valid_onboarding_payload)
        assert response.status_code == 302
        assert response.url == reverse("users:verification_required")
        assert not Merchant.objects.filter(name=valid_onboarding_payload["name"]).exists()

    def test_inactive_user_access_denied(self, client, inactive_user):
        client.force_login(inactive_user)
        url = reverse("merchants:onboarding")
        response = client.get(url)
        # LoginRequiredMixin / Authentication redirects inactive or unauthenticated session
        assert response.status_code == 302


@pytest.mark.django_db
class TestMerchantOnboardingCreation:
    """Verifies form presentation, submission, atomicity, and invariant enforcement."""

    def test_get_onboarding_form_success(self, client, verified_user):
        client.force_login(verified_user)
        url = reverse("merchants:onboarding")
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert "Register Your Business" in content
        assert "Select business type" in content
        assert verified_user.email in content
        assert "Pending Verification" in content
        # Session token initialized
        assert "onboarding_form_token" in client.session

    def test_valid_submission_creates_pending_merchant_and_active_owner(
        self, client, verified_user, valid_onboarding_payload
    ):
        client.force_login(verified_user)
        # 1. GET to seed form token in session
        client.get(reverse("merchants:onboarding"))
        token = client.session["onboarding_form_token"]

        payload = {**valid_onboarding_payload, "form_token": token}
        response = client.post(reverse("merchants:onboarding"), data=payload)

        # Expect redirect to onboarding_success
        merchant = Merchant.objects.get(name=valid_onboarding_payload["name"])
        assert response.status_code == 302
        assert response.url == reverse(
            "merchants:onboarding_success", kwargs={"merchant_id": merchant.id}
        )

        # Invariant checks:
        assert merchant.status == MerchantStatus.PENDING
        assert merchant.email == "contact@apexventures.com"
        assert merchant.business_type == BusinessType.RETAIL
        assert merchant.city == "Bengaluru"

        # Owner membership verification:
        membership = MerchantMembership.objects.get(merchant=merchant, user=verified_user)
        assert membership.role == MembershipRole.OWNER
        assert membership.status == MembershipStatus.ACTIVE

        # Session context verification:
        assert client.session.get(ACTIVE_MERCHANT_SESSION_KEY) == str(merchant.id)
        assert client.session.get("onboarding_merchant_id") == str(merchant.id)

    def test_context_establishment_failure_does_not_repeat_or_rollback_creation(
        self, client, verified_user, valid_onboarding_payload
    ):
        """If session context assignment fails, merchant remains created and view recovers gracefully."""
        client.force_login(verified_user)
        client.get(reverse("merchants:onboarding"))
        token = client.session["onboarding_form_token"]
        payload = {**valid_onboarding_payload, "form_token": token}

        with patch(
            "apps.merchants.views.set_active_merchant", side_effect=Exception("Session lock failed")
        ):
            response = client.post(reverse("merchants:onboarding"), data=payload)

        # Merchant is still persisted!
        merchant = Merchant.objects.get(name=valid_onboarding_payload["name"])
        assert response.status_code == 302
        assert response.url == reverse(
            "merchants:onboarding_success", kwargs={"merchant_id": merchant.id}
        )
        assert merchant.status == MerchantStatus.PENDING
        assert MerchantMembership.objects.filter(
            merchant=merchant, user=verified_user, role=MembershipRole.OWNER
        ).exists()

    def test_tampering_with_status_or_role_is_ignored(
        self, client, verified_user, second_verified_user, valid_onboarding_payload
    ):
        """Browser cannot inject status=ACTIVE, role=ADMIN, or cross-user owner IDs."""
        client.force_login(verified_user)
        client.get(reverse("merchants:onboarding"))
        token = client.session["onboarding_form_token"]

        malicious_payload = {
            **valid_onboarding_payload,
            "form_token": token,
            "status": MerchantStatus.ACTIVE,
            "role": MembershipRole.ADMIN,
            "owner_user": str(second_verified_user.id),
            "owner_id": str(second_verified_user.id),
        }
        response = client.post(reverse("merchants:onboarding"), data=malicious_payload)
        assert response.status_code == 302

        merchant = Merchant.objects.get(name=valid_onboarding_payload["name"])
        # Status MUST remain PENDING
        assert merchant.status == MerchantStatus.PENDING

        # Membership MUST belong to verified_user as OWNER
        assert MerchantMembership.objects.filter(
            merchant=merchant, user=verified_user, role=MembershipRole.OWNER
        ).exists()
        assert not MerchantMembership.objects.filter(
            merchant=merchant, user=second_verified_user
        ).exists()

    def test_multiple_merchant_creation_by_same_user(
        self, client, verified_user, valid_onboarding_payload
    ):
        """A user can intentionally register multiple businesses; each becomes active upon creation."""
        client.force_login(verified_user)

        # First merchant
        client.get(reverse("merchants:onboarding"))
        payload_1 = {
            **valid_onboarding_payload,
            "name": "First Venture",
            "form_token": client.session["onboarding_form_token"],
        }
        client.post(reverse("merchants:onboarding"), data=payload_1)
        m1 = Merchant.objects.get(name="First Venture")
        assert client.session.get(ACTIVE_MERCHANT_SESSION_KEY) == str(m1.id)

        # Second merchant
        client.get(reverse("merchants:onboarding"))
        payload_2 = {
            **valid_onboarding_payload,
            "name": "Second Venture",
            "form_token": client.session["onboarding_form_token"],
        }
        client.post(reverse("merchants:onboarding"), data=payload_2)
        m2 = Merchant.objects.get(name="Second Venture")

        # Both exist with verified_user as Owner
        assert MerchantMembership.objects.filter(
            user=verified_user, merchant=m1, role=MembershipRole.OWNER
        ).exists()
        assert MerchantMembership.objects.filter(
            user=verified_user, merchant=m2, role=MembershipRole.OWNER
        ).exists()
        # Active context switched to the newly created merchant
        assert client.session.get(ACTIVE_MERCHANT_SESSION_KEY) == str(m2.id)


@pytest.mark.django_db
class TestMerchantOnboardingFormValidation:
    """Verifies field requirements, placeholder rejection, and sanitization."""

    def test_missing_mandatory_fields_rejected(self, client, verified_user):
        client.force_login(verified_user)
        client.get(reverse("merchants:onboarding"))
        token = client.session["onboarding_form_token"]

        response = client.post(
            reverse("merchants:onboarding"),
            data={"form_token": token},
        )
        assert response.status_code == 200
        form = response.context["form"]
        assert "name" in form.errors
        assert "business_type" in form.errors
        assert "email" in form.errors
        assert "contact_number" in form.errors
        assert "address" in form.errors
        assert "city" in form.errors
        assert "state" in form.errors
        assert "pin_code" in form.errors

    def test_placeholder_business_type_rejected(
        self, client, verified_user, valid_onboarding_payload
    ):
        """Placeholder empty value cannot be submitted as business type."""
        client.force_login(verified_user)
        client.get(reverse("merchants:onboarding"))
        token = client.session["onboarding_form_token"]

        payload = {**valid_onboarding_payload, "business_type": "", "form_token": token}
        response = client.post(reverse("merchants:onboarding"), data=payload)
        assert response.status_code == 200
        form = response.context["form"]
        assert "business_type" in form.errors

    def test_invalid_contact_number_rejected(self, client, verified_user, valid_onboarding_payload):
        client.force_login(verified_user)
        client.get(reverse("merchants:onboarding"))
        token = client.session["onboarding_form_token"]

        payload = {**valid_onboarding_payload, "contact_number": "123", "form_token": token}
        response = client.post(reverse("merchants:onboarding"), data=payload)
        assert response.status_code == 200
        form = response.context["form"]
        assert "contact_number" in form.errors

    def test_invalid_email_format_rejected(self, client, verified_user, valid_onboarding_payload):
        client.force_login(verified_user)
        client.get(reverse("merchants:onboarding"))
        token = client.session["onboarding_form_token"]

        payload = {**valid_onboarding_payload, "email": "not-an-email", "form_token": token}
        response = client.post(reverse("merchants:onboarding"), data=payload)
        assert response.status_code == 200
        form = response.context["form"]
        assert "email" in form.errors


@pytest.mark.django_db
class TestDuplicateSubmissionMitigation:
    """Verifies that duplicate form submissions with the same token do not create duplicate merchants."""

    def test_duplicate_submission_redirects_safely(
        self, client, verified_user, valid_onboarding_payload
    ):
        client.force_login(verified_user)
        client.get(reverse("merchants:onboarding"))
        token = client.session["onboarding_form_token"]
        payload = {**valid_onboarding_payload, "form_token": token}

        # First submission succeeds
        resp1 = client.post(reverse("merchants:onboarding"), data=payload)
        assert resp1.status_code == 302
        merchant = Merchant.objects.get(name=valid_onboarding_payload["name"])

        # Second rapid submission with same token is intercepted
        resp2 = client.post(reverse("merchants:onboarding"), data=payload)
        assert resp2.status_code == 302
        # Redirected to existing onboarding confirmation
        assert resp2.url == reverse(
            "merchants:onboarding_success", kwargs={"merchant_id": merchant.id}
        )

        # Only 1 merchant was created
        assert Merchant.objects.filter(name=valid_onboarding_payload["name"]).count() == 1


@pytest.mark.django_db
class TestMerchantOnboardingSuccessView:
    """Verifies confirmation screen, ownership enforcement, and IDOR protection."""

    def test_success_view_renders_for_valid_onboarding(
        self, client, verified_user, valid_onboarding_payload
    ):
        client.force_login(verified_user)
        client.get(reverse("merchants:onboarding"))
        token = client.session["onboarding_form_token"]
        client.post(
            reverse("merchants:onboarding"),
            data={**valid_onboarding_payload, "form_token": token},
        )
        merchant = Merchant.objects.get(name=valid_onboarding_payload["name"])

        url = reverse("merchants:onboarding_success", kwargs={"merchant_id": merchant.id})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert "Business Registration Complete!" in content
        assert "Pending Verification" in content
        assert merchant.name in content
        assert "Retail &amp; E-commerce" in content
        assert "Owner (Active)" in content
        assert "Registration does not mean commercial activation" in content

    def test_success_view_rejects_manipulated_merchant_id(
        self, client, verified_user, second_verified_user, valid_onboarding_payload
    ):
        """User cannot inspect another merchant's confirmation by changing the URL UUID."""
        # Create merchant for other user
        other_merchant, _ = create_merchant(
            owner_user=second_verified_user,
            name="Confidential Competitor Corp",
            email="secret@competitor.com",
            contact_number="9999999999",
            address="Private Road",
            city="Pune",
            state="Maharashtra",
            pin_code="411001",
        )

        # Login as verified_user
        client.force_login(verified_user)
        # Attempt to access other_merchant's confirmation
        url = reverse("merchants:onboarding_success", kwargs={"merchant_id": other_merchant.id})

        # Should raise PermissionDenied (403)
        response = client.get(url)
        assert response.status_code == 403

    def test_success_view_denied_without_onboarding_session_key(self, client, verified_user):
        """Direct access to confirmation URL without onboarding in the current session is denied."""
        merchant, _ = create_merchant(
            owner_user=verified_user,
            name="Pre-existing Merchant",
            email="old@example.com",
            contact_number="9999999999",
            address="Old Street",
            city="Delhi",
            state="Delhi",
            pin_code="110001",
        )
        client.force_login(verified_user)
        url = reverse("merchants:onboarding_success", kwargs={"merchant_id": merchant.id})

        response = client.get(url)
        assert response.status_code == 403


@pytest.mark.django_db
class TestOnboardingNavigationLinks:
    """Verifies dynamic navigation link in base template based on merchant ownership status."""

    def test_anonymous_user_does_not_see_registration_link(self, client):
        response = client.get(reverse("core:index"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Register your business" not in content
        assert "Add another business" not in content

    def test_verified_user_without_merchant_sees_register_your_business(
        self, client, verified_user
    ):
        client.force_login(verified_user)
        response = client.get(reverse("core:index"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Register your business" in content
        assert "Add another business" not in content

    def test_verified_user_with_merchant_sees_add_another_business(self, client, verified_user):
        create_merchant(
            owner_user=verified_user,
            name="Existing Enterprise",
            email="existing@enterprise.com",
            contact_number="9876543210",
            address="Office 1",
            city="Mumbai",
            state="MH",
            pin_code="400001",
        )
        client.force_login(verified_user)
        response = client.get(reverse("core:index"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Add another business" in content
