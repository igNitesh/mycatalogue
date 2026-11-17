import os
import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models.functions import Lower
from django.db.models.signals import m2m_changed, post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from .choices import Currency, ProductStatus
from .exceptions import CrossTenantAssignmentError
from .validators import (
    validate_and_normalize_slug,
    validate_attributes,
)


class Category(models.Model):
    """
    Merchant-owned product category/collection.
    Slugs are unique per merchant.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.CASCADE,
        related_name="categories",
        verbose_name=_("merchant"),
    )
    name = models.CharField(_("category name"), max_length=150, db_index=True)
    slug = models.SlugField(
        _("category slug"),
        max_length=160,
        db_index=True,
        help_text=_("URL identifier for category browsing within the merchant's store."),
    )
    description = models.TextField(_("category description"), blank=True, default="")
    image = models.ImageField(
        _("category image"),
        upload_to="categories/images/%Y/%m/",
        blank=True,
        null=True,
    )
    display_order = models.PositiveIntegerField(
        _("display order"),
        default=0,
        db_index=True,
    )
    is_active = models.BooleanField(
        _("is active"),
        default=True,
        db_index=True,
    )

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ["display_order", "name"]
        constraints = [
            models.UniqueConstraint(
                "merchant",
                Lower("slug"),
                name="unique_merchant_category_slug",
            ),
        ]
        indexes = [
            models.Index(
                fields=["merchant", "is_active", "display_order"],
                name="idx_cat_mcht_active_order",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.merchant.name})"

    def clean(self) -> None:
        super().clean()
        if self.slug:
            self.slug = validate_and_normalize_slug(self.slug, max_length=160)


class Product(models.Model):
    """
    Sellable or showcase item in a merchant's digital catalogue.
    Slugs and SKUs are unique per merchant.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name=_("merchant"),
    )
    name = models.CharField(_("product name"), max_length=255, db_index=True)
    slug = models.SlugField(
        _("product slug"),
        max_length=255,
        db_index=True,
        help_text=_("URL identifier for the product within the merchant's store."),
    )
    sku = models.CharField(  # noqa: DJ001
        _("SKU"),
        max_length=100,
        blank=True,
        null=True,
        help_text=_("Optional Stock Keeping Unit. Must be unique per merchant when set."),
    )
    description = models.TextField(_("product description"), blank=True, default="")
    price = models.DecimalField(
        _("price"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Product price. Leave empty for 'Price on Request' / inquiry."),
    )
    currency = models.CharField(
        _("currency"),
        max_length=3,
        choices=Currency.choices,
        default=Currency.INR,
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.DRAFT,
        db_index=True,
    )
    is_available = models.BooleanField(
        _("is available"),
        default=True,
        db_index=True,
        help_text=_("Availability/in-stock indicator. Does not affect publication status."),
    )
    attributes = models.JSONField(
        _("custom attributes"),
        default=dict,
        blank=True,
        help_text=_("Structured key-value attributes (e.g. Fabric, Size, Color)."),
    )
    categories = models.ManyToManyField(
        Category,
        through="ProductCategory",
        related_name="products",
        blank=True,
    )

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                "merchant",
                Lower("slug"),
                name="unique_merchant_product_slug",
            ),
            models.UniqueConstraint(
                fields=["merchant", "sku"],
                condition=models.Q(sku__isnull=False) & ~models.Q(sku=""),
                name="unique_merchant_product_sku",
            ),
            models.CheckConstraint(
                condition=models.Q(price__gte=0) | models.Q(price__isnull=True),
                name="check_product_price_non_negative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["merchant", "status", "is_available"],
                name="idx_prod_mcht_stat_avail",
            ),
            models.Index(
                fields=["merchant", "-created_at"],
                name="idx_prod_mcht_created",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.merchant.name})"

    def clean(self) -> None:
        super().clean()
        if self.slug:
            self.slug = validate_and_normalize_slug(self.slug, max_length=255)
        if self.sku is not None:
            clean_sku = self.sku.strip()
            self.sku = clean_sku if clean_sku else None
        if self.attributes:
            self.attributes = validate_attributes(self.attributes)

    @property
    def primary_image(self) -> models.Model | None:
        """Returns the designated primary gallery image, if any."""
        return self.images.filter(is_primary=True).first()


