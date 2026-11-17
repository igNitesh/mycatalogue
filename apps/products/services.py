import uuid
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from apps.merchants.models import Merchant
from apps.merchants.permissions import (
    MerchantPermission,
    has_merchant_permission,
)

from .choices import AvailabilityMode, Currency, PriceDisplayMode, ProductStatus
from .exceptions import (
    CategoryNotFoundError,
    CategorySlugAlreadyTakenError,
    CrossTenantAssignmentError,
    DuplicateSKUError,
    InvalidProductImageError,
    ProductLifecycleError,
    ProductNotFoundError,
    ProductPermissionDeniedError,
    ProductSlugAlreadyTakenError,
)
from .models import Category, Product, ProductCategory, ProductImage
from .validators import (
    validate_and_normalize_slug,
    validate_attributes,
    validate_product_image,
    validate_product_pricing,
)

_UNSET = object()


def _resolve_merchant(merchant_id: uuid.UUID | str | Merchant) -> Merchant:
    if isinstance(merchant_id, Merchant):
        return merchant_id
    try:
        return Merchant.objects.get(id=merchant_id)
    except (Merchant.DoesNotExist, ValueError) as exc:
        raise ValidationError(f"Merchant with ID '{merchant_id}' does not exist.") from exc


def _check_permission(actor: Any, merchant: Merchant) -> None:
    if actor is None:
        raise TypeError("actor is required and cannot be None.")
    if not has_merchant_permission(actor, merchant, MerchantPermission.MANAGE_CATALOGUE):
        raise ProductPermissionDeniedError(
            f"User does not have permission to manage catalogue for merchant '{merchant.name}'."
        )


# ==================== PRODUCT SERVICES ====================


def create_product(
    *,
    merchant_id: uuid.UUID | str | Merchant,
    actor: Any,
    name: str,
    slug: str | None = None,
    sku: str | None = None,
    description: str = "",
    price: Decimal | None = None,
    mrp: Decimal | None = None,
    price_display_mode: str = _UNSET,
    currency: str = Currency.INR,
    is_available: bool = _UNSET,
    availability_mode: str = _UNSET,
    category_ids: list[uuid.UUID | str] | None = None,
    attributes: dict[str, Any] | None = None,
) -> Product:
    """
    Atomically creates a new Product in DRAFT status for a Merchant.
    - Locks Merchant row.
    - Validates actor's active membership and MANAGE_CATALOGUE permission.
    - Enforces merchant-scoped slug and SKU uniqueness.
    - Validates attributes schema and price bounds.
    - Validates that assigned categories belong strictly to this merchant.
    """
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError(_("Product name cannot be empty."))

    if slug:
        clean_slug = validate_and_normalize_slug(slug, max_length=255)
    else:
        clean_slug = validate_and_normalize_slug(clean_name, max_length=255)

    clean_sku = sku.strip() if sku and sku.strip() else None

    # Availability synchronization & validation
    if availability_mode is not _UNSET and is_available is not _UNSET:
        expected_avail = availability_mode != AvailabilityMode.OUT_OF_STOCK
        if bool(is_available) != expected_avail:
            raise ValidationError(
                _(
                    "Contradictory availability values: availability_mode '%(mode)s' "
                    "conflicts with is_available=%(avail)s."
                )
                % {"mode": availability_mode, "avail": is_available}
            )
        final_mode = availability_mode
        final_avail = bool(is_available)
    elif availability_mode is not _UNSET:
        final_mode = availability_mode
        final_avail = availability_mode != AvailabilityMode.OUT_OF_STOCK
    elif is_available is not _UNSET:
        final_avail = bool(is_available)
        final_mode = AvailabilityMode.IN_STOCK if final_avail else AvailabilityMode.OUT_OF_STOCK
    else:
        final_mode = AvailabilityMode.IN_STOCK
        final_avail = True

    if price_display_mode is _UNSET:
        if price is None:
            final_price_display_mode = PriceDisplayMode.CONTACT_FOR_PRICE
        else:
            final_price_display_mode = PriceDisplayMode.SHOW_PRICE
    else:
        final_price_display_mode = price_display_mode

    validate_product_pricing(
        price=price,
        mrp=mrp,
        price_display_mode=final_price_display_mode,
        status=ProductStatus.DRAFT,
    )

    clean_attributes = validate_attributes(attributes) if attributes else {}

    resolved_merchant = _resolve_merchant(merchant_id)

    with transaction.atomic():
        # 1. Lock Merchant row
        merchant = Merchant.objects.select_for_update().get(id=resolved_merchant.id)
        _check_permission(actor, merchant)

        # 2. Check slug uniqueness within merchant
        if (
            Product.objects.annotate(lower_slug=Lower("slug"))
            .filter(merchant=merchant, lower_slug=clean_slug.lower())
            .exists()
        ):
            raise ProductSlugAlreadyTakenError(
                f"A product with the slug '{clean_slug}' already exists in your catalogue."
            )

        # 3. Check SKU uniqueness within merchant
        if clean_sku and Product.objects.filter(merchant=merchant, sku=clean_sku).exists():
            raise DuplicateSKUError(
                f"A product with the SKU '{clean_sku}' already exists in your catalogue."
            )

        # 4. Create Product
        try:
            product = Product.objects.create(
                merchant=merchant,
                name=clean_name,
                slug=clean_slug,
                sku=clean_sku,
                description=description.strip() if description else "",
                price=price,
                mrp=mrp,
                price_display_mode=final_price_display_mode,
                currency=currency,
                status=ProductStatus.DRAFT,
                availability_mode=final_mode,
                is_available=final_avail,
                attributes=clean_attributes,
            )
        except IntegrityError as exc:
            err_msg = str(exc).lower()
            if "slug" in err_msg or "unique_merchant_product_slug" in err_msg:
                raise ProductSlugAlreadyTakenError(
                    f"A product with the slug '{clean_slug}' already exists."
                ) from exc
            if "sku" in err_msg or "unique_merchant_product_sku" in err_msg:
                raise DuplicateSKUError(
                    f"A product with the SKU '{clean_sku}' already exists."
                ) from exc
            raise

        # 5. Assign categories if provided
        if category_ids:
            _assign_product_categories_internal(product, category_ids)

        return product


