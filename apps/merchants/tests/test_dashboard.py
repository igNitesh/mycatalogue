import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.merchants.choices import BusinessType, MembershipStatus, MerchantStatus
from apps.merchants.context import ACTIVE_MERCHANT_SESSION_KEY
from apps.merchants.models import MerchantMembership
from apps.merchants.services import create_merchant
from apps.stores.choices import StoreStatus
from apps.stores.models import Store

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
def second_verified_user(db):
    return User.objects.create_user(
        email="other.founder@example.com",
        password="Password123!",
        is_verified=True,
        is_active=True,
    )


@pytest.fixture
def unverified_user(db):
    return User.objects.create_user(
        email="unverified@example.com",
        password="Password123!",
        is_verified=False,
        is_active=True,
    )


@pytest.fixture
def inactive_user(db):
    return User.objects.create_user(
        email="inactive@example.com",
        password="Password123!",
        is_verified=True,
        is_active=False,
    )


@pytest.fixture
def merchant_alpha(db, verified_user):
    merchant, _ = create_merchant(
        owner_user=verified_user,
        name="Alpha Commerce",
        email="alpha@example.com",
        contact_number="+91 9876543210",
        address="10 Alpha Street",
        city="Mumbai",
        state="Maharashtra",
        pin_code="400001",
        business_type=BusinessType.RETAIL,
    )
    return merchant


@pytest.fixture
def merchant_beta(db, verified_user):
    merchant, _ = create_merchant(
        owner_user=verified_user,
        name="Beta Logistics",
        email="beta@example.com",
        contact_number="+91 9876543211",
        address="20 Beta Blvd",
        city="Pune",
        state="Maharashtra",
        pin_code="411001",
        business_type=BusinessType.WHOLESALE,
    )
    return merchant


@pytest.mark.django_db
class TestDashboardAccessControl:
    """Verifies authentication, email verification, and merchant membership requirements."""

    def test_anonymous_user_redirected_to_login(self, client):
        url = reverse("merchants:dashboard")
        response = client.get(url)
        assert response.status_code == 302
        assert f"/auth/login/?next={url}" in response.url

    def test_unverified_user_redirected_to_verification_required(self, client, unverified_user):
        client.force_login(unverified_user)
        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 302
        assert response.url == reverse("users:verification_required")

    def test_inactive_user_access_denied(self, client, inactive_user):
        client.force_login(inactive_user)
        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 302

    def test_user_without_merchant_redirected_to_onboarding(self, client, verified_user):
        """A verified user with 0 merchant memberships is directed to onboarding."""
        client.force_login(verified_user)
        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 302
        assert response.url == reverse("merchants:onboarding")


