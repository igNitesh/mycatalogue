from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.products.choices import Currency, ProductStatus
from apps.products.models import Category, Product, ProductCategory, ProductImage
from apps.products.tests.conftest import make_test_image


@pytest.mark.django_db
class TestCategoryModel:
    """Verifies Category model constraints, slug normalization, and per-merchant scoping."""

    def test_category_creation_and_defaults(self, merchant_alpha):
        category = Category.objects.create(
            merchant=merchant_alpha,
            name="Summer Apparel",
            slug="summer-apparel",
        )
        assert category.id is not None
        assert category.is_active is True
        assert category.display_order == 0
        assert category.created_at is not None
        assert category.updated_at is not None
        assert "Summer Apparel" in str(category)

    def test_category_slug_unique_per_merchant(self, merchant_alpha):
        Category.objects.create(
            merchant=merchant_alpha,
            name="Footwear",
            slug="footwear",
        )
        with pytest.raises(IntegrityError):
            Category.objects.create(
                merchant=merchant_alpha,
                name="Footwear Duplicate",
                slug="FOOTWEAR",  # Case-insensitive collision
            )

    def test_same_category_slug_allowed_for_different_merchants(
        self, merchant_alpha, merchant_beta
    ):
        cat_alpha = Category.objects.create(
            merchant=merchant_alpha,
            name="Accessories",
            slug="accessories",
        )
        cat_beta = Category.objects.create(
            merchant=merchant_beta,
            name="Accessories",
            slug="accessories",
        )
        assert cat_alpha.slug == cat_beta.slug
        assert cat_alpha.merchant != cat_beta.merchant


@pytest.mark.django_db
class TestProductModel:
    """Verifies Product model constraints, SKU uniqueness, and price check constraints."""

    def test_product_creation_and_defaults(self, merchant_alpha):
        product = Product.objects.create(
            merchant=merchant_alpha,
            name="Classic Polo",
            slug="classic-polo",
        )
        assert product.id is not None
        assert product.status == ProductStatus.DRAFT
        assert product.is_available is True
        assert product.currency == Currency.INR
        assert product.price is None
        assert product.sku is None
        assert product.attributes == {}
        assert "Classic Polo" in str(product)

    def test_product_slug_unique_per_merchant(self, merchant_alpha):
        Product.objects.create(
            merchant=merchant_alpha,
            name="Linen Shirt",
            slug="linen-shirt",
        )
        with pytest.raises(IntegrityError):
            Product.objects.create(
                merchant=merchant_alpha,
                name="Another Shirt",
                slug="LINEN-SHIRT",  # Case-insensitive expression collision
            )

    def test_same_product_slug_allowed_for_different_merchants(self, merchant_alpha, merchant_beta):
        p_alpha = Product.objects.create(
            merchant=merchant_alpha,
            name="Denim Jeans",
            slug="denim-jeans",
        )
        p_beta = Product.objects.create(
            merchant=merchant_beta,
            name="Denim Jeans",
            slug="denim-jeans",
        )
        assert p_alpha.slug == p_beta.slug
        assert p_alpha.merchant != p_beta.merchant

    def test_sku_uniqueness_per_merchant(self, merchant_alpha):
        Product.objects.create(
            merchant=merchant_alpha,
            name="Item A",
            slug="item-a",
            sku="SKU-1001",
        )
        with pytest.raises(IntegrityError):
            Product.objects.create(
                merchant=merchant_alpha,
                name="Item B",
                slug="item-b",
                sku="SKU-1001",
            )

    def test_multiple_empty_or_null_skus_permitted(self, merchant_alpha):
        p1 = Product.objects.create(
            merchant=merchant_alpha,
            name="Item 1",
            slug="item-1",
            sku=None,
        )
        p2 = Product.objects.create(
            merchant=merchant_alpha,
            name="Item 2",
            slug="item-2",
            sku=None,
        )
        p3 = Product.objects.create(
            merchant=merchant_alpha,
            name="Item 3",
            slug="item-3",
            sku="",
        )
        assert p1.id and p2.id and p3.id

    def test_same_sku_allowed_across_different_merchants(self, merchant_alpha, merchant_beta):
        p_alpha = Product.objects.create(
            merchant=merchant_alpha,
            name="Alpha SKU Item",
            slug="alpha-item",
            sku="COMMON-SKU-99",
        )
        p_beta = Product.objects.create(
            merchant=merchant_beta,
            name="Beta SKU Item",
            slug="beta-item",
            sku="COMMON-SKU-99",
        )
        assert p_alpha.sku == p_beta.sku
        assert p_alpha.merchant != p_beta.merchant

    def test_price_non_negative_check_constraint(self, merchant_alpha):
        with pytest.raises(IntegrityError):
            Product.objects.create(
                merchant=merchant_alpha,
                name="Negative Price Item",
                slug="negative-item",
                price=Decimal("-10.00"),
            )

    def test_valid_zero_and_positive_prices(self, merchant_alpha):
        p_zero = Product.objects.create(
            merchant=merchant_alpha,
            name="Free Sample",
            slug="free-sample",
            price=Decimal("0.00"),
        )
        p_paid = Product.objects.create(
            merchant=merchant_alpha,
            name="Luxury Watch",
            slug="luxury-watch",
            price=Decimal("24999.50"),
        )
        assert p_zero.price == Decimal("0.00")
        assert p_paid.price == Decimal("24999.50")


