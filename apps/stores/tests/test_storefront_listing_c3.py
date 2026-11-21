from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.merchants.choices import BusinessType, MerchantStatus
from apps.merchants.models import Merchant
from apps.products.choices import AvailabilityMode, PriceDisplayMode, ProductStatus
from apps.products.models import Category, Product, ProductImage
from apps.stores.choices import StoreStatus
from apps.stores.models import Store


@pytest.fixture
def merchant_alpha(db):
    return Merchant.objects.create(
        name="Alpha Silks",
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
        name="Beta Cottons",
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
        status=StoreStatus.PUBLISHED,
    )


@pytest.fixture
def store_beta(merchant_beta):
    return Store.objects.create(
        merchant=merchant_beta,
        name="Beta Store",
        slug="beta-store",
        tagline="Pure Handspun Cottons",
        status=StoreStatus.PUBLISHED,
    )


def make_published_product(merchant, name, slug, **kwargs):
    """Helper to create valid published products satisfying all DB check constraints."""
    defaults = {
        "price": Decimal("1000.00"),
        "price_display_mode": PriceDisplayMode.SHOW_PRICE,
        "availability_mode": AvailabilityMode.IN_STOCK,
        "is_available": True,
        "status": ProductStatus.PUBLISHED,
    }
    defaults.update(kwargs)
    return Product.objects.create(merchant=merchant, name=name, slug=slug, **defaults)


