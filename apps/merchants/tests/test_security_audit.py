import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError

from apps.merchants.choices import MembershipRole, MembershipStatus
from apps.merchants.exceptions import MerchantPermissionDeniedError, SoleOwnerProtectionError
from apps.merchants.models import MerchantMembership
from apps.merchants.selectors import get_merchant_member, get_merchant_members
from apps.merchants.services import (
    add_member_to_merchant,
    admin_delete_membership,
    change_membership_role,
    create_merchant,
    deactivate_merchant,
    delete_membership,
    update_membership_status,
)

User = get_user_model()


@pytest.fixture
def alpha_owner(db):
    return User.objects.create_user(
        email="alpha.owner@example.com",
        password="Password123!",
        is_verified=True,
    )


@pytest.fixture
def alpha_admin_1(db):
    return User.objects.create_user(
        email="alpha.admin1@example.com",
        password="Password123!",
        is_verified=True,
    )


@pytest.fixture
def alpha_admin_2(db):
    return User.objects.create_user(
        email="alpha.admin2@example.com",
        password="Password123!",
        is_verified=True,
    )


@pytest.fixture
def alpha_manager(db):
    return User.objects.create_user(
        email="alpha.manager@example.com",
        password="Password123!",
        is_verified=True,
    )


@pytest.fixture
def alpha_staff(db):
    return User.objects.create_user(
        email="alpha.staff@example.com",
        password="Password123!",
        is_verified=True,
    )


@pytest.fixture
def beta_owner(db):
    return User.objects.create_user(
        email="beta.owner@example.com",
        password="Password123!",
        is_verified=True,
    )


@pytest.fixture
def beta_staff(db):
    return User.objects.create_user(
        email="beta.staff@example.com",
        password="Password123!",
        is_verified=True,
    )


@pytest.fixture
def unaffiliated_user(db):
    return User.objects.create_user(
        email="unaffiliated@example.com",
        password="Password123!",
        is_verified=True,
    )


@pytest.fixture
def merchant_alpha(db, alpha_owner, alpha_admin_1, alpha_admin_2, alpha_manager, alpha_staff):
    merchant, _ = create_merchant(
        owner_user=alpha_owner,
        name="Alpha Corp",
        email="alpha@example.com",
        contact_number="1111111111",
        address="1 Alpha Way",
        city="Mumbai",
        state="Maharashtra",
        pin_code="400001",
    )
    add_member_to_merchant(
        merchant.id,
        actor_user=alpha_owner,
        target_user=alpha_admin_1,
        role=MembershipRole.ADMIN,
    )
    add_member_to_merchant(
        merchant.id,
        actor_user=alpha_owner,
        target_user=alpha_admin_2,
        role=MembershipRole.ADMIN,
    )
    add_member_to_merchant(
        merchant.id,
        actor_user=alpha_owner,
        target_user=alpha_manager,
        role=MembershipRole.MANAGER,
    )
    add_member_to_merchant(
        merchant.id,
        actor_user=alpha_owner,
        target_user=alpha_staff,
        role=MembershipRole.STAFF,
    )
    return merchant


@pytest.fixture
def merchant_beta(db, beta_owner, beta_staff):
    merchant, _ = create_merchant(
        owner_user=beta_owner,
        name="Beta Industries",
        email="beta@example.com",
        contact_number="2222222222",
        address="2 Beta Blvd",
        city="Pune",
        state="Maharashtra",
        pin_code="411001",
    )
    add_member_to_merchant(
        merchant.id,
        actor_user=beta_owner,
        target_user=beta_staff,
        role=MembershipRole.STAFF,
    )
    return merchant


