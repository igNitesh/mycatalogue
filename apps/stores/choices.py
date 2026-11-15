from django.db import models
from django.utils.translation import gettext_lazy as _


class StoreStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    PUBLISHED = "PUBLISHED", _("Published")
    UNPUBLISHED = "UNPUBLISHED", _("Unpublished")
    SUSPENDED = "SUSPENDED", _("Suspended")
