from django.db import models
from django.utils.translation import gettext_lazy as _

from .choices import MembershipRole, MembershipStatus, MerchantStatus
from .models import MerchantMembership


class MerchantPermission(models.TextChoices):
    TRANSFER_OWNERSHIP = "TRANSFER_OWNERSHIP", _("Transfer merchant ownership")
    DEACTIVATE_MERCHANT = "DEACTIVATE_MERCHANT", _("Deactivate merchant account")
    MANAGE_BILLING = "MANAGE_BILLING", _("Manage billing and payment details")
    MANAGE_ADMINS = "MANAGE_ADMINS", _("Add, edit, or remove admins")
    MANAGE_MANAGERS = "MANAGE_MANAGERS", _("Add, edit, or remove managers")
    MANAGE_STAFF = "MANAGE_STAFF", _("Add, edit, or remove staff")
    UPDATE_SETTINGS = "UPDATE_SETTINGS", _("Update merchant settings and profile")
    VIEW_FULL_FINANCIALS = (
        "VIEW_FULL_FINANCIALS",
        _("View full financial and tax reports"),
    )
    VIEW_OPERATIONAL_SALES = (
        "VIEW_OPERATIONAL_SALES",
        _("View operational shift sales summaries"),
    )
    OPERATE_STOREFRONT = (
        "OPERATE_STOREFRONT",
        _("Execute operational storefront tasks"),
    )


ROLE_PERMISSIONS: dict[str, set[MerchantPermission]] = {
    MembershipRole.OWNER: {
        MerchantPermission.TRANSFER_OWNERSHIP,
        MerchantPermission.DEACTIVATE_MERCHANT,
        MerchantPermission.MANAGE_BILLING,
        MerchantPermission.MANAGE_ADMINS,
        MerchantPermission.MANAGE_MANAGERS,
        MerchantPermission.MANAGE_STAFF,
        MerchantPermission.UPDATE_SETTINGS,
        MerchantPermission.VIEW_FULL_FINANCIALS,
        MerchantPermission.VIEW_OPERATIONAL_SALES,
        MerchantPermission.OPERATE_STOREFRONT,
    },
    MembershipRole.ADMIN: {
        MerchantPermission.MANAGE_MANAGERS,
        MerchantPermission.MANAGE_STAFF,
        MerchantPermission.UPDATE_SETTINGS,
        MerchantPermission.VIEW_FULL_FINANCIALS,
        MerchantPermission.VIEW_OPERATIONAL_SALES,
        MerchantPermission.OPERATE_STOREFRONT,
    },
    MembershipRole.MANAGER: {
        MerchantPermission.MANAGE_STAFF,
        MerchantPermission.VIEW_OPERATIONAL_SALES,  # Limited to shift totals
        MerchantPermission.OPERATE_STOREFRONT,
    },
    MembershipRole.STAFF: {
        MerchantPermission.OPERATE_STOREFRONT,
    },
}

# Permissions accessible to OWNER when merchant is SUSPENDED (for resolution)
SUSPENDED_ALLOWED_OWNER_PERMISSIONS = {
    MerchantPermission.MANAGE_BILLING,
    MerchantPermission.TRANSFER_OWNERSHIP,
    MerchantPermission.UPDATE_SETTINGS,
    MerchantPermission.VIEW_FULL_FINANCIALS,
}

# Permissions accessible to OWNER when merchant is INACTIVE (for accounting/tax history)
INACTIVE_ALLOWED_OWNER_PERMISSIONS = {
    MerchantPermission.VIEW_FULL_FINANCIALS,
}

# Permissions allowed when merchant is PENDING (for onboarding setup)
PENDING_ALLOWED_PERMISSIONS = {
    MerchantPermission.UPDATE_SETTINGS,
    MerchantPermission.MANAGE_ADMINS,
    MerchantPermission.MANAGE_MANAGERS,
    MerchantPermission.MANAGE_STAFF,
    MerchantPermission.TRANSFER_OWNERSHIP,
}


def has_role_permission(role: str, permission: MerchantPermission) -> bool:
    """Check if a given membership role has the capability grant."""
    role_grants = ROLE_PERMISSIONS.get(role, set())
    return permission in role_grants


def can_perform_merchant_action(
    membership: MerchantMembership, permission: MerchantPermission
) -> bool:
    """
    Decoupled evaluation of member permission against merchant operational status:
    1. Member role must grant the permission.
    2. Member status must be strictly ACTIVE.
    3. Merchant lifecycle rules:
       - ACTIVE: All granted permissions allowed.
       - SUSPENDED: Only billing/settings allowed for OWNER to resolve suspension.
       - INACTIVE: Only historical viewing allowed for OWNER.
       - PENDING: Only setup/onboarding allowed; operational storefront blocked.
    """
    # 1. Membership status check
    if membership.status != MembershipStatus.ACTIVE:
        return False

    # 2. Role permission grant check
    if not has_role_permission(membership.role, permission):
        return False

    merchant_status = membership.merchant.status

    # 3. Merchant lifecycle gate
    if merchant_status == MerchantStatus.ACTIVE:
        return True

    if merchant_status == MerchantStatus.SUSPENDED:
        return (
            membership.role == MembershipRole.OWNER
            and permission in SUSPENDED_ALLOWED_OWNER_PERMISSIONS
        )

    if merchant_status == MerchantStatus.INACTIVE:
        return (
            membership.role == MembershipRole.OWNER
            and permission in INACTIVE_ALLOWED_OWNER_PERMISSIONS
        )

    if merchant_status == MerchantStatus.PENDING:
        return permission in PENDING_ALLOWED_PERMISSIONS

    return False
