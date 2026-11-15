from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .context import resolve_merchant_context


class MerchantContextMiddleware:
    """
    Middleware that establishes the active merchant organization and membership
    context on the incoming request.

    Must run after AuthenticationMiddleware and SessionMiddleware.
    Attaches:
    - request.merchant: Merchant | None
    - request.membership: MerchantMembership | None
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        merchant, membership = resolve_merchant_context(request)
        request.merchant = merchant
        request.membership = membership

        return self.get_response(request)