def update_product_profile(
    *,
    product_id: uuid.UUID | str,
    actor: Any,
    name: str = _UNSET,
    description: str = _UNSET,
    price: Decimal | None = _UNSET,
    mrp: Decimal | None = _UNSET,
    price_display_mode: str = _UNSET,
    currency: str = _UNSET,
    sku: str | None = _UNSET,
    is_available: bool = _UNSET,
    availability_mode: str = _UNSET,
    attributes: dict[str, Any] = _UNSET,
) -> Product:
    """
    Atomically updates core profile fields of an existing product.
    """
    with transaction.atomic():
        try:
            product = (
                Product.objects.select_for_update().select_related("merchant").get(id=product_id)
            )
        except (Product.DoesNotExist, ValueError) as exc:
            raise ProductNotFoundError(f"Product with ID '{product_id}' does not exist.") from exc

        _check_permission(actor, product.merchant)

        if name is not _UNSET:
            clean_name = (name or "").strip()
            if not clean_name:
                raise ValidationError(_("Product name cannot be empty."))
            product.name = clean_name

        if description is not _UNSET:
            product.description = (description or "").strip()

        target_price = product.price if price is _UNSET else price
        target_mrp = product.mrp if mrp is _UNSET else mrp
        target_mode = (
            product.price_display_mode if price_display_mode is _UNSET else price_display_mode
        )
        validate_product_pricing(
            price=target_price,
            mrp=target_mrp,
            price_display_mode=target_mode,
            status=product.status,
        )

        if price is not _UNSET:
            product.price = price

        if mrp is not _UNSET:
            product.mrp = mrp

        if price_display_mode is not _UNSET:
            product.price_display_mode = price_display_mode

        if currency is not _UNSET:
            product.currency = currency

        if sku is not _UNSET:
            clean_sku = sku.strip() if sku and sku.strip() else None
            if clean_sku and clean_sku != product.sku:
                if (
                    Product.objects.filter(merchant=product.merchant, sku=clean_sku)
                    .exclude(id=product.id)
                    .exists()
                ):
                    raise DuplicateSKUError(
                        f"A product with the SKU '{clean_sku}' already exists in your catalogue."
                    )
            product.sku = clean_sku

        if availability_mode is not _UNSET and is_available is not _UNSET:
            expected_avail = availability_mode != AvailabilityMode.OUT_OF_STOCK
            if bool(is_available) != expected_avail:
                raise ValidationError(
                    _(
                        "Contradictory availability values: availability_mode '%(mode)s' "
                        "conflicts with is_available=%(avail)s."
                    )
                    % {"mode": availability_mode, "avail": is_available}
                )
            product.availability_mode = availability_mode
            product.is_available = bool(is_available)
        elif availability_mode is not _UNSET:
            product.availability_mode = availability_mode
            product.is_available = availability_mode != AvailabilityMode.OUT_OF_STOCK
        elif is_available is not _UNSET:
            product.is_available = bool(is_available)
            product.availability_mode = (
                AvailabilityMode.IN_STOCK if product.is_available else AvailabilityMode.OUT_OF_STOCK
            )

        if attributes is not _UNSET:
            product.attributes = validate_attributes(attributes)

        try:
            product.save()
        except IntegrityError as exc:
            err_msg = str(exc).lower()
            if "sku" in err_msg or "unique_merchant_product_sku" in err_msg:
                raise DuplicateSKUError(
                    f"A product with the SKU '{product.sku}' already exists."
                ) from exc
            raise

        return product


