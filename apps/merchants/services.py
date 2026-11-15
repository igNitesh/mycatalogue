import uuid
from typing import Any

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus
from .exceptions import MerchantPermissionDeniedError, SoleOwnerProtectionError
from .models import Merchant, MerchantMembership, MerchantOwnershipTransferLog
from .permissions import MerchantPermission, can_perform_merchant_action

User = get_user_model()


def create_merchant(
    owner_user: Any,
    name: str,
    email: str,
    contact_number: str,
    address: str,
    city: str,
    state: str,
    pin_code: str,
    business_type: str = BusinessType.RETAIL,
    description: str = "",
) -> tuple[Merchant, MerchantMembership]:
    """
    Atomically creates a new merchant organization in PENDING status
    and establishes the initial ACTIVE OWNER membership.
    """
    with transaction.atomic():
        merchant = Merchant.objects.create(
            name=name,
            email=email,
            contact_number=contact_number,
            address=address,
            city=city,
            state=state,
            pin_code=pin_code,
            business_type=business_type,
            description=description,
            status=MerchantStatus.PENDING,
        )

        owner_membership = MerchantMembership.objects.create(
            user=owner_user,
            merchant=merchant,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )

        return merchant, owner_membership


def add_member_to_merchant(
    merchant_id: uuid.UUID,
    actor_user: Any,
    target_user: Any,
    role: str = MembershipRole.STAFF,
) -> MerchantMembership:
    """
    Atomically adds a registered user to a merchant with the designated role.
    Acquires merchant row lock first.
    """
    with transaction.atomic():
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # Actor permission check
        actor_membership = MerchantMembership.objects.select_for_update().get(
            merchant=merchant, user=actor_user
        )

        if role == MembershipRole.ADMIN and not can_perform_merchant_action(
            actor_membership, MerchantPermission.MANAGE_ADMINS
        ):
            raise MerchantPermissionDeniedError(_("Only owners can assign the Admin role."))
        elif role == MembershipRole.MANAGER and not can_perform_merchant_action(
            actor_membership, MerchantPermission.MANAGE_MANAGERS
        ):
            raise MerchantPermissionDeniedError(
                _("You lack permission to assign the Manager role.")
            )
        elif role == MembershipRole.STAFF and not can_perform_merchant_action(
            actor_membership, MerchantPermission.MANAGE_STAFF
        ):
            raise MerchantPermissionDeniedError(_("You lack permission to assign staff members."))

        membership, created = MerchantMembership.objects.get_or_create(
            merchant=merchant,
            user=target_user,
            defaults={"role": role, "status": MembershipStatus.ACTIVE},
        )
        if not created:
            raise ValidationError(_("This user already has a membership with this merchant."))

        return membership


def transfer_ownership(
    merchant_id: uuid.UUID,
    actor_user: Any,
    target_user: Any,
    demote_actor_to: str = MembershipRole.ADMIN,
) -> tuple[MerchantMembership, MerchantMembership, MerchantOwnershipTransferLog]:
    """
    Atomically transfers primary ownership from actor_user to target_user.

    Strict lock ordering:
    1. Lock Merchant row first.
    2. Lock Actor and Target memberships.
    """
    if actor_user.pk == target_user.pk:
        raise ValidationError(_("Cannot transfer ownership to yourself."))

    if demote_actor_to == MembershipRole.OWNER:
        raise ValidationError(_("The previous owner must be demoted to a non-owner role."))

    with transaction.atomic():
        # 1. Lock Merchant row first
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # 2. Lock Actor membership
        try:
            actor_membership = MerchantMembership.objects.select_for_update().get(
                merchant=merchant,
                user=actor_user,
                role=MembershipRole.OWNER,
                status=MembershipStatus.ACTIVE,
            )
        except MerchantMembership.DoesNotExist as exc:
            raise PermissionDenied(
                _("Requesting user is not an active owner of this merchant.")
            ) from exc

        # 3. Lock Target membership
        try:
            target_membership = MerchantMembership.objects.select_for_update().get(
                merchant=merchant,
                user=target_user,
            )
        except MerchantMembership.DoesNotExist as exc:
            raise ValidationError(
                _("Target user does not have a membership in this merchant.")
            ) from exc

        if target_membership.status != MembershipStatus.ACTIVE:
            raise ValidationError(
                _("Target user must have an active membership to receive ownership.")
            )

        # 4. Execute atomic promotion & demotion
        target_membership.role = MembershipRole.OWNER
        target_membership.save(update_fields=["role", "updated_at"])

        actor_membership.role = demote_actor_to
        actor_membership.save(update_fields=["role", "updated_at"])

        # 5. Record immutable audit log
        log_entry = MerchantOwnershipTransferLog.objects.create(
            merchant=merchant,
            previous_owner=actor_user,
            new_owner=target_user,
            transferred_by=actor_user,
        )

        return target_membership, actor_membership, log_entry


