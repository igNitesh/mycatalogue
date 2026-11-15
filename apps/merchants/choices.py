from django.db import models
from django.utils.translation import gettext_lazy as _


class MerchantStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending Verification")
    ACTIVE = "ACTIVE", _("Active")
    SUSPENDED = "SUSPENDED", _("Suspended")
    INACTIVE = "INACTIVE", _("Inactive")


class BusinessType(models.TextChoices):
    RETAIL = "RETAIL", _("Retail & E-commerce")
    WHOLESALE = "WHOLESALE", _("Wholesale & Distribution")
    RESTAURANT = "RESTAURANT", _("Restaurant & Food Service")
    GROCERY = "GROCERY", _("Grocery & Supermarket")
    SERVICES = "SERVICES", _("Professional & Consumer Services")
    OTHER = "OTHER", _("Other")


class MembershipRole(models.TextChoices):
    OWNER = "OWNER", _("Owner")
    ADMIN = "ADMIN", _("Admin")
    MANAGER = "MANAGER", _("Manager")
    STAFF = "STAFF", _("Staff")


class MembershipStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("Active")
    SUSPENDED = "SUSPENDED", _("Suspended")
    REVOKED = "REVOKED", _("Revoked")
