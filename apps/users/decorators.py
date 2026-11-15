from collections.abc import Callable
from functools import wraps
from typing import Any

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


def verified_user_required(
    view_func: Callable[..., HttpResponse] | None = None,
    login_url: str | None = None,
    redirect_field_name: str = "next",
    raise_exception: bool = False,
) -> Callable[..., Any]:
    """
    Decorator for views that checks that the user is logged in and has verified
    their email address, redirecting to the verification required page if unverified.

    Supports both:
    @verified_user_required
    def my_view(request): ...

    and:
    @verified_user_required(raise_exception=True)
    def my_view(request): ...
    """

    def decorator(func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @wraps(func)
        def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), login_url, redirect_field_name)

            if not getattr(request.user, "is_verified", False):
                if raise_exception:
                    raise PermissionDenied(
                        "You must verify your email address before accessing this feature."
                    )
                return redirect("users:verification_required")

            return func(request, *args, **kwargs)

        return _wrapped_view

    if view_func is not None:
        return decorator(view_func)
    return decorator


class VerifiedUserRequiredMixin:
    """CBV mixin that verifies both authentication and email verification."""

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not getattr(request.user, "is_verified", False):
            return redirect("users:verification_required")
        return super().dispatch(request, *args, **kwargs)  # type: ignore