def change_membership_role(
    merchant_id: uuid.UUID,
    actor_user: Any,
    target_user: Any,
    new_role: str,
) -> MerchantMembership:
    """
    Atomically updates a member's role.
    Strict lock ordering: Merchant first, then all active owners and target member.
    Enforces sole active owner protection.
    """
    with transaction.atomic():
        # 1. Lock Merchant row first
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # 2. Lock active owners
        active_owners = list(
            MerchantMembership.objects.select_for_update().filter(
                merchant=merchant,
                role=MembershipRole.OWNER,
                status=MembershipStatus.ACTIVE,
            )
        )

        # 3. Lock target membership
        target_membership = MerchantMembership.objects.select_for_update().get(
            merchant=merchant, user=target_user
        )

        # 4. Sole active owner protection check
        is_active_owner = any(owner.pk == target_membership.pk for owner in active_owners)
        if is_active_owner and new_role != MembershipRole.OWNER:
            if len(active_owners) <= 1:
                raise SoleOwnerProtectionError(
                    _("Cannot demote the sole active owner of a merchant.")
                )

        target_membership.role = new_role
        target_membership.save(update_fields=["role", "updated_at"])
        return target_membership


def update_membership_status(
    merchant_id: uuid.UUID,
    actor_user: Any,
    target_user: Any,
    new_status: str,
) -> MerchantMembership:
    """
    Atomically updates membership status (suspend, revoke, or reinstate).
    Strict lock ordering: Merchant first, then active owners and target member.
    Enforces sole active owner protection.
    """
    with transaction.atomic():
        # 1. Lock Merchant row first
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # 2. Lock active owners
        active_owners = list(
            MerchantMembership.objects.select_for_update().filter(
                merchant=merchant,
                role=MembershipRole.OWNER,
                status=MembershipStatus.ACTIVE,
            )
        )

        # 3. Lock target membership
        target_membership = MerchantMembership.objects.select_for_update().get(
            merchant=merchant, user=target_user
        )

        # 4. Sole active owner protection check
        is_active_owner = any(owner.pk == target_membership.pk for owner in active_owners)
        if is_active_owner and new_status != MembershipStatus.ACTIVE:
            if len(active_owners) <= 1:
                raise SoleOwnerProtectionError(
                    _("Cannot suspend or revoke the sole active owner of a merchant.")
                )

        target_membership.status = new_status
        target_membership.save(update_fields=["status", "updated_at"])
        return target_membership


def delete_membership(
    merchant_id: uuid.UUID,
    target_user: Any,
) -> None:
    """
    Atomically deletes a membership.
    Strict lock ordering: Merchant first, then active owners and target member.
    Enforces sole active owner protection.
    """
    with transaction.atomic():
        # 1. Lock Merchant row first
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # 2. Lock active owners
        active_owners = list(
            MerchantMembership.objects.select_for_update().filter(
                merchant=merchant,
                role=MembershipRole.OWNER,
                status=MembershipStatus.ACTIVE,
            )
        )

        # 3. Lock target membership
        target_membership = MerchantMembership.objects.select_for_update().get(
            merchant=merchant, user=target_user
        )

        # 4. Sole active owner protection check
        is_active_owner = any(owner.pk == target_membership.pk for owner in active_owners)
        if is_active_owner and len(active_owners) <= 1:
            raise SoleOwnerProtectionError(_("Cannot delete the sole active owner of a merchant."))

        target_membership.delete()


def deactivate_merchant(
    merchant_id: uuid.UUID,
    actor_user: Any,
) -> Merchant:
    """
    Soft deactivation of a merchant organization setting status to INACTIVE.
    Physical deletion of merchants is prohibited to preserve audit history.
    """
    with transaction.atomic():
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)
        actor_membership = MerchantMembership.objects.select_for_update().get(
            merchant=merchant, user=actor_user
        )

        if not can_perform_merchant_action(
            actor_membership, MerchantPermission.DEACTIVATE_MERCHANT
        ):
            raise PermissionDenied(_("Only an active owner can deactivate a merchant account."))

        merchant.status = MerchantStatus.INACTIVE
        merchant.save(update_fields=["status", "updated_at"])
        return merchant
