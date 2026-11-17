import os
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models.functions import Lower
from django.db.models.signals import m2m_changed, post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from .choices import AvailabilityMode, Currency, PriceDisplayMode, ProductStatus
from .exceptions import CrossTenantAssignmentError
from .validators import (
    validate_and_normalize_slug,
    validate_attributes,
    validate_product_pricing,
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
        _("selling price"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_(
            "Merchant selling price offered to consumers. Mandatory when Show Price is selected on published items."
        ),
    )
    mrp = models.DecimalField(
        _("maximum retail price (MRP)"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Anchor price for discount display. Must be >= price if both set."),
    )
    price_display_mode = models.CharField(
        _("price display mode"),
        max_length=20,
        choices=PriceDisplayMode.choices,
        default=PriceDisplayMode.SHOW_PRICE,
        help_text=_("Governs whether numeric price is shown or replaced by an enquiry prompt."),
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
    availability_mode = models.CharField(
        _("availability mode"),
        max_length=20,
        choices=AvailabilityMode.choices,
        default=AvailabilityMode.IN_STOCK,
        help_text=_("Inventory availability state (In Stock, Made to Order, Out of Stock)."),
    )
    is_available = models.BooleanField(
        _("is available"),
        default=True,
        db_index=True,
        help_text=_("Availability/in-stock indicator. Preserved during migration transition."),
    )
    attributes = models.JSONField(
        _("custom attributes"),
        default=dict,
        blank=True,
        help_text=_("Structured specifications or key-value attributes."),
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
            # CheckConstraints for Pricing
            models.CheckConstraint(
                condition=models.Q(price__gte=0) | models.Q(price__isnull=True),
                name="check_product_price_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(mrp__gte=0) | models.Q(mrp__isnull=True),
                name="chk_prod_mrp_non_neg",
            ),
            models.CheckConstraint(
                condition=models.Q(mrp__isnull=True)
                | models.Q(price__isnull=True)
                | models.Q(mrp__gte=models.F("price")),
                name="chk_prod_mrp_gte_price",
            ),
            models.CheckConstraint(
                condition=models.Q(price_display_mode__in=PriceDisplayMode.values),
                name="chk_prod_price_mode_valid",
            ),
            models.CheckConstraint(
                condition=~models.Q(status=ProductStatus.PUBLISHED)
                | ~models.Q(price_display_mode=PriceDisplayMode.SHOW_PRICE)
                | models.Q(price__isnull=False),
                name="chk_prod_pub_price",
            ),
            # CheckConstraint for Availability Synchronization
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(availability_mode=AvailabilityMode.OUT_OF_STOCK)
                        & models.Q(is_available=False)
                    )
                    | (
                        models.Q(
                            availability_mode__in=[
                                AvailabilityMode.IN_STOCK,
                                AvailabilityMode.MADE_TO_ORDER,
                            ]
                        )
                        & models.Q(is_available=True)
                    )
                ),
                name="chk_prod_avail_mode_sync",
            ),
        ]
        indexes = [
            # Consolidated query-justified index covering catalog queries
            models.Index(
                fields=["merchant", "status", "availability_mode", "created_at"],
                name="idx_prod_mcht_mode_created",
            ),
            # Preserved legacy index for backward compatibility during transition
            models.Index(
                fields=["merchant", "status", "is_available"],
                name="idx_prod_mcht_stat_avail",
            ),
            models.Index(
                fields=["merchant", "-created_at"],
                name="idx_prod_mcht_created",
            ),
        ]

    def __init__(self, *args, **kwargs) -> None:
        self._assigned_fields: set[str] = set()
        super().__init__(*args, **kwargs)
        for field in ("availability_mode", "is_available"):
            if field in kwargs:
                self._assigned_fields.add(field)
        self._initial_availability_mode = self.availability_mode
        self._initial_is_available = self.is_available

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name in ("availability_mode", "is_available") and hasattr(self, "_assigned_fields"):
            self._assigned_fields.add(name)

    def __str__(self) -> str:
        return f"{self.name} ({self.merchant.name})"

    def save(self, *args, **kwargs) -> None:
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            has_mode = "availability_mode" in update_fields
            has_avail = "is_available" in update_fields
            if has_mode and not has_avail:
                self.is_available = self.availability_mode != AvailabilityMode.OUT_OF_STOCK
                update_fields.add("is_available")
            elif has_avail and not has_mode:
                self.availability_mode = (
                    AvailabilityMode.IN_STOCK
                    if self.is_available
                    else AvailabilityMode.OUT_OF_STOCK
                )
                update_fields.add("availability_mode")
            elif has_mode and has_avail:
                expected_avail = self.availability_mode != AvailabilityMode.OUT_OF_STOCK
                if self.is_available != expected_avail:
                    raise ValidationError(
                        _(
                            "Contradictory availability values: availability_mode '%(mode)s' "
                            "conflicts with is_available=%(avail)s."
                        )
                        % {"mode": self.availability_mode, "avail": self.is_available}
                    )
            kwargs["update_fields"] = list(update_fields)
        else:
            # Full instance save
            has_mode = "availability_mode" in getattr(self, "_assigned_fields", set())
            has_avail = "is_available" in getattr(self, "_assigned_fields", set())

            if self._state.adding:
                if has_mode and not has_avail:
                    self.is_available = self.availability_mode != AvailabilityMode.OUT_OF_STOCK
                elif has_avail and not has_mode:
                    self.availability_mode = (
                        AvailabilityMode.IN_STOCK
                        if self.is_available
                        else AvailabilityMode.OUT_OF_STOCK
                    )
                else:
                    expected_avail = self.availability_mode != AvailabilityMode.OUT_OF_STOCK
                    if self.is_available != expected_avail:
                        raise ValidationError(
                            _(
                                "Contradictory availability values on creation: availability_mode '%(mode)s' "
                                "conflicts with is_available=%(avail)s."
                            )
                            % {"mode": self.availability_mode, "avail": self.is_available}
                        )
            else:
                if has_mode and not has_avail:
                    self.is_available = self.availability_mode != AvailabilityMode.OUT_OF_STOCK
                elif has_avail and not has_mode:
                    self.availability_mode = (
                        AvailabilityMode.IN_STOCK
                        if self.is_available
                        else AvailabilityMode.OUT_OF_STOCK
                    )
                elif has_mode and has_avail:
                    expected_avail = self.availability_mode != AvailabilityMode.OUT_OF_STOCK
                    if self.is_available != expected_avail:
                        raise ValidationError(
                            _(
                                "Contradictory availability update: availability_mode '%(mode)s' "
                                "conflicts with is_available=%(avail)s."
                            )
                            % {"mode": self.availability_mode, "avail": self.is_available}
                        )
                else:
                    self.is_available = self.availability_mode != AvailabilityMode.OUT_OF_STOCK

        super().save(*args, **kwargs)
        self._initial_availability_mode = self.availability_mode
        self._initial_is_available = self.is_available
        if hasattr(self, "_assigned_fields"):
            self._assigned_fields.clear()

    def clean(self) -> None:
        super().clean()
        if self.slug:
            self.slug = validate_and_normalize_slug(self.slug, max_length=255)
        if self.sku is not None:
            clean_sku = self.sku.strip()
            self.sku = clean_sku if clean_sku else None
        if self.attributes:
            self.attributes = validate_attributes(self.attributes)
        validate_product_pricing(
            price=self.price,
            mrp=self.mrp,
            price_display_mode=self.price_display_mode,
            status=self.status,
        )

    def refresh_from_db(self, using: Any = None, fields: Any = None) -> None:
        super().refresh_from_db(using=using, fields=fields)
        self._initial_availability_mode = self.availability_mode
        self._initial_is_available = self.is_available
        if hasattr(self, "_assigned_fields"):
            self._assigned_fields.clear()

    @property
    def discount_percentage(self) -> int | None:
        """
        Computes integer discount percentage using standard commercial half-up rounding.
        Returns None if:
          - price_display_mode != SHOW_PRICE
          - price or mrp is missing
          - mrp <= price
          - mrp <= 0
          - calculated discount is less than 1% (avoids misleading '0% OFF' badges)
        """
        if (
            self.price_display_mode == PriceDisplayMode.SHOW_PRICE
            and self.price is not None
            and self.mrp is not None
            and self.mrp > self.price
            and self.mrp > 0
        ):
            raw_discount = ((self.mrp - self.price) / self.mrp) * Decimal("100")
            rounded = int(raw_discount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            return rounded if rounded >= 1 else None
        return None

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
