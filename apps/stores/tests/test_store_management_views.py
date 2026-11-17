import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.merchants.choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.context import ACTIVE_MERCHANT_SESSION_KEY
from apps.merchants.models import MerchantMembership
from apps.merchants.services import create_merchant
from apps.stores.choices import StoreStatus
from apps.stores.models import Store
from apps.stores.services import create_store

User = get_user_model()


def make_test_image(
    format_name: str = "PNG",
    size: tuple[int, int] = (100, 100),
    color: str = "blue",
) -> SimpleUploadedFile:
    """Generate an in-memory test image file using Pillow."""
    buffer = io.BytesIO()
    image = Image.new("RGB", size, color=color)
    image.save(buffer, format=format_name)
    buffer.seek(0)
    ext = "jpg" if format_name.upper() == "JPEG" else format_name.lower()
    return SimpleUploadedFile(
        f"test.{ext}",
        buffer.read(),
        content_type=f"image/{ext}",
    )


@pytest.fixture
def owner_user(db):
    return User.objects.create_user(
        email="store.owner@example.com",
        password="ValidPassword123!",
        is_verified=True,
        is_active=True,
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="store.admin@example.com",
        password="ValidPassword123!",
        is_verified=True,
        is_active=True,
    )


@pytest.fixture
def manager_user(db):
    return User.objects.create_user(
        email="store.manager@example.com",
        password="ValidPassword123!",
        is_verified=True,
        is_active=True,
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        email="store.staff@example.com",
        password="ValidPassword123!",
        is_verified=True,
        is_active=True,
    )


@pytest.fixture
def unverified_user(db):
    return User.objects.create_user(
        email="store.unverified@example.com",
        password="ValidPassword123!",
        is_verified=False,
        is_active=True,
    )


@pytest.fixture
def merchant_alpha(db, owner_user, admin_user, manager_user, staff_user):
    merchant, _ = create_merchant(
        owner_user=owner_user,
        name="Alpha Corporation",
        business_type=BusinessType.RETAIL,
        contact_number="+91 9876543210",
        email="alpha@example.com",
        address="100 Market St",
        city="Mumbai",
        state="Maharashtra",
        pin_code="400001",
    )
    # Activate merchant
    merchant.status = MerchantStatus.ACTIVE
    merchant.save()

    # Assign roles
    MerchantMembership.objects.create(
        user=admin_user,
        merchant=merchant,
        role=MembershipRole.ADMIN,
        status=MembershipStatus.ACTIVE,
    )
    MerchantMembership.objects.create(
        user=manager_user,
        merchant=merchant,
        role=MembershipRole.MANAGER,
        status=MembershipStatus.ACTIVE,
    )
    MerchantMembership.objects.create(
        user=staff_user,
        merchant=merchant,
        role=MembershipRole.STAFF,
        status=MembershipStatus.ACTIVE,
    )
    return merchant


@pytest.fixture
def merchant_beta(db):
    user = User.objects.create_user(
        email="beta.owner@example.com",
        password="ValidPassword123!",
        is_verified=True,
    )
    merchant, _ = create_merchant(
        owner_user=user,
        name="Beta Logistics",
        business_type=BusinessType.WHOLESALE,
        contact_number="+91 9876543211",
        email="beta@example.com",
        address="200 Freight Rd",
        city="Pune",
        state="Maharashtra",
        pin_code="411001",
    )
    merchant.status = MerchantStatus.ACTIVE
    merchant.save()
    merchant.owner_user = user
    return merchant


@pytest.fixture
def store_alpha(db, merchant_alpha, owner_user):
    return create_store(
        merchant_id=merchant_alpha.id,
        actor=owner_user,
        name="Alpha Goods",
        slug="alpha-goods",
        description="Quality retail goods.",
    )


