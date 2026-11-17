import pytest
from django.core.exceptions import ValidationError

from apps.merchants.choices import BusinessType, MerchantStatus
from apps.merchants.models import Merchant
from apps.stores.models import Store
from apps.stores.validators import validate_social_links


@pytest.fixture
def active_merchant(db):
    return Merchant.objects.create(
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
