import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower

from apps.merchants.choices import MembershipStatus, MerchantStatus
from apps.merchants.models import Merchant
from apps.merchants.permissions import (
    MerchantPermission,
    can_perform_merchant_action,
    has_merchant_permission,
    has_role_permission,
)

from .choices import StoreStatus
from .exceptions import (
    DuplicateStoreError,
    SlugAlreadyTakenError,
    StorePermissionDeniedError,
    StorePublishError,
)
from .models import Store
from .validators import validate_and_normalize_slug

_UNSET = object()


def create_store(
    *,
    merchant_id: uuid.UUID | str | Merchant,
    actor: Any,
    name: str,
    slug: str,
    description: str = "",
    logo: Any = None,
    cover_image: Any = None,
) -> Store:
    """
    Atomically creates a new Store for a Merchant in DRAFT status.

    Requirements:
    - Actor is mandatory and validated server-side.
    - Resolves Merchant server-side and locks Merchant row first.
    - Verifies actor's active membership and MANAGE_STORE permission.
    - Enforces that one Merchant has at most one Store.
    - Explicitly normalizes and validates slug; rejects reserved and duplicate slugs.
    - Handles concurrent collisions safely via atomic transactions.
    """
    if actor is None:
        raise TypeError("actor is required and cannot be None.")

    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError("Store name cannot be empty.")

    normalized_slug = validate_and_normalize_slug(slug)

    # Check for slug conflict upfront
    if Store.objects.annotate(lower_slug=Lower("slug")).filter(lower_slug=normalized_slug).exists():
        raise SlugAlreadyTakenError(f"The slug '{normalized_slug}' is already taken.")

    resolved_merchant_id = getattr(merchant_id, "id", merchant_id)

    with transaction.atomic():
        # 1. Lock Merchant row first
        try:
            merchant = Merchant.objects.select_for_update().get(id=resolved_merchant_id)
        except (Merchant.DoesNotExist, ValueError) as exc:
            raise ValidationError(
                f"Merchant with ID '{resolved_merchant_id}' does not exist."
            ) from exc

        # 2. Server-side authorization check
        if not has_merchant_permission(actor, merchant, MerchantPermission.MANAGE_STORE):
            raise StorePermissionDeniedError(
                f"User does not have permission to create a store for merchant '{merchant.name}'."
            )

        # 3. Prevent duplicate store for this merchant
        if Store.objects.filter(merchant=merchant).exists():
            raise DuplicateStoreError(
                f"Merchant '{merchant.name}' already has an associated store."
            )

        # 4. Insert store in DRAFT status
        try:
            store = Store.objects.create(
                merchant=merchant,
                name=clean_name,
                slug=normalized_slug,
                description=description.strip() if description else "",
                logo=logo,
                cover_image=cover_image,
                status=StoreStatus.DRAFT,
            )
        except IntegrityError as exc:
            err_msg = str(exc).lower()
            if "slug" in err_msg or "unique_lowercase_store_slug" in err_msg:
                raise SlugAlreadyTakenError(
                    f"The slug '{normalized_slug}' is already taken."
                ) from exc
            if "merchant_id" in err_msg:
                raise DuplicateStoreError(
                    f"Merchant '{merchant.name}' already has an associated store."
                ) from exc
            raise

        return store


def update_store_profile(
    *,
    store_id: uuid.UUID | str | Store,
    actor: Any,
    name: str | None = None,
    description: str | None = None,
    logo: Any = _UNSET,
    cover_image: Any = _UNSET,
) -> Store:
    """
    Updates store branding details (name, description, logo, cover image).

    Requirements:
    - Actor is mandatory and verified server-side.
    - Consistent lock order: Merchant first, then Store.
    - Verifies actor's active membership and MANAGE_STORE permission.
    - Never mutates slug or status.
    """
    if actor is None:
        raise TypeError("actor is required and cannot be None.")

    resolved_store_id = getattr(store_id, "id", store_id)

    with transaction.atomic():
        store_lookup = (
            Store.objects.filter(id=resolved_store_id).values_list("merchant_id", flat=True).first()
        )
        if not store_lookup:
            raise ValidationError(f"Store with ID '{resolved_store_id}' does not exist.")

        merchant_id = store_lookup

        # 1. Lock Merchant first
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # 2. Lock Store second
        store = Store.objects.select_for_update().get(id=resolved_store_id)

        # 3. Server-side authorization check
        if not has_merchant_permission(actor, merchant, MerchantPermission.MANAGE_STORE):
            raise StorePermissionDeniedError(
                f"User does not have permission to update store for merchant '{merchant.name}'."
            )

        # 4. Apply branding field updates
        update_fields = ["updated_at"]

        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValidationError("Store name cannot be empty.")
            store.name = clean_name
            update_fields.append("name")

        if description is not None:
            store.description = description.strip()
            update_fields.append("description")

        if logo is not _UNSET:
            store.logo = logo
            update_fields.append("logo")

        if cover_image is not _UNSET:
            store.cover_image = cover_image
            update_fields.append("cover_image")

        store.save(update_fields=update_fields)
        return store


