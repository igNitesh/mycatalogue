from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.products.choices import AvailabilityMode, PriceDisplayMode, ProductStatus
from apps.products.services import (
    create_product,
    publish_product,
    update_product_profile,
)


@pytest.mark.django_db
class TestAvailabilitySynchronizationTask013:
    """Verifies deterministic write-path synchronization between availability_mode and is_available."""

    def test_create_product_defaults_to_in_stock_and_available(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Default Product",
        )
        assert product.availability_mode == AvailabilityMode.IN_STOCK
        assert product.is_available is True

    def test_create_product_with_availability_mode(self, merchant_alpha, owner_user):
        p_oos = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="OOS Product",
            availability_mode=AvailabilityMode.OUT_OF_STOCK,
        )
        assert p_oos.availability_mode == AvailabilityMode.OUT_OF_STOCK
        assert p_oos.is_available is False

        p_mto = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="MTO Product",
            availability_mode=AvailabilityMode.MADE_TO_ORDER,
        )
        assert p_mto.availability_mode == AvailabilityMode.MADE_TO_ORDER
        assert p_mto.is_available is True

    def test_create_product_with_legacy_is_available(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Legacy False Product",
            is_available=False,
        )
        assert product.is_available is False
        assert product.availability_mode == AvailabilityMode.OUT_OF_STOCK

    def test_create_product_with_contradictory_parameters_raises(self, merchant_alpha, owner_user):
        with pytest.raises(ValidationError, match="Contradictory availability values"):
            create_product(
                merchant_id=merchant_alpha,
                actor=owner_user,
                name="Conflict Product",
                availability_mode=AvailabilityMode.OUT_OF_STOCK,
                is_available=True,
            )

    def test_save_update_fields_availability_mode_syncs_is_available(
        self, merchant_alpha, owner_user
    ):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Sync Test 1",
            availability_mode=AvailabilityMode.IN_STOCK,
        )
        product.availability_mode = AvailabilityMode.OUT_OF_STOCK
        product.save(update_fields=["availability_mode"])

        product.refresh_from_db()
        assert product.availability_mode == AvailabilityMode.OUT_OF_STOCK
        assert product.is_available is False

    def test_save_update_fields_is_available_syncs_availability_mode(
        self, merchant_alpha, owner_user
    ):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Sync Test 2",
            availability_mode=AvailabilityMode.IN_STOCK,
        )
        product.is_available = False
        product.save(update_fields=["is_available"])

        product.refresh_from_db()
        assert product.is_available is False
        assert product.availability_mode == AvailabilityMode.OUT_OF_STOCK

    def test_save_update_fields_both_contradictory_raises(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Sync Test 3",
        )
        product.availability_mode = AvailabilityMode.OUT_OF_STOCK
        product.is_available = True
        with pytest.raises(ValidationError, match="Contradictory availability values"):
            product.save(update_fields=["availability_mode", "is_available"])

    def test_save_full_instance_tracks_mutations(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Sync Test 4",
        )
        # Mutate only is_available
        product.is_available = False
        product.save()
        product.refresh_from_db()
        assert product.is_available is False
        assert product.availability_mode == AvailabilityMode.OUT_OF_STOCK

        # Mutate only availability_mode to MADE_TO_ORDER
        product.availability_mode = AvailabilityMode.MADE_TO_ORDER
        product.save()
        product.refresh_from_db()
        assert product.availability_mode == AvailabilityMode.MADE_TO_ORDER
        assert product.is_available is True

    def test_save_full_instance_contradictory_mutation_raises(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Sync Test 5",
        )
        product.availability_mode = AvailabilityMode.OUT_OF_STOCK
        product.is_available = True
        with pytest.raises(ValidationError, match="Contradictory availability update"):
            product.save()

    def test_update_product_profile_services_sync(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Sync Test 6",
        )
        # Update mode via service
        updated = update_product_profile(
            product_id=product.id,
            actor=owner_user,
            availability_mode=AvailabilityMode.OUT_OF_STOCK,
        )
        assert updated.availability_mode == AvailabilityMode.OUT_OF_STOCK
        assert updated.is_available is False

        # Update legacy is_available via service
        updated2 = update_product_profile(
            product_id=product.id,
            actor=owner_user,
            is_available=True,
        )
        assert updated2.is_available is True
        assert updated2.availability_mode == AvailabilityMode.IN_STOCK

        # Contradictory update via service raises
        with pytest.raises(ValidationError, match="Contradictory availability values"):
            update_product_profile(
                product_id=product.id,
                actor=owner_user,
                availability_mode=AvailabilityMode.OUT_OF_STOCK,
                is_available=True,
            )


@pytest.mark.django_db
class TestPricingAndDisplayModesTask013:
    """Verifies dual pricing, discount calculation, and PriceDisplayMode invariants."""

    def test_discount_percentage_calculation_round_half_up(self, merchant_alpha, owner_user):
        # MRP 1000, Price 750 -> 25% discount
        p1 = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Item 25",
            price=Decimal("750.00"),
            mrp=Decimal("1000.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
        )
        assert p1.discount_percentage == 25

        # MRP 999, Price 749 -> ((999 - 749) / 999) * 100 = 25.025... -> 25%
        p2 = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Item 25.025",
            price=Decimal("749.00"),
            mrp=Decimal("999.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
        )
        assert p2.discount_percentage == 25

        # MRP 300, Price 200 -> 33.333% -> 33%
        p3 = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Item 33.3",
            price=Decimal("200.00"),
            mrp=Decimal("300.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
        )
        assert p3.discount_percentage == 33

        # MRP 300, Price 100 -> 66.666% -> 67% (Round Half Up)
        p4 = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Item 66.6",
            price=Decimal("100.00"),
            mrp=Decimal("300.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
        )
        assert p4.discount_percentage == 67

    def test_discount_percentage_none_conditions(self, merchant_alpha, owner_user):
        # Missing MRP
        p1 = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="No MRP",
            price=Decimal("500.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
        )
        assert p1.discount_percentage is None

        # MRP equal to Price
        p2 = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Equal MRP",
            price=Decimal("500.00"),
            mrp=Decimal("500.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
        )
        assert p2.discount_percentage is None

        # In CONTACT_FOR_PRICE mode
        p3 = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Hidden Price",
            price=Decimal("500.00"),
            mrp=Decimal("1000.00"),
            price_display_mode=PriceDisplayMode.CONTACT_FOR_PRICE,
        )
        assert p3.discount_percentage is None

    def test_mrp_less_than_price_raises_validation_error(self, merchant_alpha, owner_user):
        with pytest.raises(ValidationError):
            create_product(
                merchant_id=merchant_alpha,
                actor=owner_user,
                name="Invalid MRP",
                price=Decimal("500.00"),
                mrp=Decimal("400.00"),
            )

    def test_publish_product_requires_price_in_show_price_mode(self, merchant_alpha, owner_user):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Unpriced Show",
            price=None,
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
        )
        with pytest.raises(
            ValidationError, match="selling price is required when Show Price is selected"
        ):
            publish_product(product_id=product.id, actor=owner_user)

    def test_publish_product_succeeds_in_contact_for_price_mode_without_price(
        self, merchant_alpha, owner_user
    ):
        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Bespoke Suit",
            price=None,
            price_display_mode=PriceDisplayMode.CONTACT_FOR_PRICE,
        )
        published = publish_product(product_id=product.id, actor=owner_user)
        assert published.status == ProductStatus.PUBLISHED
        assert published.price_display_mode == PriceDisplayMode.CONTACT_FOR_PRICE
