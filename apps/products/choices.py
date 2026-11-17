from django.db import models
from django.utils.translation import gettext_lazy as _


class ProductStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    PUBLISHED = "PUBLISHED", _("Published")
    ARCHIVED = "ARCHIVED", _("Archived")


class AvailabilityMode(models.TextChoices):
    IN_STOCK = "IN_STOCK", _("In Stock")
    MADE_TO_ORDER = "MADE_TO_ORDER", _("Made to Order")
    OUT_OF_STOCK = "OUT_OF_STOCK", _("Out of Stock")


class PriceDisplayMode(models.TextChoices):
    SHOW_PRICE = "SHOW_PRICE", _("Show Price")
    CONTACT_FOR_PRICE = "CONTACT_FOR_PRICE", _("Contact for Price")


class Currency(models.TextChoices):
    INR = "INR", _("Indian Rupee (₹)")
    USD = "USD", _("US Dollar ($)")
    EUR = "EUR", _("Euro (€)")
    GBP = "GBP", _("British Pound (£)")