@pytest.mark.django_db
class TestTenantMutationSecurity:
    """Rigorous audit tests verifying cross-tenant isolation and intra-tenant role hierarchies."""

    def test_cross_tenant_role_modification_is_blocked(
        self, merchant_alpha, merchant_beta, alpha_owner, beta_staff
    ):
        """Alpha owner cannot modify the role of Beta staff within Alpha merchant context."""
        with pytest.raises(
            ValidationError,
            match="Target user does not have a membership in this merchant",
        ):
            change_membership_role(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_owner,
                target_user=beta_staff,
                new_role=MembershipRole.MANAGER,
            )

    def test_cross_tenant_role_modification_as_foreign_actor_is_blocked(
        self, merchant_beta, alpha_owner, beta_staff
    ):
        """Alpha owner cannot invoke role changes on Beta merchant where they hold no membership."""
        with pytest.raises(
            PermissionDenied,
            match="Requesting user is not a member of this merchant organization",
        ):
            change_membership_role(
                merchant_id=merchant_beta.id,
                actor_user=alpha_owner,
                target_user=beta_staff,
                new_role=MembershipRole.MANAGER,
            )

    def test_cross_tenant_status_update_is_blocked(
        self, merchant_alpha, merchant_beta, alpha_owner, beta_staff
    ):
        """Cross-tenant status suspension/revocation is rejected."""
        # Target doesn't belong to Alpha
        with pytest.raises(
            ValidationError,
            match="Target user does not have a membership in this merchant",
        ):
            update_membership_status(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_owner,
                target_user=beta_staff,
                new_status=MembershipStatus.SUSPENDED,
            )

        # Actor doesn't belong to Beta
        with pytest.raises(
            PermissionDenied,
            match="Requesting user is not a member of this merchant organization",
        ):
            update_membership_status(
                merchant_id=merchant_beta.id,
                actor_user=alpha_owner,
                target_user=beta_staff,
                new_status=MembershipStatus.SUSPENDED,
            )

    def test_cross_tenant_deletion_is_blocked(
        self, merchant_alpha, merchant_beta, alpha_owner, beta_staff
    ):
        """Cross-tenant deletion is rejected."""
        with pytest.raises(
            ValidationError,
            match="Target user does not have a membership in this merchant",
        ):
            delete_membership(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_owner,
                target_user=beta_staff,
            )

        with pytest.raises(
            PermissionDenied,
            match="Requesting user is not a member of this merchant organization",
        ):
            delete_membership(
                merchant_id=merchant_beta.id,
                actor_user=alpha_owner,
                target_user=beta_staff,
            )

    def test_admin_cannot_modify_peer_admin_role(
        self, merchant_alpha, alpha_admin_1, alpha_admin_2
    ):
        """An ADMIN cannot demote or alter another ADMIN's role (peer protection)."""
        with pytest.raises(
            PermissionDenied,
            match="You lack permission to modify this member's role",
        ):
            change_membership_role(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_admin_1,
                target_user=alpha_admin_2,
                new_role=MembershipRole.MANAGER,
            )

    def test_admin_cannot_promote_to_admin(self, merchant_alpha, alpha_admin_1, alpha_staff):
        """An ADMIN cannot promote another member to ADMIN (requires MANAGE_ADMINS)."""
        with pytest.raises(
            PermissionDenied,
            match="You lack permission to assign the requested role",
        ):
            change_membership_role(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_admin_1,
                target_user=alpha_staff,
                new_role=MembershipRole.ADMIN,
            )

    def test_admin_cannot_modify_or_delete_owner(self, merchant_alpha, alpha_admin_1, alpha_owner):
        """An ADMIN cannot modify role, status, or delete an OWNER."""
        with pytest.raises(
            PermissionDenied,
            match="You lack permission to modify an owner's role",
        ):
            change_membership_role(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_admin_1,
                target_user=alpha_owner,
                new_role=MembershipRole.ADMIN,
            )

        with pytest.raises(
            PermissionDenied,
            match="You lack permission to modify an owner's status",
        ):
            update_membership_status(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_admin_1,
                target_user=alpha_owner,
                new_status=MembershipStatus.SUSPENDED,
            )

        with pytest.raises(
            PermissionDenied,
            match="You lack permission to delete an owner",
        ):
            delete_membership(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_admin_1,
                target_user=alpha_owner,
            )

    def test_admin_cannot_modify_status_or_delete_peer_admin(
        self, merchant_alpha, alpha_admin_1, alpha_admin_2
    ):
        """An ADMIN cannot suspend or delete another ADMIN."""
        with pytest.raises(
            PermissionDenied,
            match="You lack permission to modify the status of this member",
        ):
            update_membership_status(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_admin_1,
                target_user=alpha_admin_2,
                new_status=MembershipStatus.SUSPENDED,
            )

        with pytest.raises(
            PermissionDenied,
            match="You lack permission to delete this member",
        ):
            delete_membership(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_admin_1,
                target_user=alpha_admin_2,
            )

    def test_admin_can_manage_managers_and_staff(
        self, merchant_alpha, alpha_admin_1, alpha_manager, alpha_staff
    ):
        """An ADMIN holds MANAGE_MANAGERS and MANAGE_STAFF and can manage their lifecycle."""
        # Promote STAFF to MANAGER
        promoted = change_membership_role(
            merchant_id=merchant_alpha.id,
            actor_user=alpha_admin_1,
            target_user=alpha_staff,
            new_role=MembershipRole.MANAGER,
        )
        assert promoted.role == MembershipRole.MANAGER

        # Suspend the newly promoted manager
        suspended = update_membership_status(
            merchant_id=merchant_alpha.id,
            actor_user=alpha_admin_1,
            target_user=alpha_staff,
            new_status=MembershipStatus.SUSPENDED,
        )
        assert suspended.status == MembershipStatus.SUSPENDED

        # Reinstate back to ACTIVE
        active = update_membership_status(
            merchant_id=merchant_alpha.id,
            actor_user=alpha_admin_1,
            target_user=alpha_staff,
            new_status=MembershipStatus.ACTIVE,
        )
        assert active.status == MembershipStatus.ACTIVE

        # Delete the other manager
        delete_membership(
            merchant_id=merchant_alpha.id,
            actor_user=alpha_admin_1,
            target_user=alpha_manager,
        )
        assert not MerchantMembership.objects.filter(
            merchant=merchant_alpha, user=alpha_manager
        ).exists()

    def test_manager_cannot_manage_admins_or_managers(
        self, merchant_alpha, alpha_manager, alpha_admin_1, alpha_staff
    ):
        """A MANAGER lacks MANAGE_ADMINS and MANAGE_MANAGERS."""
        with pytest.raises(PermissionDenied):
            change_membership_role(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_manager,
                target_user=alpha_admin_1,
                new_role=MembershipRole.STAFF,
            )

        # Cannot promote staff to manager
        with pytest.raises(
            PermissionDenied,
            match="You lack permission to assign the requested role",
        ):
            change_membership_role(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_manager,
                target_user=alpha_staff,
                new_role=MembershipRole.MANAGER,
            )

    def test_manager_can_manage_staff(self, merchant_alpha, alpha_manager, alpha_staff):
        """A MANAGER has MANAGE_STAFF and can suspend and delete staff."""
        suspended = update_membership_status(
            merchant_id=merchant_alpha.id,
            actor_user=alpha_manager,
            target_user=alpha_staff,
            new_status=MembershipStatus.SUSPENDED,
        )
        assert suspended.status == MembershipStatus.SUSPENDED

        delete_membership(
            merchant_id=merchant_alpha.id,
            actor_user=alpha_manager,
            target_user=alpha_staff,
        )
        assert not MerchantMembership.objects.filter(
            merchant=merchant_alpha, user=alpha_staff
        ).exists()

    def test_staff_cannot_perform_mutations(
        self, merchant_alpha, alpha_staff, alpha_manager, unaffiliated_user
    ):
        """STAFF role lacks all management capabilities."""
        with pytest.raises(MerchantPermissionDeniedError):
            add_member_to_merchant(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_staff,
                target_user=unaffiliated_user,
                role=MembershipRole.STAFF,
            )

        with pytest.raises(PermissionDenied):
            change_membership_role(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_staff,
                target_user=alpha_manager,
                new_role=MembershipRole.STAFF,
            )

        with pytest.raises(PermissionDenied):
            update_membership_status(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_staff,
                target_user=alpha_manager,
                new_status=MembershipStatus.SUSPENDED,
            )

        with pytest.raises(PermissionDenied):
            delete_membership(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_staff,
                target_user=alpha_manager,
            )

    def test_non_member_actor_raises_permission_denied(
        self, merchant_alpha, unaffiliated_user, alpha_staff
    ):
        """An actor not in the merchant gets PermissionDenied, not an unhandled 500 DoesNotExist."""
        with pytest.raises(
            PermissionDenied,
            match="Requesting user is not a member of this merchant organization",
        ):
            add_member_to_merchant(
                merchant_id=merchant_alpha.id,
                actor_user=unaffiliated_user,
                target_user=unaffiliated_user,
            )

        with pytest.raises(
            PermissionDenied,
            match="Requesting user is not a member of this merchant organization",
        ):
            change_membership_role(
                merchant_id=merchant_alpha.id,
                actor_user=unaffiliated_user,
                target_user=alpha_staff,
                new_role=MembershipRole.MANAGER,
            )

        with pytest.raises(
            PermissionDenied,
            match="Requesting user is not a member of this merchant organization",
        ):
            update_membership_status(
                merchant_id=merchant_alpha.id,
                actor_user=unaffiliated_user,
                target_user=alpha_staff,
                new_status=MembershipStatus.SUSPENDED,
            )

        with pytest.raises(
            PermissionDenied,
            match="Requesting user is not a member of this merchant organization",
        ):
            delete_membership(
                merchant_id=merchant_alpha.id,
                actor_user=unaffiliated_user,
                target_user=alpha_staff,
            )

        with pytest.raises(
            PermissionDenied,
            match="Requesting user is not a member of this merchant organization",
        ):
            deactivate_merchant(
                merchant_id=merchant_alpha.id,
                actor_user=unaffiliated_user,
            )

    def test_inactive_actor_membership_raises_permission_denied(
        self, merchant_alpha, alpha_owner, alpha_admin_1, alpha_staff
    ):
        """A suspended actor cannot perform any mutation."""
        # Suspend admin 1
        update_membership_status(
            merchant_id=merchant_alpha.id,
            actor_user=alpha_owner,
            target_user=alpha_admin_1,
            new_status=MembershipStatus.SUSPENDED,
        )

        with pytest.raises(PermissionDenied, match="Requesting user membership is not active"):
            change_membership_role(
                merchant_id=merchant_alpha.id,
                actor_user=alpha_admin_1,
                target_user=alpha_staff,
                new_role=MembershipRole.MANAGER,
            )


