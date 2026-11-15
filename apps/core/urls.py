from django.urls import path

from .views import HealthCheckView, index_view, protected_dashboard_view

app_name = "core"

urlpatterns = [
    path("", index_view, name="index"),
    path("health/", HealthCheckView.as_view(), name="health_check"),
    path("protected/", protected_dashboard_view, name="protected"),
]
