import uuid
from typing import Any

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .choices import BusinessType, MembershipRole, MembershipStatus, MerchantStatus
from .exceptions import MerchantPermissionDeniedError, SoleOwnerProtectionError
from .models import Merchant, MerchantMembership, MerchantOwnershipTransferLog
from .permissions import MerchantPermission, can_perform_merchant_action

User = get_user_model()


def _get_management_permission_for_role(role: str) -> MerchantPermission:
    """Returns the required permission to manage members with the given role."""
    if role == MembershipRole.OWNER:
        return MerchantPermission.TRANSFER_OWNERSHIP
    elif role == MembershipRole.ADMIN:
        return MerchantPermission.MANAGE_ADMINS
    elif role == MembershipRole.MANAGER:
        return MerchantPermission.MANAGE_MANAGERS
    elif role == MembershipRole.STAFF:
        return MerchantPermission.MANAGE_STAFF
    raise ValidationError(_("Invalid membership role: %(role)s") % {"role": role})


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
    Acquires merchant row lock first, validates actor membership and role authority.
    """
    if not actor_user:
        raise PermissionDenied(_("Actor user is required."))

    with transaction.atomic():
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # Actor permission check
        try:
            actor_membership = MerchantMembership.objects.select_for_update().get(
                merchant=merchant, user=actor_user
            )
        except MerchantMembership.DoesNotExist as exc:
            raise PermissionDenied(
                _("Requesting user is not a member of this merchant organization.")
            ) from exc

        if actor_membership.status != MembershipStatus.ACTIVE:
            raise PermissionDenied(_("Requesting user membership is not active."))

        if role == MembershipRole.OWNER:
            if actor_membership.role != MembershipRole.OWNER or not can_perform_merchant_action(
                actor_membership, MerchantPermission.TRANSFER_OWNERSHIP
            ):
                raise MerchantPermissionDeniedError(
                    _("Only an active owner can assign the Owner role.")
                )
        elif role == MembershipRole.ADMIN and not can_perform_merchant_action(
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
    2. Lock Actor and Target memberships in deterministic PK order.
    """
    if not actor_user:
        raise PermissionDenied(_("Actor user is required."))

    if actor_user.pk == target_user.pk:
        raise ValidationError(_("Cannot transfer ownership to yourself."))

    if demote_actor_to == MembershipRole.OWNER:
        raise ValidationError(_("The previous owner must be demoted to a non-owner role."))

    with transaction.atomic():
        # 1. Lock Merchant row first
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # 2. Lock Actor and Target memberships in deterministic order
        relevant_memberships = list(
            MerchantMembership.objects.select_for_update()
            .filter(merchant=merchant)
            .filter(Q(user=actor_user) | Q(user=target_user))
            .order_by("pk")
        )

        actor_membership = next(
            (m for m in relevant_memberships if m.user_id == actor_user.pk), None
        )
        if (
            not actor_membership
            or actor_membership.role != MembershipRole.OWNER
            or actor_membership.status != MembershipStatus.ACTIVE
        ):
            raise PermissionDenied(_("Requesting user is not an active owner of this merchant."))

        target_membership = next(
            (m for m in relevant_memberships if m.user_id == target_user.pk), None
        )
        if not target_membership:
            raise ValidationError(_("Target user does not have a membership in this merchant."))

        if target_membership.status != MembershipStatus.ACTIVE:
            raise ValidationError(
                _("Target user must have an active membership to receive ownership.")
            )

        # 3. Execute atomic promotion & demotion
        target_membership.role = MembershipRole.OWNER
        target_membership.save(update_fields=["role", "updated_at"])

        actor_membership.role = demote_actor_to
        actor_membership.save(update_fields=["role", "updated_at"])

        # 4. Record immutable audit log
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
    Strict deterministic lock ordering: Merchant first, then relevant memberships ordered by PK.
    Enforces sole active owner protection and stricter dual-role transition authorization.
    """
    if not actor_user:
        raise PermissionDenied(_("Actor user is required."))

    with transaction.atomic():
        # 1. Lock Merchant row first
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # 2. Lock relevant memberships in deterministic order
        relevant_memberships = list(
            MerchantMembership.objects.select_for_update()
            .filter(merchant=merchant)
            .filter(
                Q(user=actor_user)
                | Q(user=target_user)
                | Q(role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE)
            )
            .order_by("pk")
        )

        # 3. Resolve actor and target memberships
        actor_membership = next(
            (m for m in relevant_memberships if m.user_id == actor_user.pk), None
        )
        if not actor_membership:
            raise PermissionDenied(
                _("Requesting user is not a member of this merchant organization.")
            )
        if actor_membership.status != MembershipStatus.ACTIVE:
            raise PermissionDenied(_("Requesting user membership is not active."))

        target_membership = next(
            (m for m in relevant_memberships if m.user_id == target_user.pk), None
        )
        if not target_membership:
            raise ValidationError(_("Target user does not have a membership in this merchant."))

        active_owners = [
            m
            for m in relevant_memberships
            if m.role == MembershipRole.OWNER and m.status == MembershipStatus.ACTIVE
        ]

        # 4. Dual-role transition authorization check (both current and new roles)
        # Check current role authority
        if target_membership.role == MembershipRole.OWNER:
            if actor_membership.role != MembershipRole.OWNER or not can_perform_merchant_action(
                actor_membership, MerchantPermission.TRANSFER_OWNERSHIP
            ):
                raise PermissionDenied(_("You lack permission to modify an owner's role."))
        else:
            current_perm = _get_management_permission_for_role(target_membership.role)
            if not can_perform_merchant_action(actor_membership, current_perm):
                raise PermissionDenied(_("You lack permission to modify this member's role."))

        # Check destination role authority
        if new_role == MembershipRole.OWNER:
            if actor_membership.role != MembershipRole.OWNER or not can_perform_merchant_action(
                actor_membership, MerchantPermission.TRANSFER_OWNERSHIP
            ):
                raise PermissionDenied(_("You lack permission to promote to owner."))
        else:
            dest_perm = _get_management_permission_for_role(new_role)
            if not can_perform_merchant_action(actor_membership, dest_perm):
                raise PermissionDenied(_("You lack permission to assign the requested role."))

        # 5. Sole active owner protection check
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
    Strict deterministic lock ordering: Merchant first, then relevant memberships ordered by PK.
    Enforces sole active owner protection and actor management authority.
    """
    if not actor_user:
        raise PermissionDenied(_("Actor user is required."))

    with transaction.atomic():
        # 1. Lock Merchant row first
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # 2. Lock relevant memberships in deterministic order
        relevant_memberships = list(
            MerchantMembership.objects.select_for_update()
            .filter(merchant=merchant)
            .filter(
                Q(user=actor_user)
                | Q(user=target_user)
                | Q(role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE)
            )
            .order_by("pk")
        )

        # 3. Resolve actor and target memberships
        actor_membership = next(
            (m for m in relevant_memberships if m.user_id == actor_user.pk), None
        )
        if not actor_membership:
            raise PermissionDenied(
                _("Requesting user is not a member of this merchant organization.")
            )
        if actor_membership.status != MembershipStatus.ACTIVE:
            raise PermissionDenied(_("Requesting user membership is not active."))

        target_membership = next(
            (m for m in relevant_memberships if m.user_id == target_user.pk), None
        )
        if not target_membership:
            raise ValidationError(_("Target user does not have a membership in this merchant."))

        active_owners = [
            m
            for m in relevant_memberships
            if m.role == MembershipRole.OWNER and m.status == MembershipStatus.ACTIVE
        ]

        # 4. Role management authority check
        if target_membership.role == MembershipRole.OWNER:
            if actor_membership.role != MembershipRole.OWNER or not can_perform_merchant_action(
                actor_membership, MerchantPermission.TRANSFER_OWNERSHIP
            ):
                raise PermissionDenied(_("You lack permission to modify an owner's status."))
        else:
            required_perm = _get_management_permission_for_role(target_membership.role)
            if not can_perform_merchant_action(actor_membership, required_perm):
                raise PermissionDenied(
                    _("You lack permission to modify the status of this member.")
                )

        # 5. Sole active owner protection check
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
    actor_user: Any,
    target_user: Any,
) -> None:
    """
    Atomically deletes a membership.
    Strict deterministic lock ordering: Merchant first, then relevant memberships ordered by PK.
    Enforces sole active owner protection and actor management authority.
    """
    if not actor_user:
        raise PermissionDenied(_("Actor user is required."))

    with transaction.atomic():
        # 1. Lock Merchant row first
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # 2. Lock relevant memberships in deterministic order
        relevant_memberships = list(
            MerchantMembership.objects.select_for_update()
            .filter(merchant=merchant)
            .filter(
                Q(user=actor_user)
                | Q(user=target_user)
                | Q(role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE)
            )
            .order_by("pk")
        )

        # 3. Resolve actor and target memberships
        actor_membership = next(
            (m for m in relevant_memberships if m.user_id == actor_user.pk), None
        )
        if not actor_membership:
            raise PermissionDenied(
                _("Requesting user is not a member of this merchant organization.")
            )
        if actor_membership.status != MembershipStatus.ACTIVE:
            raise PermissionDenied(_("Requesting user membership is not active."))

        target_membership = next(
            (m for m in relevant_memberships if m.user_id == target_user.pk), None
        )
        if not target_membership:
            raise ValidationError(_("Target user does not have a membership in this merchant."))

        active_owners = [
            m
            for m in relevant_memberships
            if m.role == MembershipRole.OWNER and m.status == MembershipStatus.ACTIVE
        ]

        # 4. Role management authority check
        if target_membership.role == MembershipRole.OWNER:
            if actor_membership.role != MembershipRole.OWNER or not can_perform_merchant_action(
                actor_membership, MerchantPermission.TRANSFER_OWNERSHIP
            ):
                raise PermissionDenied(_("You lack permission to delete an owner."))
        else:
            required_perm = _get_management_permission_for_role(target_membership.role)
            if not can_perform_merchant_action(actor_membership, required_perm):
                raise PermissionDenied(_("You lack permission to delete this member."))

        # 5. Sole active owner protection check
        is_active_owner = any(owner.pk == target_membership.pk for owner in active_owners)
        if is_active_owner and len(active_owners) <= 1:
            raise SoleOwnerProtectionError(_("Cannot delete the sole active owner of a merchant."))

        target_membership.delete()