@pytest.mark.django_db
class TestAdminDeleteMembershipSecurity:
    """Security verification for platform administrative deletion service."""

    @pytest.fixture
    def platform_staff(self, db):
        staff = User.objects.create_user(
            email="platform.staff@mycatalogue.internal",
            password="StaffPassword123!",
            is_staff=True,
            is_verified=True,
        )
        content_type = ContentType.objects.get_for_model(MerchantMembership)
        perm = Permission.objects.get(
            content_type=content_type, codename="delete_merchantmembership"
        )
        staff.user_permissions.add(perm)
        return staff

    def test_admin_delete_requires_authenticated_staff_with_permission(
        self, merchant_alpha, alpha_staff, alpha_owner
    ):
        """Anonymous, regular user, or staff without permission cannot call admin_delete_membership."""
        # Anonymous / None user
        with pytest.raises(PermissionDenied, match="Platform staff deletion permission required"):
            admin_delete_membership(
                merchant_id=merchant_alpha.id,
                target_user=alpha_staff,
                admin_user=None,
            )

        # Non-staff user
        with pytest.raises(PermissionDenied, match="Platform staff deletion permission required"):
            admin_delete_membership(
                merchant_id=merchant_alpha.id,
                target_user=alpha_staff,
                admin_user=alpha_owner,
            )

        # Staff user without delete permission
        unprivileged_staff = User.objects.create_user(
            email="unprivileged.staff@mycatalogue.internal",
            password="StaffPassword123!",
            is_staff=True,
            is_verified=True,
        )
        with pytest.raises(PermissionDenied, match="Platform staff deletion permission required"):
            admin_delete_membership(
                merchant_id=merchant_alpha.id,
                target_user=alpha_staff,
                admin_user=unprivileged_staff,
            )

    def test_admin_delete_preserves_sole_owner_protection(
        self, merchant_alpha, alpha_owner, platform_staff
    ):
        """Platform staff cannot delete the sole active owner of a merchant."""
        with pytest.raises(
            SoleOwnerProtectionError,
            match="Cannot delete the sole active owner of a merchant",
        ):
            admin_delete_membership(
                merchant_id=merchant_alpha.id,
                target_user=alpha_owner,
                admin_user=platform_staff,
            )

    def test_admin_delete_allows_deleting_non_sole_owner(
        self, merchant_alpha, alpha_staff, platform_staff
    ):
        """Platform staff with permission can delete non-owner members."""
        admin_delete_membership(
            merchant_id=merchant_alpha.id,
            target_user=alpha_staff,
            admin_user=platform_staff,
        )
        assert not MerchantMembership.objects.filter(
            merchant=merchant_alpha, user=alpha_staff
        ).exists()


