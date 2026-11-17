from django.db import models
from django.utils.translation import gettext_lazy as _


class ProductStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    PUBLISHED = "PUBLISHED", _("Published")
    ARCHIVED = "ARCHIVED", _("Archived")


class Currency(models.TextChoices):
    INR = "INR", _("Indian Rupee (₹)")
    USD = "USD", _("US Dollar ($)")
    EUR = "EUR", _("Euro (€)")
    GBP = "GBP", _("British Pound (£)")
