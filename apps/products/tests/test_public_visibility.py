import pytest

from apps.merchants.choices import MerchantStatus
from apps.products.selectors import (
    get_merchant_categories,
    get_merchant_products,
    get_public_storefront_products,
)
from apps.products.services import (
    archive_product,
    assign_product_categories,
    create_category,
    create_product,
    publish_product,
)
from apps.stores.choices import StoreStatus


@pytest.mark.django_db
class TestPublicStorefrontVisibility:
    """
    Verifies that public product presentation strictly enforces the
    hierarchical visibility invariant:
    Product is PUBLISHED AND Merchant is ACTIVE AND Store is PUBLISHED.
    """

    def test_published_product_with_active_merchant_and_store_is_visible(
        self, merchant_alpha, store_alpha, owner_user
    ):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Visible Silk Shirt",
        )
        publish_product(product_id=product.id, actor=owner_user)

        qs = get_public_storefront_products(merchant=merchant_alpha)
        assert qs.filter(id=product.id).exists()

    def test_draft_and_archived_products_are_hidden_from_public(
        self, merchant_alpha, store_alpha, owner_user
    ):
        p_draft = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Draft Item",
        )
        p_archived = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Archived Item",
        )
        archive_product(product_id=p_archived.id, actor=owner_user)

        qs = get_public_storefront_products(merchant=merchant_alpha)
        assert not qs.filter(id=p_draft.id).exists()
        assert not qs.filter(id=p_archived.id).exists()

    def test_unavailable_published_product_remains_visible_with_out_of_stock_state(
        self, merchant_alpha, store_alpha, owner_user
    ):
        """is_available=False indicates out of stock, NOT hiding/unpublishing the item."""
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Out of Stock Jacket",
        )
        publish_product(product_id=product.id, actor=owner_user)
        product.is_available = False
        product.save(update_fields=["is_available"])

        qs = get_public_storefront_products(merchant=merchant_alpha)
        assert qs.filter(id=product.id).exists()
        fetched = qs.get(id=product.id)
        assert fetched.is_available is False

    def test_inactive_or_suspended_merchant_hides_all_products(
        self, merchant_alpha, store_alpha, owner_user
    ):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Shirt",
        )
        publish_product(product_id=product.id, actor=owner_user)

        # Suspended merchant
        merchant_alpha.status = MerchantStatus.SUSPENDED
        merchant_alpha.save()
        assert get_public_storefront_products(merchant=merchant_alpha).count() == 0

        # Inactive merchant
        merchant_alpha.status = MerchantStatus.INACTIVE
        merchant_alpha.save()
        assert get_public_storefront_products(merchant=merchant_alpha).count() == 0

        # Pending merchant
        merchant_alpha.status = MerchantStatus.PENDING
        merchant_alpha.save()
        assert get_public_storefront_products(merchant=merchant_alpha).count() == 0

    def test_draft_or_unpublished_store_hides_all_products(
        self, merchant_alpha, store_alpha, owner_user
    ):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Jeans",
        )
        publish_product(product_id=product.id, actor=owner_user)

        # Draft store
        store_alpha.status = StoreStatus.DRAFT
        store_alpha.save()
        assert get_public_storefront_products(merchant=merchant_alpha).count() == 0

        # Unpublished store
        store_alpha.status = StoreStatus.UNPUBLISHED
        store_alpha.save()
        assert get_public_storefront_products(merchant=merchant_alpha).count() == 0

    def test_category_filtered_public_products(self, merchant_alpha, store_alpha, owner_user):
        cat_active = create_category(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Summer",
            slug="summer",
            is_active=True,
        )
        cat_inactive = create_category(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Winter",
            slug="winter",
            is_active=False,
        )

        p1 = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="T-Shirt",
        )
        publish_product(product_id=p1.id, actor=owner_user)
        assign_product_categories(
            product_id=p1.id,
            actor=owner_user,
            category_ids=[cat_active.id],
        )

        p2 = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Wool Coat",
        )
        publish_product(product_id=p2.id, actor=owner_user)
        assign_product_categories(
            product_id=p2.id,
            actor=owner_user,
            category_ids=[cat_inactive.id],
        )

        # Active category filter returns product
        qs_active = get_public_storefront_products(
            merchant=merchant_alpha,
            category_slug="summer",
        )
        assert qs_active.filter(id=p1.id).exists()
        assert not qs_active.filter(id=p2.id).exists()

        # Inactive category filter returns empty queryset
        qs_inactive = get_public_storefront_products(
            merchant=merchant_alpha,
            category_slug="winter",
        )
        assert qs_inactive.count() == 0


@pytest.mark.django_db
class TestMerchantDashboardSelectors:
    """Verifies internal merchant selectors for dashboard and management."""

    def test_get_merchant_products_filters_archived(self, merchant_alpha, owner_user):
        p_draft = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Draft",
        )
        p_published = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Published",
        )
        publish_product(product_id=p_published.id, actor=owner_user)

        p_archived = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Archived",
        )
        archive_product(product_id=p_archived.id, actor=owner_user)

        # Default excludes archived
        default_qs = get_merchant_products(merchant=merchant_alpha)
        assert default_qs.filter(id=p_draft.id).exists()
        assert default_qs.filter(id=p_published.id).exists()
        assert not default_qs.filter(id=p_archived.id).exists()

        # With include_archived=True
        full_qs = get_merchant_products(merchant=merchant_alpha, include_archived=True)
        assert full_qs.filter(id=p_archived.id).exists()

    def test_get_merchant_categories_active_filtering(self, merchant_alpha, owner_user):
        c_active = create_category(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Active Cat",
            is_active=True,
        )
        c_inactive = create_category(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Inactive Cat",
            is_active=False,
        )

        active_only = get_merchant_categories(merchant=merchant_alpha)
        assert active_only.filter(id=c_active.id).exists()
        assert not active_only.filter(id=c_inactive.id).exists()

        all_cats = get_merchant_categories(merchant=merchant_alpha, include_inactive=True)
        assert all_cats.filter(id=c_active.id).exists()
        assert all_cats.filter(id=c_inactive.id).exists()
