import json
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.merchants.choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus
from apps.merchants.context import ACTIVE_MERCHANT_SESSION_KEY
from apps.merchants.models import MerchantMembership
from apps.merchants.services import create_merchant
from apps.products.choices import Currency, ProductStatus
from apps.products.models import Category, Product, ProductImage
from apps.products.services import (
    add_product_image,
    create_category,
    create_product,
)
from apps.products.tests.conftest import make_test_image
from apps.stores.choices import StoreStatus
from apps.stores.models import Store

User = get_user_model()


@pytest.fixture
def owner_user(db):
    return User.objects.create_user(
        email="owner@catalogue.com",
        password="ValidPassword123!",
        is_verified=True,
        is_active=True,
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="admin@catalogue.com",
        password="ValidPassword123!",
        is_verified=True,
        is_active=True,
    )


@pytest.fixture
def manager_user(db):
    return User.objects.create_user(
        email="manager@catalogue.com",
        password="ValidPassword123!",
        is_verified=True,
        is_active=True,
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        email="staff@catalogue.com",
        password="ValidPassword123!",
        is_verified=True,
        is_active=True,
    )


@pytest.fixture
def unverified_user(db):
    return User.objects.create_user(
        email="unverified@catalogue.com",
        password="ValidPassword123!",
        is_verified=False,
        is_active=True,
    )


@pytest.fixture
def merchant_alpha(db, owner_user, admin_user, manager_user, staff_user):
    merchant, _ = create_merchant(
        owner_user=owner_user,
        name="Alpha Boutique",
        business_type=BusinessType.RETAIL,
        contact_number="+91 9876543210",
        email="alpha@catalogue.com",
        address="100 Market St",
        city="Mumbai",
        state="Maharashtra",
        pin_code="400001",
    )
    merchant.status = MerchantStatus.ACTIVE
    merchant.save()

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
    merchant.owner_user = owner_user
    return merchant


@pytest.fixture
def merchant_beta(db):
    user = User.objects.create_user(
        email="beta.owner@catalogue.com",
        password="ValidPassword123!",
        is_verified=True,
        is_active=True,
    )
    merchant, _ = create_merchant(
        owner_user=user,
        name="Beta Wholesale",
        business_type=BusinessType.WHOLESALE,
        contact_number="+91 9876543211",
        email="beta@catalogue.com",
        address="200 Industrial Rd",
        city="Pune",
        state="Maharashtra",
        pin_code="411001",
    )
    merchant.status = MerchantStatus.ACTIVE
    merchant.save()
    merchant.owner_user = user
    return merchant


def set_active_merchant(client, user, merchant):
    client.force_login(user)
    session = client.session
    session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant.id)
    session.save()


