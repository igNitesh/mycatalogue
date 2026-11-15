from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from .selectors import get_public_store_by_slug


def public_store_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """
    Public storefront landing view.
    Only accessible if the Store is PUBLISHED and its Merchant is ACTIVE.
    """
    store = get_public_store_by_slug(slug)
    if not store:
        raise Http404("Store not found or is not currently active.")

    return render(
        request,
        "stores/public_detail.html",
        {
            "store": store,
        },
    )
