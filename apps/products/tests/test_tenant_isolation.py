import pytest
from django.db import transaction

from apps.merchants.choices import MerchantStatus
from apps.products.exceptions import (
    CrossTenantAssignmentError,
    ProductPermissionDeniedError,
)
from apps.products.models import Category, Product, ProductCategory
from apps.products.services import (
    archive_product,
    assign_product_categories,
    create_product,
    update_category,
    update_product_profile,
)


@pytest.mark.django_db
class TestCrossTenantCategoryProtection:
    """
    Critical security test suite verifying that products and categories
    belonging to different merchants CANNOT be associated under any circumstance.
    """

    def test_direct_through_model_creation_blocked(self, merchant_alpha, merchant_beta):
        p_alpha = Product.objects.create(
            merchant=merchant_alpha,
            name="Alpha Product",
            slug="alpha-product",
        )
        c_beta = Category.objects.create(
            merchant=merchant_beta,
            name="Beta Category",
            slug="beta-category",
        )

        with pytest.raises(CrossTenantAssignmentError):
            ProductCategory.objects.create(product=p_alpha, category=c_beta)

    def test_through_model_save_and_clean_blocked(self, merchant_alpha, merchant_beta):
        p_alpha = Product.objects.create(
            merchant=merchant_alpha,
            name="Alpha Product",
            slug="alpha-product",
        )
        c_beta = Category.objects.create(
            merchant=merchant_beta,
            name="Beta Category",
            slug="beta-category",
        )

        link = ProductCategory(product=p_alpha, category=c_beta)
        with pytest.raises(CrossTenantAssignmentError):
            link.clean()

        with pytest.raises(CrossTenantAssignmentError):
            link.save()

    def test_m2m_add_bypassing_service_blocked(self, merchant_alpha, merchant_beta):
        p_alpha = Product.objects.create(
            merchant=merchant_alpha,
            name="Alpha Product",
            slug="alpha-product",
        )
        c_beta = Category.objects.create(
            merchant=merchant_beta,
            name="Beta Category",
            slug="beta-category",
        )

        with pytest.raises(CrossTenantAssignmentError):
            with transaction.atomic():
                p_alpha.categories.add(c_beta)

        assert p_alpha.categories.count() == 0

    def test_bulk_service_assignment_with_mixed_tenants_rejected_atomically(
        self, merchant_alpha, merchant_beta, owner_user
    ):
        p_alpha = Product.objects.create(
            merchant=merchant_alpha,
            name="Alpha Goods",
            slug="alpha-goods",
        )
        c_alpha1 = Category.objects.create(
            merchant=merchant_alpha,
            name="Alpha Cat 1",
            slug="alpha-cat-1",
        )
        c_beta1 = Category.objects.create(
            merchant=merchant_beta,
            name="Beta Cat 1",
            slug="beta-cat-1",
        )

        # Assignment containing one valid alpha category and one foreign beta category
        with pytest.raises(CrossTenantAssignmentError):
            assign_product_categories(
                product_id=p_alpha.id,
                actor=owner_user,
                category_ids=[c_alpha1.id, c_beta1.id],
            )

        # Atomic rollback: c_alpha1 must NOT have been assigned
        assert p_alpha.categories.count() == 0


@pytest.mark.django_db
class TestTenantMutationAuthorization:
    """Verifies that actors cannot mutate catalogue records across tenant boundaries."""

    def test_user_cannot_mutate_another_merchant_product(
        self, merchant_alpha, merchant_beta, owner_user
    ):
        p_beta = Product.objects.create(
            merchant=merchant_beta,
            name="Beta Exclusive",
            slug="beta-exclusive",
        )

        # Alpha's owner attempts to update Beta's product
        with pytest.raises(ProductPermissionDeniedError):
            update_product_profile(
                product_id=p_beta.id,
                actor=owner_user,
                name="Tampered Name",
            )

        with pytest.raises(ProductPermissionDeniedError):
            archive_product(
                product_id=p_beta.id,
                actor=owner_user,
            )

    def test_user_cannot_mutate_another_merchant_category(
        self, merchant_alpha, merchant_beta, owner_user
    ):
        c_beta = Category.objects.create(
            merchant=merchant_beta,
            name="Beta Exclusive Cat",
            slug="beta-exclusive-cat",
        )

        with pytest.raises(ProductPermissionDeniedError):
            update_category(
                category_id=c_beta.id,
                actor=owner_user,
                name="Tampered Category",
            )


@pytest.mark.django_db
class TestRoleAndLifecyclePermissions:
    """Verifies role hierarchy (OWNER, ADMIN, MANAGER vs STAFF) and lifecycle gates."""

    def test_owner_admin_manager_permitted_staff_denied(
        self, merchant_alpha, owner_user, admin_user, manager_user, staff_user
    ):
        # Owner can create
        p1 = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Owner Product",
        )
        assert p1.id

        # Admin can create
        p2 = create_product(
            merchant_id=merchant_alpha,
            actor=admin_user,
            name="Admin Product",
        )
        assert p2.id

        # Manager can create
        p3 = create_product(
            merchant_id=merchant_alpha,
            actor=manager_user,
            name="Manager Product",
        )
        assert p3.id

        # Staff is strictly denied
        with pytest.raises(ProductPermissionDeniedError):
            create_product(
                merchant_id=merchant_alpha,
                actor=staff_user,
                name="Staff Product",
            )

    def test_pending_merchant_allows_onboarding_catalogue_setup(self, merchant_alpha, owner_user):
        merchant_alpha.status = MerchantStatus.PENDING
        merchant_alpha.save()

        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Pending Merchant Product",
        )
        assert product.id is not None

    def test_suspended_and_inactive_merchant_blocks_mutations(self, merchant_alpha, owner_user):
        # Suspended
        merchant_alpha.status = MerchantStatus.SUSPENDED
        merchant_alpha.save()

        with pytest.raises(ProductPermissionDeniedError):
            create_product(
                merchant_id=merchant_alpha,
                actor=owner_user,
                name="Suspended Attempt",
            )

        # Inactive
        merchant_alpha.status = MerchantStatus.INACTIVE
        merchant_alpha.save()

        with pytest.raises(ProductPermissionDeniedError):
            create_product(
                merchant_id=merchant_alpha,
                actor=owner_user,
                name="Inactive Attempt",
            )
