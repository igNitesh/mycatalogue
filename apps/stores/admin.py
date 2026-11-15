from django.contrib import admin

from .models import Store


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "merchant", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("name", "slug", "merchant__name", "merchant__email")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("merchant",)