@pytest.mark.django_db
class TestProductImageModel:
    """Verifies ProductImage gallery constraints, ordering, and single-primary limit."""

    def test_at_most_one_primary_image_per_product(self, merchant_alpha):
        product = Product.objects.create(
            merchant=merchant_alpha,
            name="Camera",
            slug="camera",
        )
        img1 = make_test_image()
        img2 = make_test_image()

        ProductImage.objects.create(
            product=product,
            image=img1,
            is_primary=True,
            display_order=0,
        )

        with pytest.raises(IntegrityError):
            ProductImage.objects.create(
                product=product,
                image=img2,
                is_primary=True,  # Duplicate primary
                display_order=1,
            )

    def test_multiple_non_primary_images_allowed(self, merchant_alpha):
        product = Product.objects.create(
            merchant=merchant_alpha,
            name="Handbag",
            slug="handbag",
        )
        img1 = make_test_image()
        img2 = make_test_image()

        pi1 = ProductImage.objects.create(product=product, image=img1, is_primary=False)
        pi2 = ProductImage.objects.create(product=product, image=img2, is_primary=False)

        assert pi1.id and pi2.id
        assert product.images.count() == 2
        assert product.primary_image is None


@pytest.mark.django_db
class TestProductCategoryModel:
    """Verifies ProductCategory through-model constraints and assignments."""

    def test_unique_product_category_assignment(self, merchant_alpha):
        product = Product.objects.create(
            merchant=merchant_alpha,
            name="Shoes",
            slug="shoes",
        )
        category = Category.objects.create(
            merchant=merchant_alpha,
            name="Footwear",
            slug="footwear",
        )

        ProductCategory.objects.create(product=product, category=category)

        with pytest.raises(IntegrityError):
            ProductCategory.objects.create(product=product, category=category)

    def test_model_string_representations_and_clean(self, merchant_alpha):
        cat = Category(
            merchant=merchant_alpha,
            name="Dresses",
            slug="Dresses & Gowns",
        )
        cat.clean()  # Normalizes slug from title
        cat.full_clean()
        cat.save()
        assert cat.slug == "dresses-gowns"

        product = Product(
            merchant=merchant_alpha,
            name="Evening Gown",
            slug="Evening Gown",
            sku="  SKU-GOWN-1  ",
            attributes={"Fabric": "Silk"},
        )
        product.clean()  # Normalizes slug and strips SKU
        product.full_clean()
        product.save()
        assert product.slug == "evening-gown"
        assert product.sku == "SKU-GOWN-1"

        link = ProductCategory.objects.create(product=product, category=cat)
        assert "Evening Gown -> Dresses" in str(link)

        img = ProductImage.objects.create(
            product=product,
            image=make_test_image(),
            display_order=0,
            is_primary=True,
        )
        assert "Evening Gown" in str(img)

        # Post-delete signal file cleanup
        assert img.image.path
        img.delete()
        # Verify post-delete cleanup didn't crash and path was tracked
