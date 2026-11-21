from django.urls import path

from . import views, views_management

app_name = "stores"

urlpatterns = [
    # Management endpoints (under /s/settings/ alias)
    path("settings/", views_management.StoreSettingsView.as_view(), name="settings"),
    path("settings/slug/", views_management.StoreSlugUpdateView.as_view(), name="change_slug"),
    path("settings/slug/check/", views_management.StoreSlugCheckView.as_view(), name="check_slug"),
    path(
        "settings/publish/",
        views_management.StorePublishToggleView.as_view(),
        name="toggle_publish",
    ),
    # Public customer-facing storefront catalogue & homepage
    path("<slug:slug>/products/", views.public_product_list, name="public_products"),
    path("<slug:slug>/", views.public_store_detail, name="public_detail"),
]
