from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for custom User model."""

    list_display = (
        "email",
        "first_name",
        "last_name",
        "is_verified",
        "is_active",
        "is_staff",
        "date_joined",
    )
    list_filter = ("is_verified", "is_active", "is_staff", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Personal info"),
            {"fields": ("first_name", "last_name")},
        ),
        (
            _("Permissions & Flags"),
            {
                "fields": (
                    "is_active",
                    "is_verified",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            _("Important dates"),
            {"fields": ("last_login", "date_joined", "updated_at")},
        ),
    )
    readonly_fields = ("date_joined", "updated_at", "last_login")

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password",
                    "first_name",
                    "last_name",
                    "is_verified",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )
