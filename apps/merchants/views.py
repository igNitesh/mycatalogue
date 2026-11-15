from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views import View

from .context import set_active_merchant
from .exceptions import InvalidMerchantSelectionError


class SwitchMerchantView(LoginRequiredMixin, View):
    """
    POST-only, CSRF-protected endpoint for switching the user's active merchant organization.

    Security & Invariants:
    - Rejects GET with 405 Method Not Allowed.
    - Requires authenticated user.
    - Validates target merchant membership server-side.
    - Modifies session state ONLY upon successful verification.
    - On failure, preserves the previous session selection intact.
    """

    http_method_names = ["post"]

    def post(self, request: HttpRequest) -> HttpResponse:
        target_merchant_id = request.POST.get("merchant_id", "").strip()
        redirect_to = request.POST.get("next") or request.GET.get("next") or "core:index"

        # Security check: ensure redirect URL is safe to prevent open redirect vulnerabilities
        if not url_has_allowed_host_and_scheme(
            url=redirect_to,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            redirect_to = "core:index"

        if not target_merchant_id:
            messages.error(request, _("Please select a valid merchant organization."))
            return redirect(redirect_to)

        try:
            membership = set_active_merchant(request, target_merchant_id)
            messages.success(
                request,
                _("Switched active organization to %(name)s.") % {"name": membership.merchant.name},
            )
        except InvalidMerchantSelectionError:
            messages.error(
                request,
                _("You do not have active access to the selected merchant organization."),
            )

        return redirect(redirect_to)
