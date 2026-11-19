from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from apps.products.choices import ProductStatus
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
