"""
Query selectors for products and categories.
Separates query logic from business services and presentation views.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q, QuerySet

from apps.merchants.choices import MerchantStatus
from apps.merchants.models import Merchant
from apps.stores.choices import StoreStatus

from .choices import ProductStatus
from .models import Category, Product, ProductImage


def get_catalogue_summary(merchant: Merchant) -> dict[str, int]:
    """
    Returns aggregate summary counts for the merchant's catalogue overview:
    - total_products: count of active products (PUBLISHED + DRAFT)
    - published_products: count of published products
    - draft_products: count of draft products
    - archived_products: count of archived products
    - total_categories: count of active categories
    """
    if not merchant:
        return {
            "total_products": 0,
            "published_products": 0,
            "draft_products": 0,
            "archived_products": 0,
            "total_categories": 0,
        }

    counts = Product.objects.filter(merchant=merchant).aggregate(
        published=Count("id", filter=Q(status=ProductStatus.PUBLISHED)),
        draft=Count("id", filter=Q(status=ProductStatus.DRAFT)),
        archived=Count("id", filter=Q(status=ProductStatus.ARCHIVED)),
    )
    published = counts["published"] or 0
    draft = counts["draft"] or 0
    archived = counts["archived"] or 0
    total_categories = Category.objects.filter(merchant=merchant, is_active=True).count()

    return {
        "total_products": published + draft,
        "published_products": published,
        "draft_products": draft,
        "archived_products": archived,
        "total_categories": total_categories,
    }


def get_merchant_categories(
    merchant: Merchant,
    include_inactive: bool = False,
) -> QuerySet[Category]:
    """
    Returns categories belonging to the specified merchant.
    Ordered by display_order then name.
    """
    if not merchant:
        return Category.objects.none()

    qs = Category.objects.filter(merchant=merchant)
    if not include_inactive:
        qs = qs.filter(is_active=True)
    return qs.order_by("display_order", "name")


def get_merchant_products(
    merchant: Merchant,
    include_archived: bool = False,
    category: Category | None = None,
    status: str | None = None,
    search_query: str | None = None,
) -> QuerySet[Product]:
    """
    Returns products belonging to the specified merchant for merchant dashboard/management.
    Supports optional status filtering and search query on name and SKU.
    Excludes ARCHIVED products by default unless include_archived is True or status is ARCHIVED.
    """
    if not merchant:
        return Product.objects.none()

    qs = (
        Product.objects.filter(merchant=merchant)
        .prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.order_by("display_order", "created_at"),
            ),
            "categories",
        )
        .order_by("-created_at")
    )

    if status:
        status_clean = status.strip().upper()
        if status_clean == ProductStatus.ARCHIVED:
            qs = qs.filter(status=ProductStatus.ARCHIVED)
        else:
            qs = qs.filter(status=status_clean)
    elif not include_archived:
        qs = qs.exclude(status=ProductStatus.ARCHIVED)

    if category is not None:
        qs = qs.filter(categories=category)

    if search_query:
        search_str = search_query.strip()
        if search_str:
            qs = qs.filter(Q(name__icontains=search_str) | Q(sku__icontains=search_str))

    return qs


def get_product_for_merchant(
    product_id: uuid.UUID | str,
    merchant: Merchant,
) -> Product | None:
    """
    Safely retrieves a product strictly scoped to the active merchant.
    """
    if not product_id or not merchant:
        return None
    try:
        return (
            Product.objects.filter(merchant=merchant, id=product_id)
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by("display_order", "created_at"),
                ),
                "categories",
            )
            .first()
        )
    except (ValueError, ValidationError):
        return None


def get_category_for_merchant(
    category_id: uuid.UUID | str,
    merchant: Merchant,
) -> Category | None:
    """
    Safely retrieves a category strictly scoped to the active merchant.
    """
    if not category_id or not merchant:
        return None
    try:
        return Category.objects.filter(merchant=merchant, id=category_id).first()
    except (ValueError, ValidationError):
        return None


def get_public_storefront_products(
    merchant: Merchant,
    category_slug: str | None = None,
) -> QuerySet[Product]:
    """
    Returns published products for customer-facing digital storefront browsing.

    Hierarchical Public Visibility Invariant:
    1. Merchant status must be strictly ACTIVE.
    2. Store must exist, be in PUBLISHED status, and be publicly accessible.
    3. Product status must be strictly PUBLISHED.
    4. Note: is_available=False does NOT hide the product; it displays with an out-of-stock badge.
    5. If category_slug is provided, the category must belong to this merchant and be active.
    """
    if not merchant or merchant.status != MerchantStatus.ACTIVE:
        return Product.objects.none()

    # Verify store status and accessibility
    store = getattr(merchant, "store", None)
    if not store or store.status != StoreStatus.PUBLISHED or not store.is_publicly_accessible:
        return Product.objects.none()

    qs = (
        Product.objects.filter(
            merchant=merchant,
            status=ProductStatus.PUBLISHED,
        )
        .prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.filter(is_primary=True),
                to_attr="primary_images",
            ),
            Prefetch(
                "categories",
                queryset=Category.objects.filter(is_active=True),
            ),
        )
        .order_by("name")
    )

    if category_slug:
        # Category must belong to this merchant and be active
        category = Category.objects.filter(
            merchant=merchant,
            slug=category_slug.lower(),
            is_active=True,
        ).first()

        if not category:
            return Product.objects.none()

        qs = qs.filter(categories=category)

    return qs
