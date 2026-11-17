from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.products.choices import Currency, ProductStatus
from apps.products.exceptions import (
    CategoryNotFoundError,
    CategorySlugAlreadyTakenError,
    DuplicateSKUError,
    InvalidProductImageError,
    ProductLifecycleError,
    ProductNotFoundError,
    ProductSlugAlreadyTakenError,
)
from apps.products.services import (
    add_product_image,
    archive_product,
    assign_product_categories,
    change_product_slug,
    create_category,
    create_product,
    deactivate_category,
    publish_product,
    remove_product_image,
    set_primary_product_image,
    unpublish_product,
    update_category,
    update_product_profile,
)
from apps.products.tests.conftest import make_test_image


@pytest.mark.django_db
class TestProductServices:
    """Verifies domain services for product creation, updating, and lifecycle."""

    def test_create_product_success(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Handcrafted Mug",
            price=Decimal("450.00"),
            currency=Currency.INR,
            sku="MUG-001",
            description="Ceramic glazed mug.",
            attributes={"Material": "Ceramic", "Capacity": "350ml"},
        )
        assert product.id is not None
        assert product.name == "Handcrafted Mug"
        assert product.slug == "handcrafted-mug"
        assert product.sku == "MUG-001"
        assert product.price == Decimal("450.00")
        assert product.status == ProductStatus.DRAFT
        assert product.is_available is True
        assert product.attributes["Material"] == "Ceramic"

    def test_create_product_requires_actor(self, merchant_alpha):
        with pytest.raises(TypeError, match="actor is required"):
            create_product(
                merchant_id=merchant_alpha,
                actor=None,
                name="Orphan Product",
            )

    def test_create_product_with_explicit_slug(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Formal Oxford Shoes",
            slug="mens-oxford-shoes",
        )
        assert product.slug == "mens-oxford-shoes"

    def test_create_product_duplicate_slug_rejected(self, merchant_alpha, owner_user):
        create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Silk Scarf",
            slug="silk-scarf",
        )
        with pytest.raises(ProductSlugAlreadyTakenError):
            create_product(
                merchant_id=merchant_alpha,
                actor=owner_user,
                name="Silk Scarf Duplicate",
                slug="silk-scarf",
            )

    def test_create_product_duplicate_sku_rejected(self, merchant_alpha, owner_user):
        create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Item 1",
            sku="UNIQUE-1",
        )
        with pytest.raises(DuplicateSKUError):
            create_product(
                merchant_id=merchant_alpha,
                actor=owner_user,
                name="Item 2",
                sku="UNIQUE-1",
            )

    def test_create_product_negative_price_rejected(self, merchant_alpha, owner_user):
        with pytest.raises(ValidationError, match="cannot be negative"):
            create_product(
                merchant_id=merchant_alpha,
                actor=owner_user,
                name="Discounted Item",
                price=Decimal("-1.00"),
            )

    def test_update_product_profile_success(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Table Lamp",
            price=Decimal("1200.00"),
        )
        updated = update_product_profile(
            product_id=product.id,
            actor=owner_user,
            name="Modern Desk Lamp",
            price=Decimal("1450.00"),
            is_available=False,
            attributes={"Bulb Type": "LED"},
        )
        assert updated.name == "Modern Desk Lamp"
        assert updated.price == Decimal("1450.00")
        assert updated.is_available is False
        assert updated.attributes["Bulb Type"] == "LED"

    def test_update_product_duplicate_sku_rejected(self, merchant_alpha, owner_user):
        create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="First",
            sku="SKU-AAA",
        )
        p2 = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Second",
            sku="SKU-BBB",
        )
        with pytest.raises(DuplicateSKUError):
            update_product_profile(
                product_id=p2.id,
                actor=owner_user,
                sku="SKU-AAA",
            )

    def test_change_product_slug(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Old Name",
            slug="old-slug",
        )
        updated = change_product_slug(
            product_id=product.id,
            actor=owner_user,
            new_slug="new-improved-slug",
        )
        assert updated.slug == "new-improved-slug"

    def test_change_product_slug_collision_rejected(self, merchant_alpha, owner_user):
        create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Product A",
            slug="product-a",
        )
        p2 = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Product B",
            slug="product-b",
        )
        with pytest.raises(ProductSlugAlreadyTakenError):
            change_product_slug(
                product_id=p2.id,
                actor=owner_user,
                new_slug="product-a",
            )