@pytest.mark.django_db
class TestDashboardSingleAndMultiMerchantContext:
    """Verifies single merchant auto-selection, multi-merchant selection, and switching."""

    def test_user_with_single_merchant_automatically_enters_dashboard(
        self, client, verified_user, merchant_alpha
    ):
        """User with exactly 1 merchant directly loads the dashboard with auto-selected context."""
        client.force_login(verified_user)
        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Alpha Commerce" in content
        assert "Retail &amp; E-commerce" in content
        assert "Owner" in content
        assert "Overview" in content

    def test_user_with_multiple_merchants_shows_selector_when_no_session_selection(
        self, client, verified_user, merchant_alpha, merchant_beta
    ):
        """User with >1 merchants and no session key is shown the organization selector."""
        client.force_login(verified_user)
        # Ensure session has no active_merchant_id
        session = client.session
        if ACTIVE_MERCHANT_SESSION_KEY in session:
            del session[ACTIVE_MERCHANT_SESSION_KEY]
            session.save()

        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Select Business Organization" in content
        assert "Alpha Commerce" in content
        assert "Beta Logistics" in content
        assert "Enter Workspace" in content

    def test_user_with_multiple_merchants_enters_dashboard_when_session_selection_exists(
        self, client, verified_user, merchant_alpha, merchant_beta
    ):
        """When session selection is present, multi-merchant user enters selected dashboard directly."""
        client.force_login(verified_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_beta.id)
        session.save()

        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Beta Logistics" in content
        assert "Wholesale &amp; Distribution" in content

    def test_switching_merchant_via_post_updates_active_dashboard(
        self, client, verified_user, merchant_alpha, merchant_beta
    ):
        """POST to switch endpoint changes active dashboard context cleanly."""
        client.force_login(verified_user)
        # Set initial to alpha
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        # Switch to beta
        switch_url = reverse("merchants:switch")
        response = client.post(
            switch_url,
            data={"merchant_id": str(merchant_beta.id), "next": reverse("merchants:dashboard")},
        )
        assert response.status_code == 302
        assert response.url == reverse("merchants:dashboard")

        # Verify active dashboard is now Beta
        dash_response = client.get(reverse("merchants:dashboard"))
        assert dash_response.status_code == 200
        assert "Beta Logistics" in dash_response.content.decode()

    def test_revoked_or_suspended_membership_excluded_from_active_access(
        self, client, verified_user, merchant_alpha
    ):
        """A user whose membership is REVOKED or SUSPENDED cannot access the dashboard."""
        membership = MerchantMembership.objects.get(merchant=merchant_alpha, user=verified_user)
        membership.status = MembershipStatus.REVOKED
        membership.save(update_fields=["status"])

        client.force_login(verified_user)
        response = client.get(reverse("merchants:dashboard"))
        # 0 active memberships left -> redirected to onboarding
        assert response.status_code == 302
        assert response.url == reverse("merchants:onboarding")


@pytest.mark.django_db
class TestDashboardTenantIsolation:
    """Verifies that users cannot access or view other merchants' dashboards."""

    def test_cross_tenant_access_blocked(
        self, client, verified_user, second_verified_user, merchant_alpha
    ):
        """Second user cannot access Merchant Alpha's dashboard and cannot switch to it."""
        client.force_login(second_verified_user)

        # Attempt to forge session to merchant_alpha
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        # Middleware purges unauthorized session key; user has 0 memberships -> redirected to onboarding
        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 302
        assert response.url == reverse("merchants:onboarding")


@pytest.mark.django_db
class TestDashboardMerchantLifecycleStatus:
    """Verifies dashboard rendering across all merchant lifecycle states."""

    def test_pending_merchant_displays_setup_guidance(self, client, verified_user, merchant_alpha):
        """Pending merchant shows setup guidance, pending badge, and verification notice."""
        merchant_alpha.status = MerchantStatus.PENDING
        merchant_alpha.save(update_fields=["status"])

        client.force_login(verified_user)
        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Pending Verification" in content
        assert "Setup &amp; Verification Guidance" in content
        assert "Setup Checklist" in content
        assert "Business Organization Registered" in content

    def test_active_merchant_displays_operational_banner(
        self, client, verified_user, merchant_alpha
    ):
        """Active merchant shows active status badge and operational banner."""
        merchant_alpha.status = MerchantStatus.ACTIVE
        merchant_alpha.save(update_fields=["status"])

        client.force_login(verified_user)
        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Active Operational Standing" in content

    def test_suspended_merchant_displays_neutral_message(
        self, client, verified_user, merchant_alpha
    ):
        """Suspended merchant shows exact neutral message without assuming billing."""
        merchant_alpha.status = MerchantStatus.SUSPENDED
        merchant_alpha.save(update_fields=["status"])

        client.force_login(verified_user)
        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Suspended" in content
        assert (
            "Your business account is currently suspended. Some features are unavailable. "
            "Please contact platform support for assistance."
        ) in content

    def test_inactive_merchant_displays_inactive_notice(
        self, client, verified_user, merchant_alpha
    ):
        """Inactive merchant displays inactive notice."""
        merchant_alpha.status = MerchantStatus.INACTIVE
        merchant_alpha.save(update_fields=["status"])

        client.force_login(verified_user)
        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Account Inactive" in content
        assert "This business organization is currently inactive." in content


