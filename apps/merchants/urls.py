from django.urls import path

from apps.stores import views_management as store_views

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
    # Store settings & workspace routes
    path("store/", store_views.StoreSettingsView.as_view(), name="store_settings"),
    path("store/slug/", store_views.StoreSlugUpdateView.as_view(), name="store_change_slug"),
    path("store/slug/check/", store_views.StoreSlugCheckView.as_view(), name="store_check_slug"),
    path(
        "store/publish/", store_views.StorePublishToggleView.as_view(), name="store_publish_toggle"
    ),
]
