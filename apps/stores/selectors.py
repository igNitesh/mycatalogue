from django.db.models.functions import Lower

from apps.merchants.choices import MerchantStatus

from .choices import StoreStatus
from .models import Store
from .validators import normalize_slug


def get_public_store_by_slug(slug: str) -> Store | None:
    """
    Retrieves an eligible, publicly accessible Store by its URL slug.

    Public visibility requires BOTH:
    1. Store.status == StoreStatus.PUBLISHED
    2. Merchant.status == MerchantStatus.ACTIVE

    Returns the Store instance (with merchant pre-selected) or None.
    """
    normalized_slug = normalize_slug(slug)
    if not normalized_slug:
        return None

    return (
        Store.objects.select_related("merchant")
        .annotate(lower_slug=Lower("slug"))
        .filter(
            lower_slug=normalized_slug,
            status=StoreStatus.PUBLISHED,
            merchant__status=MerchantStatus.ACTIVE,
        )
        .first()
    )
