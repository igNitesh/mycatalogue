from typing import Any

from django.db.models import QuerySet

from .models import Merchant, MerchantMembership


def get_merchant_member(
    *,
    merchant: Merchant,
    user_id: Any,
) -> MerchantMembership | None:
    """
    Scopes membership retrieval strictly to the validated merchant organization.
    Returns None if the user is not a member of the specified merchant, preventing IDOR.
    """
    resolved_user_id = getattr(user_id, "id", user_id)
    return (
        MerchantMembership.objects.filter(
            merchant=merchant,
            user_id=resolved_user_id,
        )
        .select_related("user")
        .first()
    )


def get_merchant_members(
    *,
    merchant: Merchant,
) -> QuerySet[MerchantMembership]:
    """
    Retrieves all members belonging strictly to the specified merchant organization.
    """
    return merchant.memberships.select_related("user").order_by("user__email")
