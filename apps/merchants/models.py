import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from .choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus


class Merchant(models.Model):
    """
    Primary merchant/tenant entity representing a storefront organization.
    Defaults to PENDING status upon creation.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("business name"), max_length=255, db_index=True)
    business_type = models.CharField(
        _("business type"),
        max_length=50,
        choices=BusinessType.choices,
        default=BusinessType.RETAIL,
    )
    description = models.TextField(_("business description"), blank=True)
    contact_number = models.CharField(_("contact number"), max_length=20)
    email = models.EmailField(_("business email"), db_index=True)
    address = models.TextField(_("street address"))
    city = models.CharField(_("city"), max_length=100)
    state = models.CharField(_("state"), max_length=100)
    pin_code = models.CharField(_("PIN code"), max_length=20)
    status = models.CharField(
        _("account status"),
        max_length=20,
        choices=MerchantStatus.choices,
        default=MerchantStatus.PENDING,
        db_index=True,
    )

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("merchant")
        verbose_name_plural = _("merchants")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    def is_operational(self) -> bool:
        """Determines if the merchant organization is in active operational standing."""
        return self.status == MerchantStatus.ACTIVE

    def has_active_owner(self) -> bool:
        """Checks if the merchant currently has at least one active owner membership."""
        return self.memberships.filter(
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        ).exists()


class MerchantMembership(models.Model):
    """
    Many-to-Many through-model linking Users to Merchants with granular roles
    and independent status tracking.
    User deletion is PROTECTED to prevent silent cascading loss of merchant ownership.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="merchant_memberships",
    )
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        _("role"),
        max_length=20,
        choices=MembershipRole.choices,
        default=MembershipRole.STAFF,
    )
    status = models.CharField(
        _("membership status"),
        max_length=20,
        choices=MembershipStatus.choices,
        default=MembershipStatus.ACTIVE,
    )

    joined_at = models.DateTimeField(_("joined at"), auto_now_add=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("merchant membership")
        verbose_name_plural = _("merchant memberships")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "merchant"],
                name="unique_user_merchant_membership",
            )
        ]
        indexes = [
            # High-frequency tenant access control: (merchant_id, role, status)
            models.Index(
                fields=["merchant", "role", "status"],
                name="idx_mship_mcht_role_stat",
            ),
            # User storefront listing query: (user_id, status)
            models.Index(
                fields=["user", "status"],
                name="idx_mship_user_stat",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} - {self.merchant.name} ({self.role})"

    # Convenience helper methods (authoritative checks live in permissions.py)
    def can_perform_operations(self) -> bool:
        """Convenience helper checking operational eligibility."""
        return self.status == MembershipStatus.ACTIVE and self.merchant.is_operational()

    def is_owner(self) -> bool:
        return self.role == MembershipRole.OWNER and self.status == MembershipStatus.ACTIVE

    def is_admin_or_higher(self) -> bool:
        return (
            self.role in (MembershipRole.OWNER, MembershipRole.ADMIN)
            and self.status == MembershipStatus.ACTIVE
        )

    def is_manager_or_higher(self) -> bool:
        return (
            self.role
            in (
                MembershipRole.OWNER,
                MembershipRole.ADMIN,
                MembershipRole.MANAGER,
            )
            and self.status == MembershipStatus.ACTIVE
        )


class MerchantOwnershipTransferLog(models.Model):
    """
    Immutable audit log recording every ownership transfer event.
    ForeignKeys use PROTECT to ensure audit history is preserved indefinitely.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.PROTECT,
        related_name="ownership_transfers",
    )
    previous_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transferred_away_merchants",
    )
    new_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="acquired_merchants",
    )
    transferred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="initiated_ownership_transfers",
    )
    transferred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("ownership transfer log")
        verbose_name_plural = _("ownership transfer logs")
        ordering = ["-transferred_at"]

    def __str__(self) -> str:
        return f"{self.merchant.name}: {self.previous_owner.email} -> {self.new_owner.email} at {self.transferred_at}"