def change_product_slug(
    *,
    product_id: uuid.UUID | str,
    actor: Any,
    new_slug: str,
) -> Product:
    """
    Atomically changes a product's URL slug within the merchant's namespace.
    """
    clean_slug = validate_and_normalize_slug(new_slug, max_length=255)

    with transaction.atomic():
        try:
            product = (
                Product.objects.select_for_update().select_related("merchant").get(id=product_id)
            )
        except (Product.DoesNotExist, ValueError) as exc:
            raise ProductNotFoundError(f"Product with ID '{product_id}' does not exist.") from exc

        _check_permission(actor, product.merchant)

        if clean_slug.lower() == product.slug.lower():
            return product

        if (
            Product.objects.annotate(lower_slug=Lower("slug"))
            .filter(merchant=product.merchant, lower_slug=clean_slug.lower())
            .exclude(id=product.id)
            .exists()
        ):
            raise ProductSlugAlreadyTakenError(
                f"A product with the slug '{clean_slug}' already exists in your catalogue."
            )

        product.slug = clean_slug
        try:
            product.save(update_fields=["slug", "updated_at"])
        except IntegrityError as exc:
            raise ProductSlugAlreadyTakenError(
                f"A product with the slug '{clean_slug}' already exists."
            ) from exc

        return product


def publish_product(
    *,
    product_id: uuid.UUID | str,
    actor: Any,
) -> Product:
    """
    Transitions product from DRAFT to PUBLISHED.
    Rejects publishing an ARCHIVED product.
    """
    with transaction.atomic():
        try:
            product = (
                Product.objects.select_for_update().select_related("merchant").get(id=product_id)
            )
        except (Product.DoesNotExist, ValueError) as exc:
            raise ProductNotFoundError(f"Product with ID '{product_id}' does not exist.") from exc

        _check_permission(actor, product.merchant)

        if product.status == ProductStatus.ARCHIVED:
            raise ProductLifecycleError(
                _("Cannot publish an archived product. Create a new product or restore it.")
            )

        if product.status == ProductStatus.PUBLISHED:
            return product

        if product.price_display_mode == PriceDisplayMode.SHOW_PRICE and product.price is None:
            raise ValidationError(
                _("Cannot publish product: selling price is required when Show Price is selected.")
            )

        product.status = ProductStatus.PUBLISHED
        product.save(update_fields=["status", "updated_at"])
        return product


def unpublish_product(
    *,
    product_id: uuid.UUID | str,
    actor: Any,
) -> Product:
    """
    Transitions product from PUBLISHED back to DRAFT.
    Rejects unpublishing an ARCHIVED product.
    """
    with transaction.atomic():
        try:
            product = (
                Product.objects.select_for_update().select_related("merchant").get(id=product_id)
            )
        except (Product.DoesNotExist, ValueError) as exc:
            raise ProductNotFoundError(f"Product with ID '{product_id}' does not exist.") from exc

        _check_permission(actor, product.merchant)

        if product.status == ProductStatus.ARCHIVED:
            raise ProductLifecycleError(_("Cannot unpublish an archived product."))

        if product.status == ProductStatus.DRAFT:
            return product

        product.status = ProductStatus.DRAFT
        product.save(update_fields=["status", "updated_at"])
        return product


def archive_product(
    *,
    product_id: uuid.UUID | str,
    actor: Any,
) -> Product:
    """
    Soft-deletes a product by transitioning it to ARCHIVED status.
    Archived products are hidden from public and active catalogue queries.
    """
    with transaction.atomic():
        try:
            product = (
                Product.objects.select_for_update().select_related("merchant").get(id=product_id)
            )
        except (Product.DoesNotExist, ValueError) as exc:
            raise ProductNotFoundError(f"Product with ID '{product_id}' does not exist.") from exc

        _check_permission(actor, product.merchant)

        if product.status == ProductStatus.ARCHIVED:
            return product

        product.status = ProductStatus.ARCHIVED
        product.save(update_fields=["status", "updated_at"])
        return product