@pytest.mark.django_db
class TestProductLifecycleServices:
    """Verifies DRAFT <-> PUBLISHED <-> ARCHIVED status transitions."""

    def test_publish_and_unpublish_product(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Lifecycle Item",
        )
        assert product.status == ProductStatus.DRAFT

        # DRAFT -> PUBLISHED
        published = publish_product(product_id=product.id, actor=owner_user)
        assert published.status == ProductStatus.PUBLISHED

        # Idempotent re-publish
        published_again = publish_product(product_id=product.id, actor=owner_user)
        assert published_again.status == ProductStatus.PUBLISHED

        # PUBLISHED -> DRAFT (Unpublish)
        unpublished = unpublish_product(product_id=product.id, actor=owner_user)
        assert unpublished.status == ProductStatus.DRAFT

    def test_archive_product(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Discontinued Item",
        )
        archived = archive_product(product_id=product.id, actor=owner_user)
        assert archived.status == ProductStatus.ARCHIVED

        # Attempt to publish archived product is strictly blocked
        with pytest.raises(ProductLifecycleError, match="Cannot publish an archived product"):
            publish_product(product_id=product.id, actor=owner_user)

        with pytest.raises(ProductLifecycleError, match="Cannot unpublish an archived product"):
            unpublish_product(product_id=product.id, actor=owner_user)


@pytest.mark.django_db
class TestCategoryServices:
    """Verifies Category creation, updating, and deactivation services."""

    def test_create_category_success(self, merchant_alpha, owner_user):
        cat = create_category(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Winter Collection",
            slug="winter-collection",
            description="Warm winter wear",
            display_order=5,
        )
        assert cat.id is not None
        assert cat.name == "Winter Collection"
        assert cat.slug == "winter-collection"
        assert cat.display_order == 5
        assert cat.is_active is True

    def test_create_category_duplicate_slug_rejected(self, merchant_alpha, owner_user):
        create_category(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Jewelry",
            slug="jewelry",
        )
        with pytest.raises(CategorySlugAlreadyTakenError):
            create_category(
                merchant_id=merchant_alpha,
                actor=owner_user,
                name="Fine Jewelry",
                slug="jewelry",
            )

    def test_update_and_deactivate_category(self, merchant_alpha, owner_user):
        cat = create_category(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Sale",
            slug="sale",
        )
        updated = update_category(
            category_id=cat.id,
            actor=owner_user,
            name="Flash Sale",
            display_order=1,
        )
        assert updated.name == "Flash Sale"
        assert updated.display_order == 1

        deactivated = deactivate_category(category_id=cat.id, actor=owner_user)
        assert deactivated.is_active is False


@pytest.mark.django_db
class TestProductCategoryAssignmentService:
    """Verifies atomic category assignment and detachment."""

    def test_assign_and_reassign_categories(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Leather Belt",
        )
        c1 = create_category(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Men",
            slug="men",
        )
        c2 = create_category(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Accessories",
            slug="accessories",
        )
        c3 = create_category(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Gifts",
            slug="gifts",
        )

        # Assign c1 and c2
        assign_product_categories(
            product_id=product.id,
            actor=owner_user,
            category_ids=[c1.id, c2.id],
        )
        assert product.categories.count() == 2
        assert set(product.categories.all()) == {c1, c2}

        # Reassign to c2 and c3 (removes c1, adds c3)
        assign_product_categories(
            product_id=product.id,
            actor=owner_user,
            category_ids=[c2.id, c3.id],
        )
        assert product.categories.count() == 2
        assert set(product.categories.all()) == {c2, c3}

        # Clear categories
        assign_product_categories(
            product_id=product.id,
            actor=owner_user,
            category_ids=[],
        )
        assert product.categories.count() == 0

    def test_assign_nonexistent_category_fails(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Purse",
        )
        with pytest.raises(CategoryNotFoundError):
            assign_product_categories(
                product_id=product.id,
                actor=owner_user,
                category_ids=["00000000-0000-0000-0000-000000000000"],
            )


