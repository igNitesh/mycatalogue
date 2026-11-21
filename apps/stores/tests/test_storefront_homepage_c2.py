from decimal import Decimal

import pytest
from django.urls import reverse

from apps.merchants.choices import BusinessType, MerchantStatus
from apps.merchants.models import Merchant
from apps.products.choices import AvailabilityMode, PriceDisplayMode, ProductStatus
from apps.products.models import Category, Product
from apps.products.selectors import get_public_storefront_products
from apps.stores.choices import StoreStatus
from apps.stores.models import Store


@pytest.fixture
def merchant_alpha(db):
    return Merchant.objects.create(
        name="Alpha Boutiques",
        email="alpha@example.com",
        contact_number="+91 9876543210",
        address="10 Secret Road, Suite 99",
        city="Mumbai",
        state="Maharashtra",
        pin_code="400001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )


@pytest.fixture
def merchant_beta(db):
    return Merchant.objects.create(
        name="Beta Silks",
        email="beta@example.com",
        contact_number="+91 9123456789",
        address="22 Confidential Lane",
        city="Varanasi",
        state="Uttar Pradesh",
        pin_code="221001",
        business_type=BusinessType.RETAIL,
        status=MerchantStatus.ACTIVE,
    )


@pytest.fixture
def store_alpha(merchant_alpha):
    return Store.objects.create(
        merchant=merchant_alpha,
        name="Alpha Store",
        slug="alpha-store",
        tagline="Handcrafted Silks and Sarees",
        description="Curating India's finest handloom heritage since 1995.",
        whatsapp_number="+919876543210",
        allow_whatsapp_fallback=True,
        social_links={"instagram": "https://instagram.com/alphastore"},
        status=StoreStatus.PUBLISHED,
    )


@pytest.fixture
def store_beta(merchant_beta):
    return Store.objects.create(
        merchant=merchant_beta,
        name="Beta Store",
        slug="beta-store",
        tagline="Authentic Banarasi Collections",
        status=StoreStatus.PUBLISHED,
    )


@pytest.mark.django_db
class TestStorefrontHomepageC2:
    """Automated integration and unit test suite for Stage C2 Public Store Homepage."""

    def test_homepage_renders_all_sections_successfully(self, client, store_alpha, merchant_alpha):
        # Create active category
        cat = Category.objects.create(
            merchant=merchant_alpha,
            name="Chanderi Sarees",
            slug="chanderi-sarees",
            is_active=True,
        )

        # Create published product with pricing and discount
        p1 = Product.objects.create(
            merchant=merchant_alpha,
            name="Royal Blue Chanderi Silk Saree",
            slug="royal-blue-chanderi",
            sku="SAR-CHN-001",
            price=Decimal("2499.00"),
            mrp=Decimal("3999.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
            availability_mode=AvailabilityMode.IN_STOCK,
            is_available=True,
            status=ProductStatus.PUBLISHED,
        )
        p1.categories.add(cat)

        url = reverse("stores:public_detail", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()

        # 1. Hero & Branding
        assert "Alpha Store" in content
        assert "Handcrafted Silks and Sarees" in content
        assert "Mumbai, Maharashtra" in content
        assert "1 Product" in content
        assert "1 Category" in content

        # 2. Shop by Category
        assert "Shop by Category" in content
        assert "Chanderi Sarees" in content
        assert f"/s/{store_alpha.slug}/products/?category=chanderi-sarees" in content

        # 3. Latest Products
        assert "Latest Products" in content
        assert "Royal Blue Chanderi Silk Saree" in content
        assert "SAR-CHN-001" in content
        assert "₹2499" in content
        assert "₹3999" in content
        assert "38% OFF" in content
        assert "In Stock" in content

        # 4. Browse All Products CTA
        assert f"/s/{store_alpha.slug}/products/" in content
        assert "Browse All Products" in content

        # 5. Header: Search Bar (Future), Profile (Future), and Category Navigation Row
        assert 'aria-label="Category navigation"' in content
        assert "All Products" in content
        assert 'aria-label="Search catalogue"' in content
        assert 'aria-label="Customer Profile"' in content

        # 6. Factual Store Profile Card with Owner Details (Zero Fake Badges & Zero Fake Hours)
        assert "Store Profile" in content
        assert "Active Storefront" in content
        assert "Proprietor &amp; Store Owner" in content or "Proprietor" in content
        assert "10:00 AM – 8:30 PM" not in content
        assert "Open Today" not in content
        assert "Verified Store" not in content
        assert "Verified Merchant" not in content

        # 7. Store Description
        assert (
            "Curating India&#x27;s finest handloom heritage since 1995." in content
            or "Curating India's finest" in content
        )

    def test_ordering_parameter_whitelist_and_rejection(self, merchant_alpha, store_alpha):
        # Create Anarkali Suit first (older)
        Product.objects.create(
            merchant=merchant_alpha,
            name="Anarkali Suit",
            slug="anarkali-suit",
            price=Decimal("2500.00"),
            status=ProductStatus.PUBLISHED,
        )
        # Create Zari Kurta second (newer)
        Product.objects.create(
            merchant=merchant_alpha,
            name="Zari Kurta",
            slug="zari-kurta",
            price=Decimal("1500.00"),
            status=ProductStatus.PUBLISHED,
        )

        # Default ordering by name: Anarkali Suit before Zari Kurta
        qs_name = list(get_public_storefront_products(merchant=merchant_alpha, ordering="name"))
        assert qs_name[0].name == "Anarkali Suit"
        assert qs_name[1].name == "Zari Kurta"

        # Ordering by newest: Zari Kurta (created later) before Anarkali Suit
        qs_newest = list(get_public_storefront_products(merchant=merchant_alpha, ordering="newest"))
        assert qs_newest[0].name == "Zari Kurta"
        assert qs_newest[1].name == "Anarkali Suit"

        # Invalid ordering parameter must raise ValueError
        with pytest.raises(ValueError, match="Invalid ordering"):
            get_public_storefront_products(merchant=merchant_alpha, ordering="price; DROP TABLE")

        with pytest.raises(ValueError, match="Invalid ordering"):
            get_public_storefront_products(merchant=merchant_alpha, ordering="unauthorized_field")

    def test_category_and_product_tenant_isolation(
        self, client, store_alpha, merchant_alpha, store_beta, merchant_beta
    ):
        # Store Alpha assets
        cat_alpha = Category.objects.create(
            merchant=merchant_alpha, name="Alpha Category", slug="alpha-cat", is_active=True
        )
        p_alpha = Product.objects.create(
            merchant=merchant_alpha,
            name="Alpha Pure Silk Saree",
            slug="alpha-pure-silk",
            price=Decimal("2000.00"),
            status=ProductStatus.PUBLISHED,
        )
        p_alpha.categories.add(cat_alpha)

        # Store Beta assets
        cat_beta = Category.objects.create(
            merchant=merchant_beta, name="Beta Silk Brocade", slug="beta-brocade", is_active=True
        )
        p_beta = Product.objects.create(
            merchant=merchant_beta,
            name="Beta Golden Lehenga",
            slug="beta-golden-lehenga",
            price=Decimal("8000.00"),
            status=ProductStatus.PUBLISHED,
        )
        p_beta.categories.add(cat_beta)

        # View Store Alpha
        url_alpha = reverse("stores:public_detail", kwargs={"slug": store_alpha.slug})
        resp_alpha = client.get(url_alpha)
        assert resp_alpha.status_code == 200
        content_alpha = resp_alpha.content.decode()

        assert "Alpha Category" in content_alpha
        assert "Alpha Pure Silk Saree" in content_alpha
        assert "Beta Silk Brocade" not in content_alpha
        assert "Beta Golden Lehenga" not in content_alpha

        # View Store Beta
        url_beta = reverse("stores:public_detail", kwargs={"slug": store_beta.slug})
        resp_beta = client.get(url_beta)
        assert resp_beta.status_code == 200
        content_beta = resp_beta.content.decode()

        assert "Beta Silk Brocade" in content_beta
        assert "Beta Golden Lehenga" in content_beta
        assert "Alpha Category" not in content_beta
        assert "Alpha Pure Silk Saree" not in content_beta

    def test_draft_and_archived_products_suppressed(self, client, store_alpha, merchant_alpha):
        Product.objects.create(
            merchant=merchant_alpha,
            name="Published Silk Dress",
            slug="pub-dress",
            price=Decimal("1200.00"),
            status=ProductStatus.PUBLISHED,
        )
        Product.objects.create(
            merchant=merchant_alpha,
            name="Draft Secret Sample",
            slug="draft-sample",
            price=Decimal("999.00"),
            status=ProductStatus.DRAFT,
        )
        Product.objects.create(
            merchant=merchant_alpha,
            name="Archived Old Model",
            slug="archived-model",
            price=Decimal("500.00"),
            status=ProductStatus.ARCHIVED,
        )

        url = reverse("stores:public_detail", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()

        assert "Published Silk Dress" in content
        assert "Draft Secret Sample" not in content
        assert "Archived Old Model" not in content
        # Only 1 published product counted
        assert "1 Product" in content

    def test_contact_for_price_privacy_no_numeric_price_leak(
        self, client, store_alpha, merchant_alpha
    ):
        Product.objects.create(
            merchant=merchant_alpha,
            name="Bespoke Royal Bridal Lehenga",
            slug="bespoke-bridal",
            sku="BRD-001",
            price=Decimal("75000.00"),
            mrp=Decimal("95000.00"),
            price_display_mode=PriceDisplayMode.CONTACT_FOR_PRICE,
            status=ProductStatus.PUBLISHED,
        )

        url = reverse("stores:public_detail", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()

        assert "Bespoke Royal Bridal Lehenga" in content
        assert "Contact for Price" in content

        # STRICT PRIVACY: Numeric price and MRP must not appear in the response HTML
        assert "75000" not in content
        assert "95000" not in content
        assert "75,000" not in content
        assert "95,000" not in content

    def test_empty_categories_and_products_graceful_fallbacks(
        self, client, store_alpha, merchant_alpha
    ):
        """When merchant has no categories or products, renders clean fallbacks without error."""
        url = reverse("stores:public_detail", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()

        # Categories section should be cleanly suppressed
        assert "Shop by Category" not in content
        assert 'aria-label="Category navigation"' not in content

        # Products empty state displayed
        assert "Catalogue Coming Soon" in content
        assert "Our digital catalogue is currently being curated." in content

        # Cover fallback banner rendered with high contrast text
        assert "Alpha Store" in content
        assert "0 Products" in content

    def test_unpublished_store_and_inactive_merchant_return_404(
        self, client, store_alpha, merchant_alpha
    ):
        # 1. Draft store returns 404
        store_alpha.status = StoreStatus.DRAFT
        store_alpha.save(update_fields=["status"])
        url = reverse("stores:public_detail", kwargs={"slug": store_alpha.slug})
        assert client.get(url).status_code == 404

        # Restore published
        store_alpha.status = StoreStatus.PUBLISHED
        store_alpha.save(update_fields=["status"])
        assert client.get(url).status_code == 200

        # 2. Suspended merchant returns 404
        merchant_alpha.status = MerchantStatus.SUSPENDED
        merchant_alpha.save(update_fields=["status"])
        assert client.get(url).status_code == 404

    def test_tenant_data_privacy_no_sensitive_leaks(self, client, store_alpha, merchant_alpha):
        url = reverse("stores:public_detail", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()

        # Publicly safe fields MUST be present
        assert store_alpha.name in content
        assert merchant_alpha.city in content
        assert merchant_alpha.state in content

        # Sensitive private tenant data MUST NOT be exposed
        assert str(store_alpha.id) not in content
        assert str(merchant_alpha.id) not in content
        assert merchant_alpha.address not in content  # "10 Secret Road, Suite 99"
        assert merchant_alpha.pin_code not in content  # "400001"
        assert merchant_alpha.status not in content
        assert store_alpha.status not in content