@pytest.mark.django_db
class TestDashboardStorefrontStatus:
    """Verifies storefront presentation and is_publicly_accessible enforcement."""

    def test_store_absent_displays_empty_state(self, client, verified_user, merchant_alpha):
        """When merchant has no store, displays clean empty state without crashing."""
        client.force_login(verified_user)
        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "No Storefront Created Yet" in content
        assert "Storefront setup will be available in Store Management." in content

    def test_store_draft_displays_status_and_offline_notice(
        self, client, verified_user, merchant_alpha
    ):
        """Store in DRAFT displays store name and draft status; no public link."""
        Store.objects.create(
            merchant=merchant_alpha,
            name="Alpha Boutique",
            slug="alpha-boutique",
            status=StoreStatus.DRAFT,
        )
        client.force_login(verified_user)
        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Alpha Boutique" in content
        assert "/s/alpha-boutique/" in content
        assert "Draft" in content
        assert "Public storefront is offline" in content

    def test_store_published_with_active_merchant_displays_public_link(
        self, client, verified_user, merchant_alpha
    ):
        """Published store with ACTIVE merchant displays active public storefront link."""
        merchant_alpha.status = MerchantStatus.ACTIVE
        merchant_alpha.save(update_fields=["status"])

        Store.objects.create(
            merchant=merchant_alpha,
            name="Alpha Boutique",
            slug="alpha-boutique",
            status=StoreStatus.PUBLISHED,
        )
        client.force_login(verified_user)
        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Alpha Boutique" in content
        assert "Published" in content
        assert "View Public Storefront" in content
        assert "/s/alpha-boutique/" in content

    def test_store_published_with_suspended_merchant_is_not_publicly_accessible(
        self, client, verified_user, merchant_alpha
    ):
        """Published store with SUSPENDED merchant does not show public link as accessible."""
        merchant_alpha.status = MerchantStatus.SUSPENDED
        merchant_alpha.save(update_fields=["status"])

        store = Store.objects.create(
            merchant=merchant_alpha,
            name="Alpha Boutique",
            slug="alpha-boutique",
            status=StoreStatus.PUBLISHED,
        )
        assert store.is_publicly_accessible is False

        client.force_login(verified_user)
        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "View Public Storefront" not in content
        assert "Public storefront is offline" in content


@pytest.mark.django_db
class TestDashboardNavigationAndSidebarRestrictions:
    """Verifies that only Overview is functional and other sidebar links are visibly disabled."""

    def test_overview_is_functional_and_upcoming_entries_disabled(
        self, client, verified_user, merchant_alpha
    ):
        client.force_login(verified_user)
        response = client.get(reverse("merchants:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()

        # Overview link is active
        assert 'href="/merchants/dashboard/"' in content
        assert "Overview" in content

        # Store Settings link is active in Task 008
        assert 'href="/merchants/store/"' in content
        assert "Store Settings" in content

        # Remaining upcoming modules are visibly disabled with Soon badges
        for disabled_entry in [
            "Products",
            "Categories",
            "Orders",
            "Customers",
            "Settings",
        ]:
            assert disabled_entry in content
            assert "cursor-not-allowed" in content
            assert "Soon" in content

    def test_public_navbar_displays_dashboard_link_for_merchant_users(
        self, client, verified_user, merchant_alpha
    ):
        """Public navigation shows Dashboard link only for verified users with merchant memberships."""
        client.force_login(verified_user)
        response = client.get(reverse("core:index"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Dashboard" in content

    def test_public_navbar_hides_dashboard_link_for_users_without_merchants(
        self, client, second_verified_user
    ):
        """User with no merchant memberships does not see the Dashboard link."""
        client.force_login(second_verified_user)
        response = client.get(reverse("core:index"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Register your business" in content
        # "Dashboard" should not be rendered in navigation
        assert ">Dashboard<" not in content
