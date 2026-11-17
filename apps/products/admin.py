from django.contrib import admin

from .models import Category, Product, ProductCategory, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "alt_text", "display_order", "is_primary")


class ProductCategoryInline(admin.TabularInline):
    model = ProductCategory
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "merchant", "slug", "display_order", "is_active", "created_at")
    list_filter = ("is_active", "merchant")
    search_fields = ("name", "slug", "merchant__name")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("merchant", "display_order", "name")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "merchant",
        "slug",
        "sku",
        "price",
        "currency",
        "status",
        "is_available",
        "created_at",
    )
    list_filter = ("status", "is_available", "currency", "merchant")
    search_fields = ("name", "slug", "sku", "merchant__name")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductCategoryInline, ProductImageInline]
    ordering = ("-created_at",)


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("product", "category", "created_at")
    search_fields = ("product__name", "category__name")


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "image", "is_primary", "display_order", "created_at")
    list_filter = ("is_primary",)
    search_fields = ("product__name", "alt_text")