@pytest.mark.django_db
class TestStoreSettingsAccessControl:
    """Verifies authentication, email verification, and role permissions."""

    def test_unauthenticated_user_redirected_to_login(self, client):
        response = client.get(reverse("merchants:store_settings"))
        assert response.status_code == 302
        assert "/auth/login/" in response.url

    def test_unverified_user_redirected_to_verification_required(self, client, unverified_user):
        client.force_login(unverified_user)
        response = client.get(reverse("merchants:store_settings"))
        assert response.status_code == 302
        assert response.url == reverse("users:verification_required")

    def test_user_without_merchant_redirected_to_dashboard(self, client, owner_user):
        user_no_merchant = User.objects.create_user(
            email="nomerchant@example.com",
            password="Password123!",
            is_verified=True,
        )
        client.force_login(user_no_merchant)
        response = client.get(reverse("merchants:store_settings"))
        assert response.status_code == 302
        assert response.url == reverse("merchants:dashboard")

    def test_owner_granted_access(self, client, owner_user, merchant_alpha, store_alpha):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.get(reverse("merchants:store_settings"))
        assert response.status_code == 200
        assert "Alpha Goods" in response.content.decode()

    def test_admin_granted_access(self, client, admin_user, merchant_alpha, store_alpha):
        client.force_login(admin_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.get(reverse("merchants:store_settings"))
        assert response.status_code == 200

    def test_manager_denied_access(self, client, manager_user, merchant_alpha, store_alpha):
        client.force_login(manager_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.get(reverse("merchants:store_settings"))
        assert response.status_code == 403

    def test_staff_denied_access(self, client, staff_user, merchant_alpha, store_alpha):
        client.force_login(staff_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.get(reverse("merchants:store_settings"))
        assert response.status_code == 403

    def test_suspended_merchant_owner_denied_store_management(
        self, client, owner_user, merchant_alpha, store_alpha
    ):
        merchant_alpha.status = MerchantStatus.SUSPENDED
        merchant_alpha.save()

        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.get(reverse("merchants:store_settings"))
        assert response.status_code == 403


@pytest.mark.django_db
class TestStoreCreationWorkflow:
    """Verifies store creation interface when merchant has no store."""

    def test_get_renders_create_form_when_no_store(self, client, owner_user, merchant_alpha):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.get(reverse("merchants:store_settings"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Create Digital Storefront" in content
        assert "Public URL Slug" in content

    def test_post_creates_store_successfully(self, client, owner_user, merchant_alpha):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        logo_file = make_test_image("PNG", (150, 150))
        cover_file = make_test_image("JPEG", (600, 200))

        response = client.post(
            reverse("merchants:store_settings"),
            data={
                "name": "Alpha New Store",
                "slug": "alpha-new-store",
                "description": "Our brand new store",
                "logo": logo_file,
                "cover_image": cover_file,
            },
        )
        assert response.status_code == 302
        assert response.url == reverse("merchants:store_settings")

        store = Store.objects.get(merchant=merchant_alpha)
        assert store.name == "Alpha New Store"
        assert store.slug == "alpha-new-store"
        assert store.status == StoreStatus.DRAFT
        assert store.logo
        assert store.cover_image

    def test_post_fails_with_duplicate_slug(
        self, client, owner_user, merchant_alpha, merchant_beta
    ):
        # Create an existing store for beta
        create_store(
            merchant_id=merchant_beta.id,
            actor=merchant_beta.owner_user,
            name="Existing Beta Store",
            slug="shared-slug",
        )

        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.post(
            reverse("merchants:store_settings"),
            data={
                "name": "Alpha Store",
                "slug": "shared-slug",
            },
        )
        assert response.status_code == 200
        assert "already taken" in response.content.decode()
        assert not Store.objects.filter(merchant=merchant_alpha).exists()

    def test_post_fails_with_reserved_slug(self, client, owner_user, merchant_alpha):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.post(
            reverse("merchants:store_settings"),
            data={
                "name": "Alpha Store",
                "slug": "admin",
            },
        )
        assert response.status_code == 200
        assert "reserved" in response.content.decode()


@pytest.mark.django_db
class TestStoreProfileUpdatesAndMediaValidation:
    """Verifies store profile editing, image validation, file size limits, and cleanup."""

    def test_post_updates_name_and_description(
        self, client, owner_user, merchant_alpha, store_alpha
    ):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.post(
            reverse("merchants:store_settings"),
            data={
                "name": "Alpha Goods Updated",
                "description": "Updated description text.",
            },
        )
        assert response.status_code == 302
        store_alpha.refresh_from_db()
        assert store_alpha.name == "Alpha Goods Updated"
        assert store_alpha.description == "Updated description text."

    def test_post_rejects_oversized_logo(self, client, owner_user, merchant_alpha, store_alpha):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        # Create a dummy file exceeding 2 MB
        oversized_data = b"x" * (2 * 1024 * 1024 + 500)
        oversized_file = SimpleUploadedFile(
            "large_logo.png", oversized_data, content_type="image/png"
        )

        response = client.post(
            reverse("merchants:store_settings"),
            data={
                "name": store_alpha.name,
                "logo": oversized_file,
            },
        )
        assert response.status_code == 200
        assert "exceeds the 2 MB limit" in response.content.decode()

    def test_post_rejects_oversized_cover_image(
        self, client, owner_user, merchant_alpha, store_alpha
    ):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        # Create a dummy file exceeding 5 MB
        oversized_data = b"x" * (5 * 1024 * 1024 + 500)
        oversized_file = SimpleUploadedFile(
            "large_cover.jpg", oversized_data, content_type="image/jpeg"
        )

        response = client.post(
            reverse("merchants:store_settings"),
            data={
                "name": store_alpha.name,
                "cover_image": oversized_file,
            },
        )
        assert response.status_code == 200
        assert "exceeds the 5 MB limit" in response.content.decode()

    def test_post_rejects_corrupted_image_file(
        self, client, owner_user, merchant_alpha, store_alpha
    ):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        # Corrupted header / invalid bytes disguised as PNG
        corrupt_file = SimpleUploadedFile(
            "corrupt.png", b"\x89PNG\r\n\x1a\nNotAnImageBytes", content_type="image/png"
        )

        response = client.post(
            reverse("merchants:store_settings"),
            data={
                "name": store_alpha.name,
                "logo": corrupt_file,
            },
        )
        assert response.status_code == 200
        assert "not a valid or readable image file" in response.content.decode()

    def test_post_rejects_unsupported_image_format(
        self, client, owner_user, merchant_alpha, store_alpha
    ):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        # Valid GIF image (format is GIF, not JPEG/PNG/WebP)
        gif_file = make_test_image("GIF", (50, 50))

        response = client.post(
            reverse("merchants:store_settings"),
            data={
                "name": store_alpha.name,
                "logo": gif_file,
            },
        )
        assert response.status_code == 200
        assert "Unsupported image format" in response.content.decode()

    def test_post_clear_logo_and_cover(self, client, owner_user, merchant_alpha, store_alpha):
        store_alpha.logo = make_test_image("PNG")
        store_alpha.cover_image = make_test_image("JPEG")
        store_alpha.save()

        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.post(
            reverse("merchants:store_settings"),
            data={
                "name": store_alpha.name,
                "clear_logo": True,
                "clear_cover_image": True,
            },
        )
        assert response.status_code == 302
        store_alpha.refresh_from_db()
        assert not store_alpha.logo
        assert not store_alpha.cover_image


@pytest.mark.django_db
class TestStoreSlugManagement:
    """Verifies slug change endpoint, confirmation requirement, and HTMX checks."""

    def test_post_change_slug_with_confirmation_succeeds(
        self, client, owner_user, merchant_alpha, store_alpha
    ):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.post(
            reverse("merchants:store_change_slug"),
            data={
                "slug": "alpha-brand-new",
                "confirm_slug_change": True,
            },
        )
        assert response.status_code == 302
        store_alpha.refresh_from_db()
        assert store_alpha.slug == "alpha-brand-new"

    def test_post_change_slug_without_confirmation_fails(
        self, client, owner_user, merchant_alpha, store_alpha
    ):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.post(
            reverse("merchants:store_change_slug"),
            data={
                "slug": "alpha-brand-new",
                # missing confirm_slug_change
            },
        )
        assert response.status_code == 200
        assert "previously shared links" in response.content.decode()
        store_alpha.refresh_from_db()
        assert store_alpha.slug == "alpha-goods"

    def test_post_change_slug_collision_fails(
        self, client, owner_user, merchant_alpha, store_alpha, merchant_beta
    ):
        create_store(
            merchant_id=merchant_beta.id,
            actor=merchant_beta.owner_user,
            name="Beta Store",
            slug="beta-store",
        )

        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.post(
            reverse("merchants:store_change_slug"),
            data={
                "slug": "beta-store",
                "confirm_slug_change": True,
            },
        )
        assert response.status_code == 200
        assert "already taken" in response.content.decode()

    def test_htmx_slug_check_endpoint(self, client, owner_user, merchant_alpha, store_alpha):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        # Available slug
        res1 = client.get(
            reverse("merchants:store_check_slug"),
            {"slug": "available-unique-slug"},
        )
        assert res1.status_code == 200
        assert "Slug is available" in res1.content.decode()

        # Own current slug (excluded from conflict check)
        res2 = client.get(
            reverse("merchants:store_check_slug"),
            {"slug": "alpha-goods"},
        )
        assert res2.status_code == 200
        assert "Slug is available" in res2.content.decode()

        # Reserved slug
        res3 = client.get(
            reverse("merchants:store_check_slug"),
            {"slug": "admin"},
        )
        assert res3.status_code == 200
        assert "reserved" in res3.content.decode()

        # Invalid slug characters
        res4 = client.get(
            reverse("merchants:store_check_slug"),
            {"slug": "invalid_slug_with_underscores"},
        )
        assert res4.status_code == 200
        assert "only lowercase letters" in res4.content.decode()


@pytest.mark.django_db
class TestStorePublishingControlsAndPublicAccess:
    """Verifies publish and unpublish transitions and public visibility invariants."""

    def test_publish_store_when_merchant_active_succeeds(
        self, client, owner_user, merchant_alpha, store_alpha
    ):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        # Initially DRAFT
        assert store_alpha.status == StoreStatus.DRAFT

        # Public storefront is initially 404
        public_url = reverse("stores:public_detail", kwargs={"slug": store_alpha.slug})
        pub_res = client.get(public_url)
        assert pub_res.status_code == 404

        # Publish store
        response = client.post(
            reverse("merchants:store_publish_toggle"),
            data={"action": "publish"},
        )
        assert response.status_code == 302
        store_alpha.refresh_from_db()
        assert store_alpha.status == StoreStatus.PUBLISHED

        # Now public storefront returns 200
        pub_res = client.get(public_url)
        assert pub_res.status_code == 200
        assert "Alpha Goods" in pub_res.content.decode()

    def test_unpublish_store_succeeds(self, client, owner_user, merchant_alpha, store_alpha):
        store_alpha.status = StoreStatus.PUBLISHED
        store_alpha.save()

        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.post(
            reverse("merchants:store_publish_toggle"),
            data={"action": "unpublish"},
        )
        assert response.status_code == 302
        store_alpha.refresh_from_db()
        assert store_alpha.status == StoreStatus.UNPUBLISHED

        # Public storefront returns 404 after unpublish
        public_url = reverse("stores:public_detail", kwargs={"slug": store_alpha.slug})
        pub_res = client.get(public_url)
        assert pub_res.status_code == 404

    def test_publish_store_when_merchant_is_pending_is_rejected(
        self, client, owner_user, merchant_alpha, store_alpha
    ):
        merchant_alpha.status = MerchantStatus.PENDING
        merchant_alpha.save()

        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.post(
            reverse("merchants:store_publish_toggle"),
            data={"action": "publish"},
        )
        assert response.status_code == 403
        store_alpha.refresh_from_db()
        assert store_alpha.status != StoreStatus.PUBLISHED

    def test_invalid_publish_action_rejected(self, client, owner_user, merchant_alpha, store_alpha):
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.post(
            reverse("merchants:store_publish_toggle"),
            data={"action": "malicious_action"},
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestStoreTenantIsolation:
    """Verifies that users of Merchant Alpha cannot access or modify Merchant Beta's store."""

    def test_user_cannot_access_other_merchant_store(
        self, client, owner_user, merchant_alpha, merchant_beta
    ):
        create_store(
            merchant_id=merchant_beta.id,
            actor=merchant_beta.owner_user,
            name="Beta Exclusive Store",
            slug="beta-exclusive",
        )

        # Owner of Alpha logs in with Alpha context
        client.force_login(owner_user)
        session = client.session
        session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant_alpha.id)
        session.save()

        response = client.get(reverse("merchants:store_settings"))
        # Alpha currently has no store, so it sees create page
        assert "Create Digital Storefront" in response.content.decode()
        assert "Beta Exclusive Store" not in response.content.decode()