@pytest.mark.django_db
class TestMerchantSelectorsTenantScoping:
    """Security verification for merchant-scoped selectors preventing IDOR."""

    def test_get_merchant_member_scopes_strictly_to_merchant(
        self, merchant_alpha, merchant_beta, alpha_staff, beta_staff
    ):
        """get_merchant_member returns None for a foreign tenant member even if the user exists."""
        # beta_staff queried within merchant_alpha -> returns None (IDOR prevented)
        result = get_merchant_member(merchant=merchant_alpha, user_id=beta_staff)
        assert result is None

        # alpha_staff queried within merchant_alpha -> returns membership
        result_valid = get_merchant_member(merchant=merchant_alpha, user_id=alpha_staff)
        assert result_valid is not None
        assert result_valid.user == alpha_staff
        assert result_valid.merchant == merchant_alpha

    def test_get_merchant_members_scopes_strictly_to_merchant(self, merchant_alpha, merchant_beta):
        """get_merchant_members returns only members of the specified merchant."""
        alpha_members = get_merchant_members(merchant=merchant_alpha)
        beta_members = get_merchant_members(merchant=merchant_beta)

        alpha_user_emails = {m.user.email for m in alpha_members}
        beta_user_emails = {m.user.email for m in beta_members}

        # Sets must be completely disjoint
        assert alpha_user_emails.isdisjoint(beta_user_emails)
        assert "beta.staff@example.com" not in alpha_user_emails
        assert "alpha.staff@example.com" not in beta_user_emails