class ProductCategory(models.Model):
    """
    Explicit through-model connecting Products to Categories.
    Strictly enforces that Product and Category belong to the exact same Merchant.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="product_categories",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="product_categories",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("product category assignment")
        verbose_name_plural = _("product category assignments")
        constraints = [
            models.UniqueConstraint(
                fields=["product", "category"],
                name="unique_product_category_assignment",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} -> {self.category.name}"

    def save(self, *args, **kwargs) -> None:
        # Enforce cross-tenant validation at database write boundary
        if self.product.merchant_id != self.category.merchant_id:
            raise CrossTenantAssignmentError(
                _("Cannot associate product and category belonging to different merchants.")
            )
        super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if self.product_id and self.category_id:
            if self.product.merchant_id != self.category.merchant_id:
                raise CrossTenantAssignmentError(
                    _("Cannot associate product and category belonging to different merchants.")
                )


class ProductImage(models.Model):
    """
    Media gallery image belonging to a Product.
    Enforces at most one primary thumbnail per product at the database level.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("product"),
    )
    image = models.ImageField(
        _("product image"),
        upload_to="products/images/%Y/%m/",
    )
    alt_text = models.CharField(
        _("alternative text"),
        max_length=255,
        blank=True,
        default="",
    )
    display_order = models.PositiveIntegerField(
        _("display order"),
        default=0,
        db_index=True,
    )
    is_primary = models.BooleanField(
        _("is primary image"),
        default=False,
        db_index=True,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("product image")
        verbose_name_plural = _("product images")
        ordering = ["display_order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_primary=True),
                name="unique_primary_product_image",
            ),
        ]
        indexes = [
            models.Index(
                fields=["product", "display_order"],
                name="idx_prod_img_order",
            ),
        ]

    def __str__(self) -> str:
        return f"Image for {self.product.name} (order: {self.display_order}, primary: {self.is_primary})"


@receiver(m2m_changed, sender=ProductCategory)
def prevent_cross_tenant_m2m_assignment(sender, instance, action, reverse, pk_set, **kwargs):
    """
    Enforces strict tenant isolation when M2M relationship methods (.add, .set) are invoked.
    """
    if action in ("pre_add", "pre_set") and pk_set:
        if reverse:
            # instance is a Category, pk_set contains Product IDs
            if (
                Product.objects.filter(id__in=pk_set)
                .exclude(merchant_id=instance.merchant_id)
                .exists()
            ):
                raise CrossTenantAssignmentError(
                    _("Cannot associate product and category belonging to different merchants.")
                )
        else:
            # instance is a Product, pk_set contains Category IDs
            if (
                Category.objects.filter(id__in=pk_set)
                .exclude(merchant_id=instance.merchant_id)
                .exists()
            ):
                raise CrossTenantAssignmentError(
                    _("Cannot associate product and category belonging to different merchants.")
                )


def _safe_cleanup_file(file_path: str) -> None:
    try:
        if file_path and os.path.isfile(file_path):
            os.remove(file_path)
    except Exception:
        pass


@receiver(post_delete, sender=ProductImage)
def cleanup_product_image_file(sender, instance, **kwargs):
    """Safely cleans up underlying image file on storage after deletion commits."""
    if instance.image:
        try:
            file_path = instance.image.path
            transaction.on_commit(lambda: _safe_cleanup_file(file_path))
        except Exception:
            pass


@receiver(post_delete, sender=Category)
def cleanup_category_image_file(sender, instance, **kwargs):
    """Safely cleans up underlying category image file on storage after deletion commits."""
    if instance.image:
        try:
            file_path = instance.image.path
            transaction.on_commit(lambda: _safe_cleanup_file(file_path))
        except Exception:
            pass
