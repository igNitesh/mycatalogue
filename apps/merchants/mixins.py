from typing import Any

from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import HttpRequest, HttpResponse

from .exceptions import NoActiveMerchantError
from .permissions import MerchantPermission, can_perform_merchant_action


class MerchantContextMixin:
    """
    Class-based view mixin that provides merchant and membership context
    to the view instance and template context.
    """

    merchant: Any = None
    membership: Any = None

    def setup(self, request: HttpRequest, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        self.merchant = getattr(request, "merchant", None)
        self.membership = getattr(request, "membership", None)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        if hasattr(super(), "get_context_data"):
            context = super().get_context_data(**kwargs)
        else:
            context = kwargs
        context["active_merchant"] = self.merchant
        context["active_membership"] = self.membership
        return context


class MerchantPermissionRequiredMixin(MerchantContextMixin):
    """
    Class-based view mixin enforcing a specific MerchantPermission.
    Uses can_perform_merchant_action as the single source of truth.
    """

    required_permission: MerchantPermission | None = None

    def get_required_permission(self) -> MerchantPermission:
        if self.required_permission is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} is missing a required_permission attribute. "
                "Define required_permission or override get_required_permission()."
            )
        return self.required_permission

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not self.merchant or not self.membership:
            raise NoActiveMerchantError(
                "An active merchant organization context is required to access this view."
            )

        permission = self.get_required_permission()
        if not can_perform_merchant_action(self.membership, permission):
            raise PermissionDenied(
                f"Permission '{permission}' denied for role '{self.membership.role}'."
            )

        return super().dispatch(request, *args, **kwargs)
