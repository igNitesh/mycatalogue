from django.urls import path

from . import views

app_name = "products"

urlpatterns = [
    # Catalogue Overview
    path("", views.CatalogueOverviewView.as_view(), name="overview"),
    # Product Management
    path("items/", views.ProductListView.as_view(), name="product_list"),
    path("items/new/", views.ProductCreateView.as_view(), name="product_create"),
    path("items/<uuid:product_id>/edit/", views.ProductEditView.as_view(), name="product_edit"),
    path(
        "items/<uuid:product_id>/publish/",
        views.ProductPublishView.as_view(),
        name="product_publish",
    ),
    path(
        "items/<uuid:product_id>/unpublish/",
        views.ProductUnpublishView.as_view(),
        name="product_unpublish",
    ),
    path(
        "items/<uuid:product_id>/archive/",
        views.ProductArchiveView.as_view(),
        name="product_archive",
    ),
    # Product Image Gallery Management
    path(
        "items/<uuid:product_id>/images/upload/",
        views.ProductImageUploadView.as_view(),
        name="product_image_upload",
    ),
    path(
        "images/<uuid:image_id>/delete/",
        views.ProductImageDeleteView.as_view(),
        name="product_image_delete",
    ),
    path(
        "images/<uuid:image_id>/set-primary/",
        views.ProductImageSetPrimaryView.as_view(),
        name="product_image_set_primary",
    ),
    # Category Management
    path("categories/", views.CategoryListView.as_view(), name="category_list"),
    path("categories/new/", views.CategoryCreateView.as_view(), name="category_create"),
    path(
        "categories/<uuid:category_id>/edit/",
        views.CategoryEditView.as_view(),
        name="category_edit",
    ),
    path(
        "categories/<uuid:category_id>/toggle/",
        views.CategoryToggleActiveView.as_view(),
        name="category_toggle",
    ),
    # Real-time Slug Validation / Collision Checks
    path("slug-check/product/", views.ProductSlugCheckView.as_view(), name="product_slug_check"),
    path("slug-check/category/", views.CategorySlugCheckView.as_view(), name="category_slug_check"),
]