# ==================== CATEGORY SERVICES ====================


def create_category(
    *,
    merchant_id: uuid.UUID | str | Merchant,
    actor: Any,
    name: str,
    slug: str | None = None,
    description: str = "",
    image: Any = None,
    display_order: int = 0,
    is_active: bool = True,
) -> Category:
    """
    Atomically creates a new Category for a Merchant.
    - Locks Merchant row.
    - Validates actor's active membership and MANAGE_CATALOGUE permission.
    - Enforces merchant-scoped category slug uniqueness.
    """
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError(_("Category name cannot be empty."))

    if slug:
        clean_slug = validate_and_normalize_slug(slug, max_length=160)
    else:
        clean_slug = validate_and_normalize_slug(clean_name, max_length=160)

    if image:
        validate_product_image(image)

    resolved_merchant = _resolve_merchant(merchant_id)

    with transaction.atomic():
        merchant = Merchant.objects.select_for_update().get(id=resolved_merchant.id)
        _check_permission(actor, merchant)

        if (
            Category.objects.annotate(lower_slug=Lower("slug"))
            .filter(merchant=merchant, lower_slug=clean_slug.lower())
            .exists()
        ):
            raise CategorySlugAlreadyTakenError(
                f"A category with the slug '{clean_slug}' already exists in your catalogue."
            )

        try:
            category = Category.objects.create(
                merchant=merchant,
                name=clean_name,
                slug=clean_slug,
                description=description.strip() if description else "",
                image=image,
                display_order=max(0, display_order),
                is_active=is_active,
            )
        except IntegrityError as exc:
            err_msg = str(exc).lower()
            if "slug" in err_msg or "unique_merchant_category_slug" in err_msg:
                raise CategorySlugAlreadyTakenError(
                    f"A category with the slug '{clean_slug}' already exists."
                ) from exc
            raise

        return category


def update_category(
    *,
    category_id: uuid.UUID | str,
    actor: Any,
    name: str = _UNSET,
    description: str = _UNSET,
    image: Any = _UNSET,
    display_order: int = _UNSET,
    is_active: bool = _UNSET,
) -> Category:
    """
    Atomically updates category details and display properties.
    """
    with transaction.atomic():
        try:
            category = (
                Category.objects.select_for_update().select_related("merchant").get(id=category_id)
            )
        except (Category.DoesNotExist, ValueError) as exc:
            raise CategoryNotFoundError(
                f"Category with ID '{category_id}' does not exist."
            ) from exc

        _check_permission(actor, category.merchant)

        if name is not _UNSET:
            clean_name = (name or "").strip()
            if not clean_name:
                raise ValidationError(_("Category name cannot be empty."))
            category.name = clean_name

        if description is not _UNSET:
            category.description = (description or "").strip()

        if image is not _UNSET:
            if image is not None:
                validate_product_image(image)
            category.image = image

        if display_order is not _UNSET:
            category.display_order = max(0, display_order)

        if is_active is not _UNSET:
            category.is_active = bool(is_active)

        category.save()
        return category


def deactivate_category(
    *,
    category_id: uuid.UUID | str,
    actor: Any,
) -> Category:
    """
    Deactivates a category (is_active=False).
    Products associated with the category remain intact.
    """
    return update_category(category_id=category_id, actor=actor, is_active=False)


# ==================== PRODUCT-CATEGORY ASSIGNMENT ====================


def _assign_product_categories_internal(
    product: Product,
    category_ids: list[uuid.UUID | str],
) -> None:
    """
    Internal assignment helper.
    Ensures that ALL category_ids belong strictly to product.merchant.
    Atomic: if any category is cross-tenant or missing, rolls back and raises an exception.
    """
    if not category_ids:
        ProductCategory.objects.filter(product=product).delete()
        return

    # 1. Look up categories within this merchant
    valid_merchant_categories = list(
        Category.objects.filter(merchant=product.merchant, id__in=category_ids)
    )

    if len(valid_merchant_categories) != len(set(category_ids)):
        # Identify whether categories are nonexistent or belonging to another merchant
        foreign_categories = list(
            Category.objects.filter(id__in=category_ids).exclude(merchant=product.merchant)
        )
        if foreign_categories:
            names = ", ".join(f"'{c.name}'" for c in foreign_categories)
            raise CrossTenantAssignmentError(
                f"Cannot assign categories {names} as they belong to a different business organization."
            )
        raise CategoryNotFoundError("One or more specified categories do not exist.")

    # 2. Synchronize assignments atomically
    existing_assignments = set(
        ProductCategory.objects.filter(product=product).values_list("category_id", flat=True)
    )
    desired_ids = {c.id for c in valid_merchant_categories}

    to_remove = existing_assignments - desired_ids
    if to_remove:
        ProductCategory.objects.filter(product=product, category_id__in=to_remove).delete()

    to_add = [
        ProductCategory(product=product, category=c)
        for c in valid_merchant_categories
        if c.id not in existing_assignments
    ]
    if to_add:
        ProductCategory.objects.bulk_create(to_add)


