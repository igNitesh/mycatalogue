from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, resolve_url

from .exceptions import NoActiveMerchantError
from .permissions import MerchantPermission, can_perform_merchant_action


def merchant_required(
    view_func: Callable | None = None,
    *,
    redirect_url: str | None = None,
    raise_exception: bool = False,
) -> Callable:
    """
    Decorator for views that require an authenticated user with an established,
    valid active merchant organization context.

    Note: Does NOT require Merchant.status == ACTIVE. Allows access to onboarding
    or suspended/billing views as long as a valid merchant context is established.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            # 1. User must be authenticated and active
            if not request.user.is_authenticated or not request.user.is_active:
                login_url = resolve_url(getattr(settings, "LOGIN_URL", "users:login"))
                return redirect(f"{login_url}?next={request.path}")

            # 2. Must have an active merchant context
            merchant = getattr(request, "merchant", None)
            membership = getattr(request, "membership", None)

            if not merchant or not membership:
                if raise_exception:
                    raise NoActiveMerchantError(
                        "An active merchant organization context is required to access this resource."
                    )
                target_url = redirect_url or getattr(
                    settings, "MERCHANT_SELECTION_URL", "core:index"
                )
                return redirect(target_url)

            return func(request, *args, **kwargs)

        return _wrapped_view

    if view_func is not None:
        return decorator(view_func)
    return decorator


def merchant_permission_required(
    permission: MerchantPermission,
    *,
    redirect_url: str | None = None,
    raise_exception: bool = True,
) -> Callable:
    """
    Decorator for views that require a specific MerchantPermission.

    Single Source of Truth:
    Evaluates can_perform_merchant_action(request.membership, permission), which
    strictly enforces role capability, membership status, and merchant lifecycle state.
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            # 1. Enforce merchant context first
            if not request.user.is_authenticated or not request.user.is_active:
                login_url = resolve_url(getattr(settings, "LOGIN_URL", "users:login"))
                return redirect(f"{login_url}?next={request.path}")

            merchant = getattr(request, "merchant", None)
            membership = getattr(request, "membership", None)

            if not merchant or not membership:
                if raise_exception:
                    raise NoActiveMerchantError(
                        "An active merchant organization context is required."
                    )
                target_url = redirect_url or getattr(
                    settings, "MERCHANT_SELECTION_URL", "core:index"
                )
                return redirect(target_url)

            # 2. Evaluate permission via authoritative engine
            if not can_perform_merchant_action(membership, permission):
                if raise_exception:
                    raise PermissionDenied(
                        f"Permission '{permission}' denied for membership role '{membership.role}' "
                        f"under merchant status '{merchant.status}'."
                    )
                target_url = redirect_url or getattr(
                    settings, "MERCHANT_SELECTION_URL", "core:index"
                )
                return redirect(target_url)

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