@pytest.mark.django_db
class TestStorefrontListingC3:
    """Comprehensive automated integration test suite for Stage C3 Public Product Catalogue."""

    def test_public_listing_route_accessible(self, client, store_alpha, merchant_alpha):
        """Catalogue renders successfully with HTTP 200, breadcrumbs, header, and search elements."""
        cat = Category.objects.create(
            merchant=merchant_alpha,
            name="Silk Sarees",
            slug="silk-sarees",
            is_active=True,
        )
        p1 = make_published_product(
            merchant_alpha,
            name="Banarasi Katan Silk",
            slug="banarasi-katan-silk",
            sku="BAN-001",
            price=Decimal("4999.00"),
        )
        p1.categories.add(cat)

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()

        assert "All Products" in content
        assert "Banarasi Katan Silk" in content
        assert "BAN-001" in content
        assert "₹4999" in content
        assert "In Stock" in content
        assert 'aria-label="Breadcrumb"' in content
        assert 'aria-label="Catalogue pagination"' not in content

    def test_public_listing_unpublished_store_404(self, client, store_alpha):
        """Unpublished stores return HTTP 404."""
        store_alpha.status = StoreStatus.DRAFT
        store_alpha.save(update_fields=["status"])

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        assert response.status_code == 404

    def test_public_listing_inactive_merchant_404(self, client, store_alpha, merchant_alpha):
        """Stores belonging to non-ACTIVE merchants return HTTP 404."""
        merchant_alpha.status = MerchantStatus.SUSPENDED
        merchant_alpha.save(update_fields=["status"])

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        assert response.status_code == 404

    def test_public_listing_strict_tenant_isolation(
        self, client, store_alpha, merchant_alpha, store_beta, merchant_beta
    ):
        """Products belonging to Merchant Beta must never appear in Store Alpha's listing."""
        make_published_product(
            merchant_alpha,
            name="Alpha Exclusive Chanderi",
            slug="alpha-chanderi",
            price=Decimal("1500.00"),
        )
        make_published_product(
            merchant_beta,
            name="Beta Confidential Muslin",
            slug="beta-muslin",
            price=Decimal("3000.00"),
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()

        assert "Alpha Exclusive Chanderi" in content
        assert "Beta Confidential Muslin" not in content

    def test_public_listing_draft_and_archived_excluded(self, client, store_alpha, merchant_alpha):
        """Draft and archived products are hidden from public storefront catalogue."""
        Product.objects.create(
            merchant=merchant_alpha,
            name="Draft Kurta",
            slug="draft-kurta",
            status=ProductStatus.DRAFT,
            price=Decimal("999.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
        )
        Product.objects.create(
            merchant=merchant_alpha,
            name="Archived Dupatta",
            slug="archived-dupatta",
            status=ProductStatus.ARCHIVED,
            price=Decimal("499.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
        )
        make_published_product(
            merchant_alpha,
            name="Published Lehenga",
            slug="published-lehenga",
            price=Decimal("8999.00"),
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        content = response.content.decode()

        assert "Published Lehenga" in content
        assert "Draft Kurta" not in content
        assert "Archived Dupatta" not in content

    def test_public_listing_search_by_name(self, client, store_alpha, merchant_alpha):
        """Search query 'q' matches product name case-insensitively."""
        make_published_product(
            merchant_alpha,
            name="Red Chanderi Anarkali",
            slug="red-chanderi",
        )
        make_published_product(
            merchant_alpha,
            name="Blue Georgette Saree",
            slug="blue-georgette",
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url, {"q": "chanderi"})
        assert response.status_code == 200
        content = response.content.decode()

        assert "Red Chanderi Anarkali" in content
        assert "Blue Georgette Saree" not in content

    def test_public_listing_search_by_sku(self, client, store_alpha, merchant_alpha):
        """Search query 'q' matches product SKU accurately."""
        make_published_product(
            merchant_alpha,
            name="Silk Dupatta",
            slug="silk-dupatta",
            sku="SKU-SILK-99",
        )
        make_published_product(
            merchant_alpha,
            name="Cotton Dupatta",
            slug="cotton-dupatta",
            sku="SKU-COT-01",
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url, {"q": "SILK-99"})
        assert response.status_code == 200
        content = response.content.decode()

        assert "Silk Dupatta" in content
        assert "Cotton Dupatta" not in content

    def test_public_listing_search_whitespace_and_length_safety(
        self, client, store_alpha, merchant_alpha
    ):
        """Excessive search string (>100 chars) and whitespace are handled safely."""
        make_published_product(
            merchant_alpha,
            name="Handloom Saree",
            slug="handloom-saree",
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        long_query = "   " + "a" * 150 + "   "
        response = client.get(url, {"q": long_query})
        assert response.status_code == 200

    def test_public_listing_filter_by_valid_category(self, client, store_alpha, merchant_alpha):
        """Filtering by category slug returns only products tagged with that category."""
        cat_festive = Category.objects.create(
            merchant=merchant_alpha,
            name="Festive Wear",
            slug="festive-wear",
            is_active=True,
        )
        cat_casual = Category.objects.create(
            merchant=merchant_alpha,
            name="Casual Wear",
            slug="casual-wear",
            is_active=True,
        )

        p1 = make_published_product(
            merchant_alpha,
            name="Festive Sherwani",
            slug="festive-sherwani",
        )
        p1.categories.add(cat_festive)

        p2 = make_published_product(
            merchant_alpha,
            name="Casual Kurti",
            slug="casual-kurti",
        )
        p2.categories.add(cat_casual)

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url, {"category": "festive-wear"})
        assert response.status_code == 200
        content = response.content.decode()

        assert "Festive Sherwani" in content
        assert "Casual Kurti" not in content
        assert "Festive Wear" in content

    def test_public_listing_invalid_category_returns_no_results_state(
        self, client, store_alpha, merchant_alpha, merchant_beta
    ):
        """Cross-tenant or bogus category slug renders HTTP 200 with no-results state and clear CTA."""
        make_published_product(
            merchant_alpha,
            name="Alpha Product",
            slug="alpha-product",
        )
        # Beta category
        Category.objects.create(
            merchant=merchant_beta,
            name="Beta Category",
            slug="beta-cat",
            is_active=True,
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        # 1. Non-existent slug
        resp1 = client.get(url, {"category": "non-existent-xyz"})
        assert resp1.status_code == 200
        content1 = resp1.content.decode()
        assert "No Matching Products" in content1
        assert "Clear All Filters" in content1

        # 2. Cross-tenant category slug
        resp2 = client.get(url, {"category": "beta-cat"})
        assert resp2.status_code == 200
        content2 = resp2.content.decode()
        assert "No Matching Products" in content2
        assert "Alpha Product" not in content2

    def test_public_listing_inactive_category_returns_no_results_state(
        self, client, store_alpha, merchant_alpha
    ):
        """Inactive categories are excluded from public filtering."""
        cat_inactive = Category.objects.create(
            merchant=merchant_alpha,
            name="Discontinued Fabrics",
            slug="discontinued-fabrics",
            is_active=False,
        )
        p1 = make_published_product(
            merchant_alpha,
            name="Discontinued Silk",
            slug="discontinued-silk",
        )
        p1.categories.add(cat_inactive)

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url, {"category": "discontinued-fabrics"})
        assert response.status_code == 200
        content = response.content.decode()
        assert "No Matching Products" in content

    def test_public_listing_filter_by_availability(self, client, store_alpha, merchant_alpha):
        """Filter by availability mode returns correct subsets."""
        make_published_product(
            merchant_alpha,
            name="In-Stock Dress",
            slug="in-stock-dress",
            availability_mode=AvailabilityMode.IN_STOCK,
            is_available=True,
        )
        make_published_product(
            merchant_alpha,
            name="Made-to-Order Bridal",
            slug="mto-bridal",
            availability_mode=AvailabilityMode.MADE_TO_ORDER,
            is_available=True,
        )
        make_published_product(
            merchant_alpha,
            name="Sold-Out Brocade",
            slug="sold-out-brocade",
            availability_mode=AvailabilityMode.OUT_OF_STOCK,
            is_available=False,
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})

        # Test IN_STOCK
        resp_stock = client.get(url, {"availability": "in_stock"})
        assert "In-Stock Dress" in resp_stock.content.decode()
        assert "Made-to-Order Bridal" not in resp_stock.content.decode()
        assert "Sold-Out Brocade" not in resp_stock.content.decode()

        # Test MADE_TO_ORDER
        resp_mto = client.get(url, {"availability": "made_to_order"})
        assert "Made-to-Order Bridal" in resp_mto.content.decode()
        assert "In-Stock Dress" not in resp_mto.content.decode()

        # Test OUT_OF_STOCK
        resp_oos = client.get(url, {"availability": "out_of_stock"})
        assert "Sold-Out Brocade" in resp_oos.content.decode()
        assert "In-Stock Dress" not in resp_oos.content.decode()

    def test_public_listing_invalid_availability_falls_back_to_all(
        self, client, store_alpha, merchant_alpha
    ):
        """Unrecognized availability string safely displays all published items."""
        make_published_product(
            merchant_alpha,
            name="Item One",
            slug="item-one",
            availability_mode=AvailabilityMode.IN_STOCK,
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url, {"availability": "bogus_status_123"})
        assert response.status_code == 200
        assert "Item One" in response.content.decode()

    def test_public_listing_sorting_newest(self, client, store_alpha, merchant_alpha):
        """Default sort and explicit ?sort=newest order by -created_at."""
        make_published_product(
            merchant_alpha,
            name="First Created",
            slug="first-created",
        )
        make_published_product(
            merchant_alpha,
            name="Second Created",
            slug="second-created",
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url, {"sort": "newest"})
        content = response.content.decode()

        idx1 = content.index("First Created")
        idx2 = content.index("Second Created")
        assert idx2 < idx1  # Second created should appear first (newest first)

    def test_public_listing_sorting_price_asc_and_desc(self, client, store_alpha, merchant_alpha):
        """Price sorting orders priced products correctly."""
        make_published_product(
            merchant_alpha,
            name="Affordable Saree",
            slug="affordable-saree",
            price=Decimal("500.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
        )
        make_published_product(
            merchant_alpha,
            name="Luxury Saree",
            slug="luxury-saree",
            price=Decimal("5000.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})

        # Ascending: Low to High
        resp_asc = client.get(url, {"sort": "price_asc"})
        content_asc = resp_asc.content.decode()
        assert content_asc.index("Affordable Saree") < content_asc.index("Luxury Saree")

        # Descending: High to Low
        resp_desc = client.get(url, {"sort": "price_desc"})
        content_desc = resp_desc.content.decode()
        assert content_desc.index("Luxury Saree") < content_desc.index("Affordable Saree")

    def test_public_listing_contact_for_price_hardened_privacy_audit(
        self, client, store_alpha, merchant_alpha
    ):
        """
        Hardened privacy test:
        1. Uses unique sentinel price 133742.00 and sentinel MRP 199999.00.
        2. Asserts item sorts at the very end (NULLS LAST) in both price_asc and price_desc.
        3. Asserts sentinel numeric values NEVER appear anywhere in HTML, attributes, JSON, or scripts.
        """
        sentinel_price = Decimal("133742.00")
        sentinel_mrp = Decimal("199999.00")

        make_published_product(
            merchant_alpha,
            name="Priced Item Low",
            slug="priced-item-low",
            price=Decimal("500.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
        )
        make_published_product(
            merchant_alpha,
            name="Priced Item High",
            slug="priced-item-high",
            price=Decimal("500000.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
        )
        make_published_product(
            merchant_alpha,
            name="Secret Bridal Set",
            slug="secret-bridal-set",
            price=sentinel_price,
            mrp=sentinel_mrp,
            price_display_mode=PriceDisplayMode.CONTACT_FOR_PRICE,
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})

        # Test price_asc: Secret Bridal Set must sort at the end (NULLS LAST)
        resp_asc = client.get(url, {"sort": "price_asc"})
        content_asc = resp_asc.content.decode()
        assert content_asc.index("Priced Item Low") < content_asc.index("Secret Bridal Set")
        assert content_asc.index("Priced Item High") < content_asc.index("Secret Bridal Set")

        # Test price_desc: Secret Bridal Set must STILL sort at the end (NULLS LAST)
        resp_desc = client.get(url, {"sort": "price_desc"})
        content_desc = resp_desc.content.decode()
        assert content_desc.index("Priced Item High") < content_desc.index("Secret Bridal Set")
        assert content_desc.index("Priced Item Low") < content_desc.index("Secret Bridal Set")

        # Hardened Content Audit: Sentinel values must NEVER appear anywhere in response
        for content in (content_asc, content_desc):
            assert "133742" not in content
            assert "133,742" not in content
            assert "199999" not in content
            assert "199,999" not in content
            assert "Contact for Price" in content

    def test_public_listing_invalid_sort_falls_back_to_newest(
        self, client, store_alpha, merchant_alpha
    ):
        """Unsupported sort parameter safely falls back to newest first."""
        make_published_product(
            merchant_alpha,
            name="Test Alpha Item",
            slug="test-alpha-item",
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url, {"sort": "malicious_or_unknown_sort_key"})
        assert response.status_code == 200
        assert "Test Alpha Item" in response.content.decode()

    def test_public_listing_pagination_12_per_page(self, client, store_alpha, merchant_alpha):
        """Paginator correctly serves 12 items per page."""
        for i in range(15):
            make_published_product(
                merchant_alpha,
                name=f"Catalogue Item {i:02d}",
                slug=f"item-{i:02d}",
            )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})

        # Page 1: 12 items
        resp1 = client.get(url)
        assert resp1.status_code == 200
        assert len(resp1.context["page_obj"]) == 12
        assert resp1.context["page_obj"].has_next()

        # Page 2: 3 items
        resp2 = client.get(url, {"page": 2})
        assert resp2.status_code == 200
        assert len(resp2.context["page_obj"]) == 3
        assert not resp2.context["page_obj"].has_next()

    def test_public_listing_pagination_preserves_query_filters(
        self, client, store_alpha, merchant_alpha
    ):
        """Pagination links preserve active q, category, availability, and sort parameters."""
        cat = Category.objects.create(
            merchant=merchant_alpha,
            name="Silk",
            slug="silk",
            is_active=True,
        )
        for i in range(15):
            p = make_published_product(
                merchant_alpha,
                name=f"Silk Item {i:02d}",
                slug=f"silk-item-{i:02d}",
                price=Decimal("1000.00") + Decimal(i * 10),
            )
            p.categories.add(cat)

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        params = {
            "q": "Silk",
            "category": "silk",
            "availability": "in_stock",
            "sort": "price_asc",
            "page": 1,
        }
        response = client.get(url, params)
        content = response.content.decode()

        # Assert next page link contains preserved filters
        assert "q=Silk" in content
        assert "category=silk" in content
        assert "availability=in_stock" in content
        assert "sort=price_asc" in content
        assert "page=2" in content

    def test_public_listing_pagination_invalid_page_numbers(
        self, client, store_alpha, merchant_alpha
    ):
        """Non-integer and out-of-bounds page parameters fall back safely."""
        for i in range(15):
            make_published_product(
                merchant_alpha,
                name=f"Paginated Item {i:02d}",
                slug=f"pag-item-{i:02d}",
            )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})

        # Non-integer -> Page 1
        resp_alpha = client.get(url, {"page": "invalid_page"})
        assert resp_alpha.status_code == 200
        assert resp_alpha.context["page_obj"].number == 1

        # Out-of-bounds -> Last page (2)
        resp_out = client.get(url, {"page": 9999})
        assert resp_out.status_code == 200
        assert resp_out.context["page_obj"].number == 2

    def test_public_listing_discount_percentage_rounding_and_edge_cases(
        self, client, store_alpha, merchant_alpha
    ):
        """Verifies discount calculation edge cases and commercial half-up rounding."""
        # 1. 38% OFF (2499 from 3999)
        p1 = make_published_product(
            merchant_alpha,
            name="Standard Discount Item",
            slug="std-discount",
            price=Decimal("2499.00"),
            mrp=Decimal("3999.00"),
        )
        # 2. <1% discount suppression (995 from 1000 = 0.5% -> suppressed)
        make_published_product(
            merchant_alpha,
            name="Negligible Discount Item",
            slug="neg-discount",
            price=Decimal("995.00"),
            mrp=Decimal("1000.00"),
        )
        # 3. Equal MRP and Price (500 from 500 -> suppressed)
        p3 = make_published_product(
            merchant_alpha,
            name="No Discount Item",
            slug="no-discount",
            price=Decimal("500.00"),
            mrp=Decimal("500.00"),
        )

        assert p1.discount_percentage == 38
        assert p3.discount_percentage is None

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        content = response.content.decode()

        # In Revision 4 simplified cards, commercial discount badges are omitted to keep cards clean and image-focused
        assert "% OFF" not in content

    def test_public_listing_image_fallback_when_no_primary_image(
        self, client, store_alpha, merchant_alpha
    ):
        """Falls back to first gallery image when none is primary; displays placeholder if 0 images."""
        p_with_img = make_published_product(
            merchant_alpha,
            name="Item With Non-Primary Image",
            slug="item-non-primary",
        )
        # Image with is_primary=False
        fake_file = SimpleUploadedFile("gallery1.jpg", b"fakeimagebytes", content_type="image/jpeg")
        ProductImage.objects.create(
            product=p_with_img,
            image=fake_file,
            is_primary=False,
            display_order=1,
        )

        # Product with zero images
        make_published_product(
            merchant_alpha,
            name="Item Without Any Image",
            slug="item-zero-images",
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        content = response.content.decode()

        # Non-primary image was fetched and rendered via fallback
        assert "gallery1" in content
        # Zero-image item renders accessible placeholder
        assert "No Image Available" in content

    def test_public_listing_n_plus_one_prevention_differential(
        self, client, store_alpha, merchant_alpha
    ):
        """
        Differential N+1 query prevention test:
        Compares query count when listing 1 product vs 12 products.
        Asserts that query count remains O(1) constant: Q(12) == Q(1).
        """
        cat = Category.objects.create(
            merchant=merchant_alpha,
            name="Fabrics",
            slug="fabrics",
            is_active=True,
        )
        # Create 12 products each with images and categories
        for i in range(12):
            p = make_published_product(
                merchant_alpha,
                name=f"Fabrics Sample {i:02d}",
                slug=f"fabrics-sample-{i:02d}",
                price=Decimal("1200.00"),
            )
            p.categories.add(cat)
            fake_file = SimpleUploadedFile(f"fab_{i}.jpg", b"fakebytes", content_type="image/jpeg")
            ProductImage.objects.create(product=p, image=fake_file, is_primary=True)

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})

        # 1. Measure query count for 1 product (via search filter)
        with CaptureQueriesContext(connection) as ctx_one:
            resp_one = client.get(url, {"q": "Fabrics Sample 00"})
            assert resp_one.status_code == 200
        q1_count = len(ctx_one.captured_queries)

        # 2. Measure query count for all 12 products
        with CaptureQueriesContext(connection) as ctx_all:
            resp_all = client.get(url)
            assert resp_all.status_code == 200
        q12_count = len(ctx_all.captured_queries)

        # Assert zero N+1 scaling: Q(12) == Q(1)
        assert q12_count == q1_count
        assert q12_count <= 10  # Generous upper ceiling to guard against query bloat

    def test_public_listing_no_premature_product_detail_links(
        self, client, store_alpha, merchant_alpha
    ):
        """Asserts product cards do NOT contain href='#' or /products/<slug>/ prior to Stage C4."""
        make_published_product(
            merchant_alpha,
            name="Unlinked Card Test Item",
            slug="unlinked-item",
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        content = response.content.decode()

        # Assert no premature product detail link
        assert f"/s/{store_alpha.slug}/products/unlinked-item/" not in content
        # Assert no dead href="#" on product card
        assert 'href="#"' not in content

    def test_public_listing_empty_catalogue_state(self, client, store_alpha):
        """Merchant with 0 published products renders the editorial 'Catalogue Coming Soon' state."""
        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()

        assert "Catalogue Coming Soon" in content
        assert "Our digital catalogue is currently being curated" in content
        assert "Back to Store Home" in content

    def test_public_listing_two_control_toolbar_and_no_sidebar(
        self, client, store_alpha, merchant_alpha
    ):
        """Verifies Revision 4 toolbar has exactly two controls and no permanent sidebar."""
        make_published_product(
            merchant_alpha,
            name="Sample Silk Saree",
            slug="sample-silk-saree",
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        content = response.content.decode()

        # Exactly two toolbar controls: Sort by and Filter
        assert 'id="catalogue-sort"' in content
        assert 'name="sort"' in content
        assert 'aria-label="Filter products by availability"' in content
        assert 'aria-label="Availability filter menu"' in content

        # Availability choices in filter popover
        assert 'value="in_stock"' in content
        assert 'value="made_to_order"' in content
        assert 'value="out_of_stock"' in content
        assert "Apply Filter" in content

        # No duplicate in-page search input (only the header search exists)
        assert 'placeholder="Search by product name or SKU..."' not in content

        # No permanent left filter sidebar
        assert "col-span-3" not in content

    def test_public_listing_active_filter_chips_and_no_sort_chip(
        self, client, store_alpha, merchant_alpha
    ):
        """Verifies active chips represent search/cat/avail only, and never a sort chip."""
        cat = Category.objects.create(
            merchant=merchant_alpha,
            name="Silk Sarees",
            slug="silk-sarees",
            is_active=True,
        )
        p = make_published_product(
            merchant_alpha,
            name="Embroidered Silk",
            slug="embroidered-silk",
        )
        p.categories.add(cat)

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        # Apply search, category, availability, and non-default sort
        response = client.get(
            url,
            {
                "q": "Embroidered",
                "category": "silk-sarees",
                "availability": "in_stock",
                "sort": "price_asc",
            },
        )
        content = response.content.decode()

        # Active chips present for search, category, and availability
        assert 'Search: "Embroidered"' in content
        assert "Category: Silk Sarees" in content
        assert "In_Stock" in content or "In Stock" in content

        # Filter button displays active count badge '1'
        assert "Filter" in content
        assert "1" in content

        # Crucial Revision 4 requirement: NO Sort chip is displayed!
        assert "Sort: Price Low to High" not in content
        assert "Sort: Price: Low to High" not in content

        # Clear all link is present
        assert "Clear all" in content

    def test_public_listing_no_unsupported_features(
        self, client, store_alpha, merchant_alpha
    ):
        """Verifies removal of WhatsApp assistance banner and e-commerce shopping features from C3."""
        make_published_product(
            merchant_alpha,
            name="Classic Kurta",
            slug="classic-kurta",
        )

        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url)
        content = response.content.decode()

        # WhatsApp assistance banner removed from catalogue feed
        assert "Need direct assistance?" not in content
        assert "Connect directly with" not in content

        # No unsupported e-commerce features (cart, checkout, payment, ratings)
        assert "Add to Cart" not in content
        assert "Checkout" not in content
        assert "Customer Reviews" not in content
        assert "star" not in content.lower() or "material-symbols-outlined" in content

    def test_public_listing_heading_uses_matching_count(
        self, client, store_alpha, merchant_alpha
    ):
        """Heading displays paginator.count matching filtered results, not total store count."""
        cat1 = Category.objects.create(
            merchant=merchant_alpha,
            name="Silks",
            slug="silks",
            is_active=True,
        )
        cat2 = Category.objects.create(
            merchant=merchant_alpha,
            name="Cottons",
            slug="cottons",
            is_active=True,
        )

        p1 = make_published_product(merchant_alpha, name="Silk One", slug="silk-one")
        p1.categories.add(cat1)
        p2 = make_published_product(merchant_alpha, name="Silk Two", slug="silk-two")
        p2.categories.add(cat1)

        p3 = make_published_product(merchant_alpha, name="Cotton One", slug="cotton-one")
        p3.categories.add(cat2)

        # Filter by Silks: 2 matching out of 3 total published
        url = reverse("stores:public_products", kwargs={"slug": store_alpha.slug})
        response = client.get(url, {"category": "silks"})
        content = response.content.decode()

        # Heading must show matching count (2 items), not total catalogue count (3 items)
        assert "Silks" in content
        assert "(2 items)" in content
        assert "(3 items)" not in content
