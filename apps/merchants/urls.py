from django.urls import path

from . import views

app_name = "merchants"

urlpatterns = [
    path("dashboard/", views.MerchantDashboardView.as_view(), name="dashboard"),
    path("switch/", views.SwitchMerchantView.as_view(), name="switch"),
    path("onboarding/", views.MerchantOnboardingView.as_view(), name="onboarding"),
    path(
        "onboarding/success/<uuid:merchant_id>/",
        views.MerchantOnboardingSuccessView.as_view(),
        name="onboarding_success",
    ),
]
