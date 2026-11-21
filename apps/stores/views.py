from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from apps.products.choices import AvailabilityMode, ProductStatus
from apps.products.models import Product
from apps.products.selectors import (
    get_merchant_categories,
    get_public_storefront_products,
)

from .selectors import get_public_store_by_slug


def public_store_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """
    Public storefront landing homepage view.
    Only accessible if the Store is PUBLISHED and its Merchant is ACTIVE.
    Renders store branding, active categories, latest published products,
    and safe merchant contact information.
    """
    store = get_public_store_by_slug(slug)
    if not store:
        raise Http404("Store not found or is not currently active.")

    categories = get_merchant_categories(store.merchant)
    latest_products = get_public_storefront_products(
        merchant=store.merchant,
        ordering="-created_at",
    )[:8]
    total_products = Product.objects.filter(
        merchant=store.merchant,
        status=ProductStatus.PUBLISHED,
    ).count()

    owner_membership = (
        store.merchant.memberships.filter(role="OWNER").select_related("user").first()
    )
    owner_name = ""
    if owner_membership and owner_membership.user:
        u = owner_membership.user
        owner_name = u.get_full_name() or u.first_name or ""

    return render(
        request,
        "stores/public_detail.html",
        {
            "store": store,
            "categories": categories,
            "latest_products": latest_products,
            "total_products": total_products,
            "owner_name": owner_name,
        },
    )


def public_product_list(request: HttpRequest, slug: str) -> HttpResponse:
    """
    Public customer-facing product catalogue listing and search view.
    Handles search (q), category, availability, sorting, and filter-preserving pagination.
    Only accessible if the Store is PUBLISHED and its Merchant is ACTIVE.
    """
    store = get_public_store_by_slug(slug)
    if not store:
        raise Http404("Store not found or is not currently active.")

    merchant = store.merchant
    all_categories = get_merchant_categories(merchant)

    # 1. Parse and sanitize query parameters
    raw_q = request.GET.get("q", "").strip()[:100]
    search_query = raw_q if raw_q else None

    raw_cat = request.GET.get("category", "").strip().lower()
    category_slug = raw_cat if raw_cat else None

    raw_avail = request.GET.get("availability", "").strip().upper()
    availability_mode = raw_avail if raw_avail in AvailabilityMode.values else None

    raw_sort = request.GET.get("sort", "").strip().lower()
    valid_sorts = {"newest", "price_asc", "price_desc"}
    ordering = raw_sort if raw_sort in valid_sorts else "newest"

    # 2. Selected category resolution
    selected_category = None
    if category_slug:
        selected_category = all_categories.filter(slug=category_slug).first()

    # 3. Retrieve published products via selector
    products_qs = get_public_storefront_products(
        merchant=merchant,
        category_slug=category_slug,
        ordering=ordering,
        search_query=search_query,
        availability_mode=availability_mode,
    )

    # Total published catalogue count (to differentiate empty catalogue vs. no filter results)
    total_published_count = Product.objects.filter(
        merchant=merchant,
        status=ProductStatus.PUBLISHED,
    ).count()

    # 4. Pagination (12 items per page)
    paginator = Paginator(products_qs, 12)
    page_number = request.GET.get("page")
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    # 5. Build base query string preserving filters across pagination links
    query_params = request.GET.copy()
    query_params.pop("page", None)
    base_query_string = query_params.urlencode()

    has_active_filters = bool(
        search_query or category_slug or availability_mode or (ordering != "newest")
    )

    return render(
        request,
        "storefront/product_list.html",
        {
            "store": store,
            "categories": all_categories,
            "page_obj": page_obj,
            "paginator": paginator,
            "total_published_count": total_published_count,
            "search_query": search_query or "",
            "selected_category": selected_category,
            "selected_category_slug": category_slug or "",
            "selected_availability": availability_mode or "",
            "selected_sort": ordering,
            "base_query_string": base_query_string,
            "has_active_filters": has_active_filters,
        },
    )