@pytest.mark.django_db
class TestCatalogueAccessControl:
    """Verifies authentication, email verification, active context, and role permissions."""

    def test_unauthenticated_user_redirected_to_login(self, client):
        response = client.get(reverse("products:overview"))
        assert response.status_code == 302
        assert "/auth/login/" in response.url

    def test_unverified_user_redirected_to_verification_required(self, client, unverified_user):
        client.force_login(unverified_user)
        response = client.get(reverse("products:overview"))
        assert response.status_code == 302
        assert response.url == reverse("users:verification_required")

    def test_user_without_merchant_redirected_to_dashboard(self, client):
        orphan_user = User.objects.create_user(
            email="orphan@example.com",
            password="Password123!",
            is_verified=True,
        )
        client.force_login(orphan_user)
        response = client.get(reverse("products:overview"))
        assert response.status_code == 302
        assert response.url == reverse("merchants:dashboard")

    def test_owner_granted_access(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        response = client.get(reverse("products:overview"))
        assert response.status_code == 200
        assert "Product Catalogue" in response.content.decode()

    def test_admin_granted_access(self, client, admin_user, merchant_alpha):
        set_active_merchant(client, admin_user, merchant_alpha)
        response = client.get(reverse("products:overview"))
        assert response.status_code == 200

    def test_manager_granted_access(self, client, manager_user, merchant_alpha):
        set_active_merchant(client, manager_user, merchant_alpha)
        response = client.get(reverse("products:overview"))
        assert response.status_code == 200

    def test_staff_denied_access(self, client, staff_user, merchant_alpha):
        set_active_merchant(client, staff_user, merchant_alpha)
        response = client.get(reverse("products:overview"))
        assert response.status_code == 403

    def test_suspended_merchant_denied_access(self, client, owner_user, merchant_alpha):
        merchant_alpha.status = MerchantStatus.SUSPENDED
        merchant_alpha.save()
        set_active_merchant(client, owner_user, merchant_alpha)

        response = client.get(reverse("products:overview"))
        assert response.status_code == 403

    def test_inactive_merchant_denied_access(self, client, owner_user, merchant_alpha):
        merchant_alpha.status = MerchantStatus.INACTIVE
        merchant_alpha.save()
        set_active_merchant(client, owner_user, merchant_alpha)

        response = client.get(reverse("products:overview"))
        assert response.status_code == 403

    def test_pending_merchant_allowed_catalogue_setup(self, client, owner_user, merchant_alpha):
        merchant_alpha.status = MerchantStatus.PENDING
        merchant_alpha.save()
        set_active_merchant(client, owner_user, merchant_alpha)

        response = client.get(reverse("products:overview"))
        assert response.status_code == 200


@pytest.mark.django_db
class TestCatalogueOverviewView:
    """Verifies overview metrics, storefront status banners, and recent products list."""

    def test_overview_displays_correct_metrics(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)

        create_product(merchant_id=merchant_alpha, actor=owner_user, name="Draft Product")
        p2 = create_product(merchant_id=merchant_alpha, actor=owner_user, name="Published Product")
        p2.status = ProductStatus.PUBLISHED
        p2.save()
        p3 = create_product(merchant_id=merchant_alpha, actor=owner_user, name="Archived Product")
        p3.status = ProductStatus.ARCHIVED
        p3.save()

        create_category(merchant_id=merchant_alpha, actor=owner_user, name="Category 1")
        create_category(
            merchant_id=merchant_alpha, actor=owner_user, name="Category 2", is_active=False
        )

        response = client.get(reverse("products:overview"))
        assert response.status_code == 200
        content = response.content.decode()

        assert "Active Products" in content
        # Total active = 2 (p1 + p2)
        assert response.context["summary"]["total_products"] == 2
        assert response.context["summary"]["published_products"] == 1
        assert response.context["summary"]["draft_products"] == 1
        assert response.context["summary"]["archived_products"] == 1
        assert response.context["summary"]["total_categories"] == 1

    def test_overview_with_published_storefront(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        Store.objects.create(
            merchant=merchant_alpha,
            name="Alpha Store",
            slug="alpha-store",
            status=StoreStatus.PUBLISHED,
        )

        response = client.get(reverse("products:overview"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Storefront is Live" in content
        assert "/s/alpha-store/" in content


@pytest.mark.django_db
class TestProductListView:
    """Verifies listing, pagination, status filtering, category filtering, search, and HTMX."""

    def test_list_displays_products(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Silk Scarf",
            sku="SKU-SILK-01",
            price=Decimal("49.99"),
        )
        create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Wool Scarf",
            sku="SKU-WOOL-01",
            price=Decimal("89.99"),
        )

        response = client.get(reverse("products:product_list"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Silk Scarf" in content
        assert "Wool Scarf" in content
        assert "SKU-SILK-01" in content

    def test_filter_by_status(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        create_product(merchant_id=merchant_alpha, actor=owner_user, name="Draft Item")
        p2 = create_product(merchant_id=merchant_alpha, actor=owner_user, name="Published Item")
        p2.status = ProductStatus.PUBLISHED
        p2.save()

        # Filter Published
        response = client.get(reverse("products:product_list"), {"status": "PUBLISHED"})
        assert response.status_code == 200
        names = [p.name for p in response.context["products"]]
        assert "Published Item" in names
        assert "Draft Item" not in names

        # Filter Draft
        response = client.get(reverse("products:product_list"), {"status": "DRAFT"})
        assert response.status_code == 200
        names = [p.name for p in response.context["products"]]
        assert "Draft Item" in names
        assert "Published Item" not in names

    def test_search_by_name_and_sku(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Leather Jacket",
            sku="LJ-100",
        )
        create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Denim Jacket",
            sku="DJ-200",
        )

        # Search by name
        response = client.get(reverse("products:product_list"), {"q": "Leather"})
        assert response.status_code == 200
        names = [p.name for p in response.context["products"]]
        assert "Leather Jacket" in names
        assert "Denim Jacket" not in names

        # Search by SKU
        response = client.get(reverse("products:product_list"), {"q": "DJ-200"})
        assert response.status_code == 200
        names = [p.name for p in response.context["products"]]
        assert "Denim Jacket" in names
        assert "Leather Jacket" not in names

    def test_filter_by_category(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        cat_shoes = create_category(merchant_id=merchant_alpha, actor=owner_user, name="Shoes")
        cat_hats = create_category(merchant_id=merchant_alpha, actor=owner_user, name="Hats")

        create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Sneakers",
            category_ids=[cat_shoes.id],
        )
        create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Fedora",
            category_ids=[cat_hats.id],
        )

        response = client.get(reverse("products:product_list"), {"category": str(cat_shoes.id)})
        assert response.status_code == 200
        names = [p.name for p in response.context["products"]]
        assert "Sneakers" in names
        assert "Fedora" not in names

    def test_htmx_partial_response(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        create_product(merchant_id=merchant_alpha, actor=owner_user, name="HTMX Test Product")

        response = client.get(reverse("products:product_list"), HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        content = response.content.decode()
        # Should contain partial container, OOB count badge, and product row, but not full base layout
        assert '<div id="products-table-container">' in content
        assert 'id="product-count-badge" hx-swap-oob="true"' in content
        assert "HTMX Test Product" in content
        assert "<html" not in content

    def test_active_filter_includes_published_and_draft_excludes_archived(
        self, client, owner_user, merchant_alpha
    ):
        set_active_merchant(client, owner_user, merchant_alpha)
        p_pub = create_product(merchant_id=merchant_alpha, actor=owner_user, name="Published Tee")
        p_pub.status = ProductStatus.PUBLISHED
        p_pub.save()

        create_product(merchant_id=merchant_alpha, actor=owner_user, name="Draft Tee")

        p_arch = create_product(merchant_id=merchant_alpha, actor=owner_user, name="Archived Tee")
        p_arch.status = ProductStatus.ARCHIVED
        p_arch.save()

        # Default Active (status="")
        response = client.get(reverse("products:product_list"))
        assert response.status_code == 200
        product_names = [p.name for p in response.context["products"]]
        assert "Published Tee" in product_names
        assert "Draft Tee" in product_names
        assert "Archived Tee" not in product_names

        # Explicit Active (status="ACTIVE")
        response_active = client.get(reverse("products:product_list"), {"status": "ACTIVE"})
        assert response_active.status_code == 200
        product_names_active = [p.name for p in response_active.context["products"]]
        assert "Published Tee" in product_names_active
        assert "Draft Tee" in product_names_active
        assert "Archived Tee" not in product_names_active

    def test_archived_filter_only_shows_archived(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        p_pub = create_product(merchant_id=merchant_alpha, actor=owner_user, name="Live Tee")
        p_pub.status = ProductStatus.PUBLISHED
        p_pub.save()

        p_arch = create_product(merchant_id=merchant_alpha, actor=owner_user, name="Old Tee")
        p_arch.status = ProductStatus.ARCHIVED
        p_arch.save()

        response = client.get(reverse("products:product_list"), {"status": "ARCHIVED"})
        assert response.status_code == 200
        product_names = [p.name for p in response.context["products"]]
        assert "Old Tee" in product_names
        assert "Live Tee" not in product_names

    def test_pagination_controls(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        for i in range(18):
            create_product(
                merchant_id=merchant_alpha,
                actor=owner_user,
                name=f"Product {i:02d}",
                sku=f"SKU-{i:02d}",
            )

        response = client.get(reverse("products:product_list"), {"page": 1})
        assert response.status_code == 200
        assert len(response.context["products"]) == 15
        assert response.context["page_obj"].paginator.num_pages == 2
        content = response.content.decode()
        assert "Showing" in content
        assert "Page 1 of 2" in content
        assert "Next" in content

        # Page 2
        response_p2 = client.get(reverse("products:product_list"), {"page": 2})
        assert response_p2.status_code == 200
        assert len(response_p2.context["products"]) == 3
        assert "Previous" in response_p2.content.decode()

    def test_empty_state_no_products(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        response = client.get(reverse("products:product_list"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Your catalogue has no products yet" in content
        assert "Add New Product" in content
        assert "No matching products found" not in content

    def test_empty_state_with_active_filters(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        create_product(merchant_id=merchant_alpha, actor=owner_user, name="Existing Scarf")

        response = client.get(reverse("products:product_list"), {"q": "NonExistentThing"})
        assert response.status_code == 200
        content = response.content.decode()
        assert "No matching products found" in content
        assert "Clear All Filters" in content
        assert "Your catalogue has no products yet" not in content

    def test_full_page_and_htmx_identical_results(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Consistent Product",
            sku="CON-001",
        )

        resp_full = client.get(reverse("products:product_list"))
        resp_htmx = client.get(reverse("products:product_list"), HTTP_HX_REQUEST="true")

        assert resp_full.status_code == 200
        assert resp_htmx.status_code == 200
        assert [p.id for p in resp_full.context["products"]] == [
            p.id for p in resp_htmx.context["products"]
        ]
        assert "Consistent Product" in resp_full.content.decode()
        assert "Consistent Product" in resp_htmx.content.decode()


@pytest.mark.django_db
class TestProductCreateView:
    """Verifies creating products, category assignment, custom attributes, and validation errors."""

    def test_get_create_form(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        response = client.get(reverse("products:product_create"))
        assert response.status_code == 200
        assert "Add New Product" in response.content.decode()

    def test_post_create_product_success(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        cat = create_category(merchant_id=merchant_alpha, actor=owner_user, name="Outerwear")

        payload = {
            "name": "Trench Coat",
            "slug": "trench-coat",
            "sku": "TC-001",
            "description": "Double breasted water-resistant trench coat.",
            "price": "149.99",
            "currency": Currency.INR,
            "is_available": "on",
            "categories": [str(cat.id)],
            "attributes_json": json.dumps({"Color": "Beige", "Size": "M"}),
        }
        response = client.post(reverse("products:product_create"), data=payload)
        assert response.status_code == 302

        product = Product.objects.get(merchant=merchant_alpha, slug="trench-coat")
        assert response.url == reverse("products:product_edit", kwargs={"product_id": product.id})
        assert product.name == "Trench Coat"
        assert product.sku == "TC-001"
        assert product.price == Decimal("149.99")
        assert product.status == ProductStatus.DRAFT
        assert product.is_available is True
        assert product.attributes == {"Color": "Beige", "Size": "M"}
        assert list(product.categories.all()) == [cat]

    def test_create_product_auto_generates_slug_when_blank(
        self, client, owner_user, merchant_alpha
    ):
        set_active_merchant(client, owner_user, merchant_alpha)
        payload = {
            "name": "Summer Linen Shirt",
            "slug": "",
            "currency": Currency.INR,
            "is_available": "on",
        }
        response = client.post(reverse("products:product_create"), data=payload)
        assert response.status_code == 302

        product = Product.objects.get(merchant=merchant_alpha, name="Summer Linen Shirt")
        assert product.slug == "summer-linen-shirt"

    def test_create_product_duplicate_slug_rejected(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Existing Product",
            slug="test-slug",
        )

        payload = {
            "name": "Another Product",
            "slug": "test-slug",
            "currency": Currency.INR,
        }
        response = client.post(reverse("products:product_create"), data=payload)
        assert response.status_code == 200
        assert "already exists in your catalogue" in response.content.decode()

    def test_create_product_duplicate_sku_rejected(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Existing SKU Product",
            sku="SKU-DUP-1",
        )

        payload = {
            "name": "New Product",
            "sku": "SKU-DUP-1",
            "currency": Currency.INR,
        }
        response = client.post(reverse("products:product_create"), data=payload)
        assert response.status_code == 200
        assert "already exists in your catalogue" in response.content.decode()


@pytest.mark.django_db
class TestProductEditView:
    """Verifies editing product details, changing slug, and cross-tenant isolation."""

    def test_get_edit_product(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Leather Boots",
            price=Decimal("199.00"),
        )

        response = client.get(reverse("products:product_edit", kwargs={"product_id": product.id}))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Leather Boots" in content
        assert "199.00" in content

    def test_post_edit_product_success(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Original Name",
            slug="original-slug",
        )

        payload = {
            "name": "Updated Name",
            "slug": "updated-slug",
            "sku": "NEW-SKU-99",
            "description": "Updated description.",
            "price": "79.50",
            "currency": Currency.INR,
            "is_available": "on",
            "attributes_json": json.dumps({"Material": "Cotton"}),
        }
        response = client.post(
            reverse("products:product_edit", kwargs={"product_id": product.id}),
            data=payload,
        )
        assert response.status_code == 302

        product.refresh_from_db()
        assert product.name == "Updated Name"
        assert product.slug == "updated-slug"
        assert product.sku == "NEW-SKU-99"
        assert product.price == Decimal("79.50")
        assert product.attributes == {"Material": "Cotton"}

    def test_cannot_edit_another_merchant_product(
        self, client, owner_user, merchant_alpha, merchant_beta
    ):
        # Create product in Merchant Beta
        beta_product = create_product(
            merchant_id=merchant_beta,
            actor=merchant_beta.owner_user,
            name="Beta Exclusive",
        )

        # Logged in as Merchant Alpha
        set_active_merchant(client, owner_user, merchant_alpha)

        # GET should 404
        response = client.get(
            reverse("products:product_edit", kwargs={"product_id": beta_product.id})
        )
        assert response.status_code == 404

        # POST should 404
        response = client.post(
            reverse("products:product_edit", kwargs={"product_id": beta_product.id}),
            data={"name": "Hacked Name", "currency": Currency.INR},
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestProductLifecycleViews:
    """Verifies publish, unpublish, and archive operations."""

    def test_publish_product(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Draft Item",
        )
        assert product.status == ProductStatus.DRAFT

        response = client.post(
            reverse("products:product_publish", kwargs={"product_id": product.id})
        )
        assert response.status_code == 302

        product.refresh_from_db()
        assert product.status == ProductStatus.PUBLISHED

    def test_unpublish_product(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Live Item",
        )
        product.status = ProductStatus.PUBLISHED
        product.save()

        response = client.post(
            reverse("products:product_unpublish", kwargs={"product_id": product.id})
        )
        assert response.status_code == 302

        product.refresh_from_db()
        assert product.status == ProductStatus.DRAFT

    def test_archive_product(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Item to Archive",
        )

        response = client.post(
            reverse("products:product_archive", kwargs={"product_id": product.id})
        )
        assert response.status_code == 302
        assert response.url == reverse("products:product_list")

        product.refresh_from_db()
        assert product.status == ProductStatus.ARCHIVED

    def test_get_not_allowed_on_lifecycle_actions(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        product = create_product(merchant_id=merchant_alpha, actor=owner_user, name="Item")

        res_pub = client.get(reverse("products:product_publish", kwargs={"product_id": product.id}))
        assert res_pub.status_code == 405

        res_unpub = client.get(
            reverse("products:product_unpublish", kwargs={"product_id": product.id})
        )
        assert res_unpub.status_code == 405

        res_arch = client.get(
            reverse("products:product_archive", kwargs={"product_id": product.id})
        )
        assert res_arch.status_code == 405


@pytest.mark.django_db
class TestProductImageGalleryViews:
    """Verifies gallery image upload, primary thumbnail promotion, and deletion."""

    def test_upload_image_success(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        product = create_product(merchant_id=merchant_alpha, actor=owner_user, name="Item")

        test_img = make_test_image("JPEG", (200, 200))
        response = client.post(
            reverse("products:product_image_upload", kwargs={"product_id": product.id}),
            data={"image": test_img, "alt_text": "Item thumbnail"},
        )
        assert response.status_code == 302

        images = ProductImage.objects.filter(product=product)
        assert images.count() == 1
        assert images.first().is_primary is True
        assert images.first().alt_text == "Item thumbnail"

    def test_upload_invalid_image_rejected(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        product = create_product(merchant_id=merchant_alpha, actor=owner_user, name="Item")

        fake_file = SimpleUploadedFile("fake.png", b"not an image data", content_type="image/png")
        response = client.post(
            reverse("products:product_image_upload", kwargs={"product_id": product.id}),
            data={"image": fake_file},
        )
        assert response.status_code == 302
        assert ProductImage.objects.filter(product=product).count() == 0

    def test_set_primary_image(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        product = create_product(merchant_id=merchant_alpha, actor=owner_user, name="Item")

        img1 = add_product_image(
            product_id=product.id,
            actor=owner_user,
            image_file=make_test_image("PNG"),
        )
        img2 = add_product_image(
            product_id=product.id,
            actor=owner_user,
            image_file=make_test_image("PNG"),
        )
        assert img1.is_primary is True
        assert img2.is_primary is False

        response = client.post(
            reverse("products:product_image_set_primary", kwargs={"image_id": img2.id})
        )
        assert response.status_code == 302

        img1.refresh_from_db()
        img2.refresh_from_db()
        assert img2.is_primary is True
        assert img1.is_primary is False

    def test_delete_image(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        product = create_product(merchant_id=merchant_alpha, actor=owner_user, name="Item")

        img1 = add_product_image(
            product_id=product.id,
            actor=owner_user,
            image_file=make_test_image("PNG"),
        )
        img2 = add_product_image(
            product_id=product.id,
            actor=owner_user,
            image_file=make_test_image("PNG"),
        )

        response = client.post(
            reverse("products:product_image_delete", kwargs={"image_id": img1.id})
        )
        assert response.status_code == 302

        assert not ProductImage.objects.filter(id=img1.id).exists()
        img2.refresh_from_db()
        # Deleted primary image, so next image is promoted to primary
        assert img2.is_primary is True


@pytest.mark.django_db
class TestCategoryViews:
    """Verifies category listing, creation, editing, and active toggling."""

    def test_category_list(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        create_category(merchant_id=merchant_alpha, actor=owner_user, name="Category A")
        create_category(merchant_id=merchant_alpha, actor=owner_user, name="Category B")

        response = client.get(reverse("products:category_list"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Category A" in content
        assert "Category B" in content

    def test_category_create(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        payload = {
            "name": "Accessories",
            "slug": "accessories",
            "description": "Bags, scarves, and jewelry.",
            "display_order": "1",
            "is_active": "on",
        }
        response = client.post(reverse("products:category_create"), data=payload)
        assert response.status_code == 302
        assert response.url == reverse("products:category_list")

        cat = Category.objects.get(merchant=merchant_alpha, slug="accessories")
        assert cat.name == "Accessories"
        assert cat.display_order == 1
        assert cat.is_active is True

    def test_category_edit(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        cat = create_category(merchant_id=merchant_alpha, actor=owner_user, name="Old Name")

        payload = {
            "name": "New Name",
            "slug": "new-name",
            "description": "Updated description.",
            "display_order": "5",
            "is_active": "on",
        }
        response = client.post(
            reverse("products:category_edit", kwargs={"category_id": cat.id}),
            data=payload,
        )
        assert response.status_code == 302

        cat.refresh_from_db()
        assert cat.name == "New Name"
        assert cat.display_order == 5

    def test_category_toggle_active(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        cat = create_category(
            merchant_id=merchant_alpha, actor=owner_user, name="Active Cat", is_active=True
        )

        response = client.post(reverse("products:category_toggle", kwargs={"category_id": cat.id}))
        assert response.status_code == 302

        cat.refresh_from_db()
        assert cat.is_active is False

        # Toggle back
        client.post(reverse("products:category_toggle", kwargs={"category_id": cat.id}))
        cat.refresh_from_db()
        assert cat.is_active is True


@pytest.mark.django_db
class TestSlugCheckEndpoints:
    """Verifies real-time slug format and collision endpoints."""

    def test_product_slug_check_available(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        response = client.get(
            reverse("products:product_slug_check"),
            {"slug": "unique-product-slug"},
        )
        assert response.status_code == 200
        assert "Slug is available!" in response.content.decode()

    def test_product_slug_check_already_taken(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Existing Product",
            slug="taken-slug",
        )

        response = client.get(
            reverse("products:product_slug_check"),
            {"slug": "taken-slug"},
        )
        assert response.status_code == 200
        assert "already used by another product" in response.content.decode()

    def test_category_slug_check_available(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        response = client.get(
            reverse("products:category_slug_check"),
            {"slug": "unique-cat-slug"},
        )
        assert response.status_code == 200
        assert "Slug is available!" in response.content.decode()


@pytest.mark.django_db
class TestResponsiveUIElements:
    """Verifies compliance with frontend.md design and responsive guidelines."""

    def test_product_list_responsive_views_and_touch_targets(
        self, client, owner_user, merchant_alpha
    ):
        set_active_merchant(client, owner_user, merchant_alpha)
        create_product(merchant_id=merchant_alpha, actor=owner_user, name="Responsive Product")

        response = client.get(reverse("products:product_list"))
        assert response.status_code == 200
        content = response.content.decode()

        # Responsive layout classes
        assert "hidden md:block" in content  # Desktop table container
        assert "md:hidden" in content  # Mobile cards container
        assert "min-h-[44px]" in content  # Mobile 44px min touch target

        # Active navigation link
        assert 'aria-current="page"' in content

    def test_product_form_responsive_controls(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        response = client.get(reverse("products:product_create"))
        assert response.status_code == 200
        content = response.content.decode()

        # Grid responsive breakpoints
        assert "grid-cols-1 sm:grid-cols-2" in content
        assert "focus:ring-indigo-500" in content

    def test_category_list_responsive_views(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)
        create_category(merchant_id=merchant_alpha, actor=owner_user, name="Responsive Category")

        response = client.get(reverse("products:category_list"))
        assert response.status_code == 200
        content = response.content.decode()

        assert "hidden md:block" in content
        assert "md:hidden" in content
        assert "min-h-[44px]" in content
