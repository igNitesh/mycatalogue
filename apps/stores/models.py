import uuid

from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.merchants.choices import MerchantStatus

from .choices import StoreStatus
from .validators import normalize_slug, validate_store_slug


class Store(models.Model):
    """
    Public digital storefront identity associated with a single Merchant organization.
    Protected from cascading deletion to preserve tenant assets.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.OneToOneField(
        "merchants.Merchant",
        on_delete=models.PROTECT,
        related_name="store",
        verbose_name=_("merchant"),
    )
    name = models.CharField(_("store name"), max_length=255, db_index=True)
    slug = models.SlugField(
        _("store slug"),
        max_length=100,
        validators=[validate_store_slug],
        help_text=_("Public store URL identifier (lowercase letters, numbers, hyphens)."),
    )
    description = models.TextField(_("store description"), blank=True, default="")
    logo = models.ImageField(
        _("logo image"),
        upload_to="stores/logos/%Y/%m/",
        blank=True,
        null=True,
    )
    cover_image = models.ImageField(
        _("cover image"),
        upload_to="stores/covers/%Y/%m/",
        blank=True,
        null=True,
    )
    status = models.CharField(
        _("store status"),
        max_length=20,
        choices=StoreStatus.choices,
        default=StoreStatus.DRAFT,
        db_index=True,
    )

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("store")
        verbose_name_plural = _("stores")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                Lower("slug"),
                name="unique_lowercase_store_slug",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"

    def get_absolute_url(self) -> str:
        return reverse("stores:public_detail", kwargs={"slug": self.slug})

    def clean(self) -> None:
        super().clean()
        if self.slug:
            self.slug = normalize_slug(self.slug)

    @property
    def is_publicly_accessible(self) -> bool:
        """
        Public visibility invariant:
        Store must be PUBLISHED AND the associated Merchant must be in ACTIVE status.
        """
        return (
            self.status == StoreStatus.PUBLISHED and self.merchant.status == MerchantStatus.ACTIVE
        )