@pytest.mark.django_db
class TestProductImageServices:
    """Verifies image uploads, format restrictions, Pillow verification, and primary image management."""

    def test_add_product_image_auto_sets_first_image_as_primary(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Sneakers",
        )
        img_file = make_test_image("JPEG", (200, 200))
        img1 = add_product_image(
            product_id=product.id,
            actor=owner_user,
            image_file=img_file,
            alt_text="Front view of sneakers",
        )
        assert img1.id is not None
        assert img1.is_primary is True
        assert product.primary_image.id == img1.id

    def test_add_second_image_as_primary_updates_old_primary(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Watch",
        )
        img1 = add_product_image(
            product_id=product.id,
            actor=owner_user,
            image_file=make_test_image("PNG"),
            is_primary=True,
        )
        assert img1.is_primary is True

        # Upload second image and designate as primary
        img2 = add_product_image(
            product_id=product.id,
            actor=owner_user,
            image_file=make_test_image("PNG"),
            is_primary=True,
        )
        img1.refresh_from_db()
        assert img1.is_primary is False
        assert img2.is_primary is True
        assert product.primary_image.id == img2.id

    def test_add_image_rejects_oversized_file(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Book",
        )
        oversized_data = b"x" * (5 * 1024 * 1024 + 500)
        oversized_file = SimpleUploadedFile("big.png", oversized_data, content_type="image/png")

        with pytest.raises(InvalidProductImageError, match="exceeds the 5 MB limit"):
            add_product_image(
                product_id=product.id,
                actor=owner_user,
                image_file=oversized_file,
            )

    def test_add_image_rejects_corrupted_file(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Phone",
        )
        corrupt_file = SimpleUploadedFile(
            "corrupt.png", b"\x89PNG\r\n\x1a\nCorruptBytes", content_type="image/png"
        )
        with pytest.raises(InvalidProductImageError, match="not a valid or readable image"):
            add_product_image(
                product_id=product.id,
                actor=owner_user,
                image_file=corrupt_file,
            )

    def test_add_image_rejects_unsupported_format(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Toy",
        )
        gif_file = make_test_image("GIF")
        with pytest.raises(InvalidProductImageError, match="Unsupported image format"):
            add_product_image(
                product_id=product.id,
                actor=owner_user,
                image_file=gif_file,
            )

    def test_remove_primary_image_promotes_next_image(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Backpack",
        )
        img1 = add_product_image(
            product_id=product.id,
            actor=owner_user,
            image_file=make_test_image("PNG"),
            display_order=0,
            is_primary=True,
        )
        img2 = add_product_image(
            product_id=product.id,
            actor=owner_user,
            image_file=make_test_image("PNG"),
            display_order=1,
            is_primary=False,
        )

        remove_product_image(image_id=img1.id, actor=owner_user)
        img2.refresh_from_db()
        assert img2.is_primary is True

    def test_set_primary_product_image(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Wallet",
        )
        img1 = add_product_image(
            product_id=product.id,
            actor=owner_user,
            image_file=make_test_image("PNG"),
            is_primary=True,
        )
        img2 = add_product_image(
            product_id=product.id,
            actor=owner_user,
            image_file=make_test_image("PNG"),
            is_primary=False,
        )

        set_primary_product_image(image_id=img2.id, actor=owner_user)
        img1.refresh_from_db()
        img2.refresh_from_db()
        assert img1.is_primary is False
        assert img2.is_primary is True

    def test_nonexistent_product_or_image_errors(self, owner_user):
        missing_id = "00000000-0000-0000-0000-000000000000"
        with pytest.raises(ProductNotFoundError):
            update_product_profile(product_id=missing_id, actor=owner_user, name="X")

        with pytest.raises(ProductNotFoundError):
            change_product_slug(product_id=missing_id, actor=owner_user, new_slug="x")

        with pytest.raises(ProductNotFoundError):
            publish_product(product_id=missing_id, actor=owner_user)

        with pytest.raises(ProductNotFoundError):
            unpublish_product(product_id=missing_id, actor=owner_user)

        with pytest.raises(ProductNotFoundError):
            archive_product(product_id=missing_id, actor=owner_user)

        with pytest.raises(CategoryNotFoundError):
            update_category(category_id=missing_id, actor=owner_user, name="X")

        with pytest.raises(InvalidProductImageError):
            remove_product_image(image_id=missing_id, actor=owner_user)

        with pytest.raises(InvalidProductImageError):
            set_primary_product_image(image_id=missing_id, actor=owner_user)

    def test_lifecycle_and_slug_noop_branches(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Noop Item",
            slug="noop-item",
        )
        # unpublish when already DRAFT is a noop
        unpub = unpublish_product(product_id=product.id, actor=owner_user)
        assert unpub.status == ProductStatus.DRAFT

        # archive
        arch = archive_product(product_id=product.id, actor=owner_user)
        assert arch.status == ProductStatus.ARCHIVED

        # archive when already ARCHIVED is a noop
        arch2 = archive_product(product_id=product.id, actor=owner_user)
        assert arch2.status == ProductStatus.ARCHIVED

        # change_product_slug to identical slug is a noop
        p2 = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Same Slug Item",
            slug="same-slug",
        )
        same = change_product_slug(product_id=p2.id, actor=owner_user, new_slug="SAME-SLUG")
        assert same.slug == "same-slug"