def admin_delete_membership(
    *,
    merchant_id: uuid.UUID,
    target_user: Any,
    admin_user: Any,
) -> None:
    """
    Dedicated platform administrative operation for Django Admin.
    Validates authenticated, active platform staff with 'merchants.delete_merchantmembership' permission.
    Preserves SoleOwnerProtectionError and ownership invariants.
    """
    if (
        not admin_user
        or not admin_user.is_authenticated
        or not admin_user.is_active
        or not admin_user.is_staff
        or not admin_user.has_perm("merchants.delete_merchantmembership")
    ):
        raise PermissionDenied(_("Platform staff deletion permission required."))

    with transaction.atomic():
        # 1. Lock Merchant row first
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # 2. Lock target membership and active owners in deterministic order
        relevant_memberships = list(
            MerchantMembership.objects.select_for_update()
            .filter(merchant=merchant)
            .filter(
                Q(user=target_user) | Q(role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE)
            )
            .order_by("pk")
        )

        target_membership = next(
            (m for m in relevant_memberships if m.user_id == target_user.pk), None
        )
        if not target_membership:
            raise ValidationError(_("Target user does not have a membership in this merchant."))

        active_owners = [
            m
            for m in relevant_memberships
            if m.role == MembershipRole.OWNER and m.status == MembershipStatus.ACTIVE
        ]

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
    if not actor_user:
        raise PermissionDenied(_("Actor user is required."))

    with transaction.atomic():
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)
        try:
            actor_membership = MerchantMembership.objects.select_for_update().get(
                merchant=merchant, user=actor_user
            )
        except MerchantMembership.DoesNotExist as exc:
            raise PermissionDenied(
                _("Requesting user is not a member of this merchant organization.")
            ) from exc

        if not can_perform_merchant_action(
            actor_membership, MerchantPermission.DEACTIVATE_MERCHANT
        ):
            raise PermissionDenied(_("Only an active owner can deactivate a merchant account."))

        merchant.status = MerchantStatus.INACTIVE
        merchant.save(update_fields=["status", "updated_at"])
        return merchant
