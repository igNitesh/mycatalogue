import uuid
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import QuerySet
from django.http import HttpRequest

from .choices import MembershipStatus
from .exceptions import InvalidMerchantSelectionError
from .models import Merchant, MerchantMembership

ACTIVE_MERCHANT_SESSION_KEY = "active_merchant_id"


def resolve_merchant_context(
    request: HttpRequest,
) -> tuple[Merchant | None, MerchantMembership | None]:
    """
    Resolves the active merchant organization and membership for the current request.

    Resolution Rules:
    1. Unauthenticated or inactive users: returns (None, None).
    2. Session selection present:
       - Validated server-side against the user's ACTIVE memberships.
       - If valid: returns (merchant, membership).
       - If stale/invalid: immediately purges session key and falls through.
    3. No valid session selection:
       - 0 active memberships: returns (None, None).
       - 1 active membership: automatically selects it and records in session.
       - > 1 active memberships: leaves context as (None, None) and requires explicit selection.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_active:
        return None, None

    session = getattr(request, "session", None)
    if session is None:
        return None, None

    session_merchant_id = session.get(ACTIVE_MERCHANT_SESSION_KEY)

    # 1. Attempt to resolve from session
    if session_merchant_id:
        try:
            membership = (
                MerchantMembership.objects.select_related("merchant")
                .filter(
                    user=user,
                    merchant_id=session_merchant_id,
                    status=MembershipStatus.ACTIVE,
                )
                .first()
            )
        except (ValueError, ValidationError):
            membership = None

        if membership:
            return membership.merchant, membership

        # Stale or tampered session key: purge immediately
        del session[ACTIVE_MERCHANT_SESSION_KEY]
        session.modified = True

    # 2. No valid session selection: count active memberships
    active_memberships = MerchantMembership.objects.select_related("merchant").filter(
        user=user,
        status=MembershipStatus.ACTIVE,
    )
    membership_count = active_memberships.count()

    if membership_count == 1:
        single_membership = active_memberships.first()
        str_id = str(single_membership.merchant.id)
        if session.get(ACTIVE_MERCHANT_SESSION_KEY) != str_id:
            session[ACTIVE_MERCHANT_SESSION_KEY] = str_id
            session.modified = True
        return single_membership.merchant, single_membership

    # 0 or > 1 memberships without valid session selection: context remains None
    return None, None


def set_active_merchant(
    request: HttpRequest,
    merchant_id: uuid.UUID | str,
) -> MerchantMembership:
    """
    Switches or sets the active merchant context in the user's session.

    Requirements:
    - User must be authenticated and active.
    - Validates membership server-side.
    - State changes only on success; on failure, existing session remains untouched.
    - Avoids unnecessary session writes when selection is unchanged.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_active:
        raise PermissionDenied("Authentication required to set active merchant.")

    session = getattr(request, "session", None)
    if session is None:
        raise PermissionDenied("Active session required to set active merchant.")

    try:
        membership = (
            MerchantMembership.objects.select_related("merchant")
            .filter(
                user=user,
                merchant_id=merchant_id,
                status=MembershipStatus.ACTIVE,
            )
            .first()
        )
    except (ValueError, ValidationError) as exc:
        raise InvalidMerchantSelectionError(
            f"Invalid merchant identifier: '{merchant_id}'."
        ) from exc

    if not membership:
        raise InvalidMerchantSelectionError(
            f"User does not have an active membership in merchant '{merchant_id}'."
        )

    str_merchant_id = str(membership.merchant.id)
    if session.get(ACTIVE_MERCHANT_SESSION_KEY) != str_merchant_id:
        session[ACTIVE_MERCHANT_SESSION_KEY] = str_merchant_id
        session.modified = True

    request.merchant = membership.merchant
    request.membership = membership

    return membership


def clear_active_merchant(request: HttpRequest) -> None:
    """Clears the active merchant selection from session and request."""
    session = getattr(request, "session", None)
    if session and ACTIVE_MERCHANT_SESSION_KEY in session:
        del session[ACTIVE_MERCHANT_SESSION_KEY]
        session.modified = True

    request.merchant = None
    request.membership = None


def get_user_merchant_memberships(user: Any) -> QuerySet[MerchantMembership]:
    """
    Selector returning all active memberships for a user.
    Loaded only when explicitly requested (e.g. by switcher UI).
    """
    if not user or not user.is_authenticated or not user.is_active:
        return MerchantMembership.objects.none()

    return (
        MerchantMembership.objects.select_related("merchant")
        .filter(user=user, status=MembershipStatus.ACTIVE)
        .order_by("merchant__name")
    )
