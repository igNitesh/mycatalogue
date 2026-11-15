"""Core views including health check endpoint."""

from typing import Any

from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views import View

from apps.users.decorators import verified_user_required


class HealthCheckView(View):
    """
    Health check endpoint for container orchestrators, load balancers,
    and monitoring agents.

    Verifies Django application availability and active database connectivity.
    Returns HTTP 200 when healthy, HTTP 503 when degraded or database unavailable.
    """

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        components: dict[str, str] = {}
        is_healthy = True

        # 1. Database connection check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
                if row and row[0] == 1:
                    components["database"] = "healthy"
                else:
                    components["database"] = "unexpected_response"
                    is_healthy = False
        except Exception as exc:
            components["database"] = f"unhealthy: {exc.__class__.__name__}"
            is_healthy = False

        status_code = 200 if is_healthy else 503
        payload = {
            "status": "healthy" if is_healthy else "unhealthy",
            "components": components,
        }
        return JsonResponse(payload, status=status_code)


def index_view(request: HttpRequest):
    """Landing page verifying Tailwind CSS and HTMX foundation."""
    return render(request, "core/index.html")


@verified_user_required
def protected_dashboard_view(request: HttpRequest):
    """Protected storefront area strictly restricted to email-verified users."""
    return render(request, "core/protected.html")
