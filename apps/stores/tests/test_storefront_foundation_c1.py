import pytest
from django.template.loader import render_to_string
from django.urls import reverse

from apps.merchants.choices import BusinessType, MerchantStatus
from apps.merchants.models import Merchant
from apps.stores.choices import StoreStatus
from apps.stores.models import Store


@pytest.fixture
def active_merchant(db):
    return Merchant.objects.create(
        name="Luxe Boutiques",
        email="merchant@example.com",
        contact_number="+91 9876543210",
        address="10 Secret Private Street",
        city="Mumbai",
        state="Maharashtra",
        pin_code="400001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )


@pytest.fixture
def published_store(active_merchant):
    return Store.objects.create(
        merchant=active_merchant,
        name="Luxe Official",
        slug="luxe-official",
        tagline="Boutique Designer Apparel and Sarees",
        description="Handcrafted heritage fashion curated with love.",
        whatsapp_number="+919876543210",
        allow_whatsapp_fallback=True,
        social_links={
            "instagram": "https://instagram.com/luxeofficial",
            "facebook": "https://facebook.com/luxeofficial",
            "youtube": "https://youtube.com/@luxeofficial",
            "twitter_x": "https://x.com/luxeofficial",
            "pinterest": "https://pinterest.com/luxeofficial",
            "website": "https://luxeofficial.example.com",
        },
        status=StoreStatus.PUBLISHED,
    )


@pytest.mark.django_db
class TestStorefrontFoundationTemplates:
    """Unit tests for Stage C1 storefront base layout, header, and footer."""

    def test_base_template_assets_and_accessibility(self, published_store):
        rendered = render_to_string(
            "storefront/base.html",
            {"store": published_store},
        )
        # Fonts
        assert "Plus+Jakarta+Sans" in rendered
        assert "Space+Grotesk" in rendered
        assert "Material+Symbols+Outlined" in rendered

        # Static assets
        assert "css/dist/styles.css" in rendered
        assert "js/vendor/htmx.min.js" in rendered

        # Accessibility skip link
        assert 'href="#main-content"' in rendered
        assert "Skip to main content" in rendered

        # Semantic structure
        assert "<header" in rendered
        assert '<main id="main-content"' in rendered
        assert "<footer" in rendered

        # Title & Meta description
        assert "Luxe Official" in rendered
        assert "Boutique Designer Apparel and Sarees" in rendered

    def test_header_renders_brand_identity_and_merchant_context(self, published_store):
        rendered = render_to_string(
            "storefront/partials/_header.html",
            {"store": published_store},
        )
        assert "Luxe Official" in rendered
        assert "Boutique Designer Apparel and Sarees" in rendered
        assert "Mumbai" in rendered
        assert "Maharashtra" in rendered
        assert "+91 9876543210" in rendered
        assert "Catalogue" in rendered

        # Initials fallback avatar when no logo is set
        assert "LU" in rendered

    def test_header_handles_missing_tagline_and_contact_gracefully(self, active_merchant):
        store = Store.objects.create(
            merchant=active_merchant,
            name="Minimal Store",
            slug="minimal-store",
            status=StoreStatus.PUBLISHED,
        )
        rendered = render_to_string(
            "storefront/partials/_header.html",
            {"store": store},
        )
        assert "Minimal Store" in rendered
        assert "MI" in rendered
        assert "Catalogue" in rendered

    def test_footer_renders_merchant_details_and_social_links(self, published_store):
        rendered = render_to_string(
            "storefront/partials/_footer.html",
            {"store": published_store},
        )
        assert "Luxe Official" in rendered
        assert "Luxe Boutiques" in rendered
        assert "Handcrafted heritage fashion curated with love." in rendered
        assert "Mumbai, Maharashtra" in rendered
        assert "+91 9876543210" in rendered
        assert "merchant@example.com" in rendered

        # All 6 supported social platforms
        assert "https://instagram.com/luxeofficial" in rendered
        assert "https://facebook.com/luxeofficial" in rendered
        assert "https://youtube.com/@luxeofficial" in rendered
        assert "https://x.com/luxeofficial" in rendered
        assert "https://pinterest.com/luxeofficial" in rendered
        assert "https://luxeofficial.example.com" in rendered

        # Attestation and copyright
        assert "All rights reserved" in rendered
        assert "mycatalogue" in rendered

    def test_footer_privacy_protection_no_sensitive_leaks(self, published_store, active_merchant):
        """Ensures internal UUIDs, street address, and PIN codes are never exposed in public footer."""
        rendered = render_to_string(
            "storefront/partials/_footer.html",
            {"store": published_store},
        )
        assert str(published_store.id) not in rendered
        assert str(active_merchant.id) not in rendered
        assert active_merchant.address not in rendered  # "10 Secret Private Street"
        assert active_merchant.pin_code not in rendered  # "400001"
        assert active_merchant.status not in rendered

    def test_footer_empty_social_links_shows_default_note(self, active_merchant):
        store = Store.objects.create(
            merchant=active_merchant,
            name="Plain Store",
            slug="plain-store",
            social_links={},
            status=StoreStatus.PUBLISHED,
        )
        rendered = render_to_string(
            "storefront/partials/_footer.html",
            {"store": store},
        )
        assert "Browse our published digital catalogue online." in rendered


@pytest.mark.django_db
class TestStorefrontLiveEndpointIntegration:
    """Verifies that the live /s/<slug>/ endpoint renders the storefront foundation properly."""

    def test_public_store_view_renders_storefront_foundation(self, client, published_store):
        url = reverse("stores:public_detail", kwargs={"slug": published_store.slug})
        response = client.get(url)
        assert response.status_code == 200

        content = response.content.decode()
        # Verify storefront foundation elements
        assert "Plus+Jakarta+Sans" in content
        assert "Space+Grotesk" in content
        assert "Material+Symbols+Outlined" in content
        assert "Skip to main content" in content

        # Header elements
        assert "Luxe Official" in content
        assert "Boutique Designer Apparel and Sarees" in content
        assert "Mumbai" in content

        # Footer elements
        assert "Luxe Boutiques" in content
        assert "https://instagram.com/luxeofficial" in content
        assert "All rights reserved" in content
        assert "Powered by" in content

        # Privacy checks
        assert str(published_store.id) not in content
        assert str(published_store.merchant.id) not in content
        assert published_store.merchant.address not in content
        assert published_store.merchant.pin_code not in content
