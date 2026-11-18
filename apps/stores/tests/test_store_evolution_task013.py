import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.merchants.choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.models import Merchant, MerchantMembership
from apps.stores.models import Store
from apps.stores.services import create_store, update_store_profile
from apps.stores.validators import validate_social_links

User = get_user_model()


@pytest.fixture
def owner_user(db):
    return User.objects.create_user(
        email="apex_owner@example.com",
        password="ValidPassword123!",
        is_verified=True,
    )


@pytest.fixture
def active_merchant(db, owner_user):
    merchant = Merchant.objects.create(
        name="Apex Mart",
        email="apex@example.com",
        contact_number="9876543210",
        address="123 High Street",
        city="Mumbai",
        state="Maharashtra",
        pin_code="400001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )
    MerchantMembership.objects.create(
        merchant=merchant,
        user=owner_user,
        role=MembershipRole.OWNER,
        status=MembershipStatus.ACTIVE,
    )
    return merchant


@pytest.fixture
def store_alpha(db, active_merchant):
    return Store.objects.create(
        merchant=active_merchant,
        name="Apex Store",
        slug="apex-store",
        description="Official store of Apex Mart",
    )


@pytest.mark.django_db
class TestStoreFieldsAndSocialLinksTask013:
    """Verifies Store tagline, whatsapp_number, allow_whatsapp_fallback, and social_links."""

    def test_store_new_fields_defaults(self, store_alpha):
        store = Store.objects.get(id=store_alpha.id)
        assert store.tagline == ""
        assert store.whatsapp_number == ""
        assert store.allow_whatsapp_fallback is True
        assert store.social_links == {}

    def test_store_save_with_valid_new_fields(self, store_alpha):
        store = store_alpha
        store.tagline = "Pure Handloom Silks since 1984"
        store.whatsapp_number = "+919876543210"
        store.allow_whatsapp_fallback = False
        store.social_links = {
            "instagram": "https://instagram.com/krishnagarments",
            "facebook": "https://facebook.com/krishnagarments",
            "website": "https://krishnagarments.com",
        }
        store.full_clean()
        store.save()

        store.refresh_from_db()
        assert store.tagline == "Pure Handloom Silks since 1984"
        assert store.whatsapp_number == "+919876543210"
        assert store.allow_whatsapp_fallback is False
        assert len(store.social_links) == 3

    def test_validate_social_links_unsupported_platform_rejected(self):
        with pytest.raises(ValidationError, match="Unsupported social platform 'tiktok'"):
            validate_social_links({"tiktok": "https://tiktok.com/@krishna"})

    def test_validate_social_links_insecure_http_rejected(self):
        with pytest.raises(ValidationError, match="Invalid HTTPS URL"):
            validate_social_links({"website": "http://krishnagarments.com"})

    def test_validate_social_links_malformed_url_rejected(self):
        with pytest.raises(ValidationError, match="Invalid HTTPS URL"):
            validate_social_links({"instagram": "not-a-valid-url"})

    def test_validate_social_links_strips_empty_values(self):
        cleaned = validate_social_links(
            {
                "instagram": "https://instagram.com/krishna",
                "facebook": "",
                "youtube": None,
            }
        )
        assert "instagram" in cleaned
        assert "facebook" not in cleaned
        assert "youtube" not in cleaned

    def test_create_store_service_with_evolution_fields(self, active_merchant, owner_user):
        # Delete existing fixture store so we can create a fresh one
        Store.objects.filter(merchant=active_merchant).delete()

        store = create_store(
            merchant_id=active_merchant,
            actor=owner_user,
            name="Apex Flagship",
            slug="apex-flagship",
            description="Our primary store",
            tagline="Quality First",
            whatsapp_number="+919876500000",
            allow_whatsapp_fallback=False,
            social_links={"instagram": "https://instagram.com/apex"},
        )
        assert store.tagline == "Quality First"
        assert store.whatsapp_number == "+919876500000"
        assert store.allow_whatsapp_fallback is False
        assert store.social_links == {"instagram": "https://instagram.com/apex"}

    def test_create_store_service_validates_oversized_fields(self, active_merchant, owner_user):
        Store.objects.filter(merchant=active_merchant).delete()

        with pytest.raises(ValidationError, match="Store tagline cannot exceed 120 characters"):
            create_store(
                merchant_id=active_merchant,
                actor=owner_user,
                name="Apex",
                slug="apex-test",
                tagline="X" * 121,
            )

        with pytest.raises(ValidationError, match="WhatsApp number cannot exceed 20 characters"):
            create_store(
                merchant_id=active_merchant,
                actor=owner_user,
                name="Apex",
                slug="apex-test",
                whatsapp_number="1" * 21,
            )

    def test_update_store_profile_service_with_evolution_fields(self, store_alpha, owner_user):
        updated = update_store_profile(
            store_id=store_alpha.id,
            actor=owner_user,
            tagline="Updated Heritage Brand",
            whatsapp_number="+919999988888",
            allow_whatsapp_fallback=False,
            social_links={"facebook": "https://facebook.com/apexbrand"},
        )
        assert updated.tagline == "Updated Heritage Brand"
        assert updated.whatsapp_number == "+919999988888"
        assert updated.allow_whatsapp_fallback is False
        assert updated.social_links == {"facebook": "https://facebook.com/apexbrand"}

        # Verify in database
        store_alpha.refresh_from_db()
        assert store_alpha.tagline == "Updated Heritage Brand"
        assert store_alpha.whatsapp_number == "+919999988888"
        assert store_alpha.allow_whatsapp_fallback is False
        assert store_alpha.social_links == {"facebook": "https://facebook.com/apexbrand"}