def assign_product_categories(
    *,
    product_id: uuid.UUID | str,
    actor: Any,
    category_ids: list[uuid.UUID | str],
) -> Product:
    """
    Authoritatively assigns categories to a product.
    Rejects the entire operation if ANY category belongs to a different merchant.
    """
    with transaction.atomic():
        try:
            product = (
                Product.objects.select_for_update().select_related("merchant").get(id=product_id)
            )
        except (Product.DoesNotExist, ValueError) as exc:
            raise ProductNotFoundError(f"Product with ID '{product_id}' does not exist.") from exc

        _check_permission(actor, product.merchant)
        _assign_product_categories_internal(product, category_ids)

        return product


# ==================== PRODUCT IMAGE SERVICES ====================


def add_product_image(
    *,
    product_id: uuid.UUID | str,
    actor: Any,
    image_file: Any,
    alt_text: str = "",
    is_primary: bool = False,
    display_order: int = 0,
) -> ProductImage:
    """
    Validates and uploads an image for a product.
    - Decodes and validates image with Pillow.
    - If is_primary=True, unsets any existing primary image for this product.
    - If this is the product's first image, automatically designates it as primary.
    """
    validate_product_image(image_file)

    with transaction.atomic():
        try:
            product = (
                Product.objects.select_for_update().select_related("merchant").get(id=product_id)
            )
        except (Product.DoesNotExist, ValueError) as exc:
            raise ProductNotFoundError(f"Product with ID '{product_id}' does not exist.") from exc

        _check_permission(actor, product.merchant)

        existing_images_count = ProductImage.objects.filter(product=product).count()

        # If designated as primary or if this is the first image uploaded, set as primary
        make_primary = is_primary or (existing_images_count == 0)

        if make_primary:
            ProductImage.objects.filter(product=product, is_primary=True).update(is_primary=False)

        product_image = ProductImage.objects.create(
            product=product,
            image=image_file,
            alt_text=(alt_text or "").strip(),
            display_order=max(0, display_order),
            is_primary=make_primary,
        )

        return product_image


def remove_product_image(
    *,
    image_id: uuid.UUID | str,
    actor: Any,
) -> None:
    """
    Deletes a product gallery image and triggers post-commit file cleanup.
    If the deleted image was primary, promotes the next image in display order.
    """
    with transaction.atomic():
        try:
            product_image = (
                ProductImage.objects.select_for_update()
                .select_related("product__merchant")
                .get(id=image_id)
            )
        except (ProductImage.DoesNotExist, ValueError) as exc:
            raise InvalidProductImageError(
                f"Product image with ID '{image_id}' does not exist."
            ) from exc

        product = product_image.product
        _check_permission(actor, product.merchant)

        was_primary = product_image.is_primary

        product_image.delete()

        # If primary image was removed, promote the next available image
        if was_primary:
            next_image = (
                ProductImage.objects.filter(product=product)
                .order_by("display_order", "created_at")
                .first()
            )
            if next_image:
                next_image.is_primary = True
                next_image.save(update_fields=["is_primary"])


def set_primary_product_image(
    *,
    image_id: uuid.UUID | str,
    actor: Any,
) -> ProductImage:
    """
    Promotes an existing product image to primary thumbnail.
    """
    with transaction.atomic():
        try:
            product_image = (
                ProductImage.objects.select_for_update()
                .select_related("product__merchant")
                .get(id=image_id)
            )
        except (ProductImage.DoesNotExist, ValueError) as exc:
            raise InvalidProductImageError(
                f"Product image with ID '{image_id}' does not exist."
            ) from exc

        product = product_image.product
        _check_permission(actor, product.merchant)

        ProductImage.objects.filter(product=product, is_primary=True).update(is_primary=False)
        product_image.is_primary = True
        product_image.save(update_fields=["is_primary"])

        return product_image
