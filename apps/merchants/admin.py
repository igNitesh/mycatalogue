from typing import Any

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest

from .exceptions import SoleOwnerProtectionError
from .models import Merchant, MerchantMembership, MerchantOwnershipTransferLog
from .services import delete_membership


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "business_type",
        "email",
        "city",
        "status",
        "created_at",
    )
    list_filter = ("status", "business_type")
    search_fields = ("name", "email", "city", "pin_code")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(MerchantMembership)
class MerchantMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "merchant", "role", "status", "joined_at")
    list_filter = ("role", "status", "merchant")
    search_fields = ("user__email", "merchant__name")
    readonly_fields = ("id", "joined_at", "created_at", "updated_at")

    # Disable unsafe bulk actions to prevent bypassing sole-owner checks
    actions = None

    def delete_model(self, request: HttpRequest, obj: Any) -> None:
        """Route single deletion through protected service."""
        try:
            delete_membership(merchant_id=obj.merchant_id, target_user=obj.user)
        except SoleOwnerProtectionError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            raise ValidationError(str(exc)) from exc

    def delete_queryset(self, request: HttpRequest, queryset: Any) -> None:
        """Route queryset deletion through protected service sequentially."""
        for membership in queryset:
            try:
                delete_membership(
                    merchant_id=membership.merchant_id,
                    target_user=membership.user,
                )
            except SoleOwnerProtectionError as exc:
                self.message_user(request, str(exc), level=messages.ERROR)
                return


@admin.register(MerchantOwnershipTransferLog)
class MerchantOwnershipTransferLogAdmin(admin.ModelAdmin):
    list_display = (
        "merchant",
        "previous_owner",
        "new_owner",
        "transferred_by",
        "transferred_at",
    )
    search_fields = (
        "merchant__name",
        "previous_owner__email",
        "new_owner__email",
        "transferred_by__email",
    )
    readonly_fields = (
        "id",
        "merchant",
        "previous_owner",
        "new_owner",
        "transferred_by",
        "transferred_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