def change_store_slug(
    *,
    store_id: uuid.UUID | str | Store,
    actor: Any,
    new_slug: str,
) -> Store:
    """
    Changes store URL slug.

    Requirements:
    - Actor is mandatory and verified server-side.
    - Normalizes and validates new_slug against format and reserved words.
    - Consistent lock order: Merchant first, then Store.
    - Verifies actor's active membership and CHANGE_STORE_SLUG permission.
    - Atomically updates slug; safely catches race conditions.
    """
    if actor is None:
        raise TypeError("actor is required and cannot be None.")

    normalized_slug = validate_and_normalize_slug(new_slug)
    resolved_store_id = getattr(store_id, "id", store_id)

    # Check for slug conflict upfront
    if (
        Store.objects.annotate(lower_slug=Lower("slug"))
        .filter(lower_slug=normalized_slug)
        .exclude(id=resolved_store_id)
        .exists()
    ):
        raise SlugAlreadyTakenError(f"The slug '{normalized_slug}' is already taken.")

    with transaction.atomic():
        store_lookup = (
            Store.objects.filter(id=resolved_store_id).values_list("merchant_id", flat=True).first()
        )
        if not store_lookup:
            raise ValidationError(f"Store with ID '{resolved_store_id}' does not exist.")

        merchant_id = store_lookup

        # 1. Lock Merchant first
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # 2. Lock Store second
        store = Store.objects.select_for_update().get(id=resolved_store_id)

        # 3. Server-side authorization check
        if not has_merchant_permission(actor, merchant, MerchantPermission.CHANGE_STORE_SLUG):
            raise StorePermissionDeniedError(
                f"User does not have permission to change store slug for merchant '{merchant.name}'."
            )

        # 4. Save new slug
        if store.slug == normalized_slug:
            return store

        store.slug = normalized_slug
        try:
            store.save(update_fields=["slug", "updated_at"])
        except IntegrityError as exc:
            err_msg = str(exc).lower()
            if "slug" in err_msg or "unique_lowercase_store_slug" in err_msg:
                raise SlugAlreadyTakenError(
                    f"The slug '{normalized_slug}' is already taken."
                ) from exc
            raise

        return store


def publish_store(
    *,
    store_id: uuid.UUID | str | Store,
    actor: Any,
) -> Store:
    """
    Transitions store status to PUBLISHED.

    Requirements:
    - Actor is mandatory and verified server-side.
    - Consistent lock order: Merchant first, then Store.
    - Verifies actor's active membership and PUBLISH_STORE permission.
    - Precondition: Merchant status MUST be ACTIVE.
    - Precondition: Store must have valid name and slug.
    """
    if actor is None:
        raise TypeError("actor is required and cannot be None.")

    resolved_store_id = getattr(store_id, "id", store_id)

    with transaction.atomic():
        store_lookup = (
            Store.objects.filter(id=resolved_store_id).values_list("merchant_id", flat=True).first()
        )
        if not store_lookup:
            raise ValidationError(f"Store with ID '{resolved_store_id}' does not exist.")

        merchant_id = store_lookup

        # 1. Lock Merchant first
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # 2. Lock Store second
        store = Store.objects.select_for_update().get(id=resolved_store_id)

        # 3. Server-side membership and role authorization check
        membership = (
            merchant.memberships.filter(
                user=actor,
                status=MembershipStatus.ACTIVE,
            )
            .select_related("merchant")
            .first()
        )
        if not membership or not has_role_permission(
            membership.role, MerchantPermission.PUBLISH_STORE
        ):
            raise StorePermissionDeniedError(
                f"User does not have permission to publish the store for merchant '{merchant.name}'."
            )

        # 4. Invariant: Merchant must be ACTIVE
        if merchant.status != MerchantStatus.ACTIVE:
            raise StorePublishError(
                f"Cannot publish store: Merchant '{merchant.name}' is in {merchant.status} status. "
                "Merchant organization must be in ACTIVE status before publishing the store."
            )

        # 5. Full operational check
        if not can_perform_merchant_action(membership, MerchantPermission.PUBLISH_STORE):
            raise StorePermissionDeniedError(
                "User cannot perform publish action in current merchant state."
            )

        # 5. Invariant: Store must have name and slug
        if not store.name or not store.name.strip():
            raise StorePublishError("Cannot publish store without a name.")
        if not store.slug or not store.slug.strip():
            raise StorePublishError("Cannot publish store without a slug.")

        store.status = StoreStatus.PUBLISHED
        store.save(update_fields=["status", "updated_at"])
        return store


def unpublish_store(
    *,
    store_id: uuid.UUID | str | Store,
    actor: Any,
) -> Store:
    """
    Transitions store status to UNPUBLISHED.

    Requirements:
    - Actor is mandatory and verified server-side.
    - Consistent lock order: Merchant first, then Store.
    - Verifies actor's active membership and PUBLISH_STORE permission.
    """
    if actor is None:
        raise TypeError("actor is required and cannot be None.")

    resolved_store_id = getattr(store_id, "id", store_id)

    with transaction.atomic():
        store_lookup = (
            Store.objects.filter(id=resolved_store_id).values_list("merchant_id", flat=True).first()
        )
        if not store_lookup:
            raise ValidationError(f"Store with ID '{resolved_store_id}' does not exist.")

        merchant_id = store_lookup

        # 1. Lock Merchant first
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # 2. Lock Store second
        store = Store.objects.select_for_update().get(id=resolved_store_id)

        # 3. Server-side authorization check
        if not has_merchant_permission(actor, merchant, MerchantPermission.PUBLISH_STORE):
            raise StorePermissionDeniedError(
                f"User does not have permission to unpublish the store for merchant '{merchant.name}'."
            )

        store.status = StoreStatus.UNPUBLISHED
        store.save(update_fields=["status", "updated_at"])
        return store
