import json
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.merchants.choices import BusinessType, MerchantStatus
from apps.merchants.context import ACTIVE_MERCHANT_SESSION_KEY
from apps.merchants.services import create_merchant
from apps.products.choices import AvailabilityMode, Currency, PriceDisplayMode, ProductStatus
from apps.products.forms import ProductForm
from apps.products.models import Product
from apps.products.services import create_product

User = get_user_model()


@pytest.fixture
def owner_user(db):
    return User.objects.create_user(
        email="prod.stageb.owner@example.com",
        password="ValidPassword123!",
        is_verified=True,
        is_active=True,
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email="prod.stageb.other@example.com",
        password="ValidPassword123!",
        is_verified=True,
        is_active=True,
    )


@pytest.fixture
def merchant_alpha(db, owner_user):
    merchant, _ = create_merchant(
        owner_user=owner_user,
        name="Alpha Apparel Corp",
        business_type=BusinessType.RETAIL,
        contact_number="+91 9876543210",
        email="alpha_apparel@example.com",
        address="100 Fashion St",
        city="Mumbai",
        state="Maharashtra",
        pin_code="400001",
    )
    merchant.status = MerchantStatus.ACTIVE
    merchant.save()
    return merchant


@pytest.fixture
def merchant_beta(db, other_user):
    merchant, _ = create_merchant(
        owner_user=other_user,
        name="Beta Boutique Corp",
        business_type=BusinessType.RETAIL,
        contact_number="+91 9876543211",
        email="beta_boutique@example.com",
        address="200 Style Ave",
        city="Bengaluru",
        state="Karnataka",
        pin_code="560001",
    )
    merchant.status = MerchantStatus.ACTIVE
    merchant.save()
    return merchant


def set_active_merchant(client, user, merchant):
    client.force_login(user)
    session = client.session
    session[ACTIVE_MERCHANT_SESSION_KEY] = str(merchant.id)
    session.save()


@pytest.mark.django_db
class TestProductFormStageB:
    """Verifies ProductForm validation for Stage B evolution requirements."""

    def test_form_valid_with_pricing_and_availability(self, merchant_alpha):
        form = ProductForm(
            merchant=merchant_alpha,
            data={
                "name": "Classic Wool Overcoat",
                "price": "199.99",
                "mrp": "299.99",
                "price_display_mode": PriceDisplayMode.SHOW_PRICE,
                "currency": Currency.INR,
                "availability_mode": AvailabilityMode.IN_STOCK,
            },
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["price"] == Decimal("199.99")
        assert form.cleaned_data["mrp"] == Decimal("299.99")
        assert form.cleaned_data["price_display_mode"] == PriceDisplayMode.SHOW_PRICE
        assert form.cleaned_data["availability_mode"] == AvailabilityMode.IN_STOCK
        assert form.cleaned_data["is_available"] is True

    def test_form_rejects_mrp_less_than_price(self, merchant_alpha):
        form = ProductForm(
            merchant=merchant_alpha,
            data={
                "name": "Discounted Coat",
                "price": "200.00",
                "mrp": "150.00",
                "currency": Currency.INR,
            },
        )
        assert not form.is_valid()
        assert "mrp" in form.errors
        assert "cannot be less than selling price" in form.errors["mrp"][0]

    def test_form_rejects_negative_price(self, merchant_alpha):
        form = ProductForm(
            merchant=merchant_alpha,
            data={
                "name": "Invalid Price Item",
                "price": "-10.00",
                "currency": Currency.INR,
            },
        )
        assert not form.is_valid()
        assert "price" in form.errors

    def test_form_rejects_negative_mrp(self, merchant_alpha):
        form = ProductForm(
            merchant=merchant_alpha,
            data={
                "name": "Invalid MRP Item",
                "price": "50.00",
                "mrp": "-20.00",
                "currency": Currency.INR,
            },
        )
        assert not form.is_valid()
        assert "mrp" in form.errors

    def test_form_made_to_order_synchronizes_is_available_true(self, merchant_alpha):
        form = ProductForm(
            merchant=merchant_alpha,
            data={
                "name": "Custom Tailored Suit",
                "availability_mode": AvailabilityMode.MADE_TO_ORDER,
                "currency": Currency.INR,
            },
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["availability_mode"] == AvailabilityMode.MADE_TO_ORDER
        assert form.cleaned_data["is_available"] is True

    def test_form_out_of_stock_synchronizes_is_available_false(self, merchant_alpha):
        form = ProductForm(
            merchant=merchant_alpha,
            data={
                "name": "Sold Out Item",
                "availability_mode": AvailabilityMode.OUT_OF_STOCK,
                "currency": Currency.INR,
            },
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["availability_mode"] == AvailabilityMode.OUT_OF_STOCK
        assert form.cleaned_data["is_available"] is False

    def test_form_legacy_is_available_backward_compatible(self, merchant_alpha):
        # Legacy checkbox checked
        form_on = ProductForm(
            merchant=merchant_alpha,
            data={
                "name": "Legacy Available Item",
                "is_available": "on",
                "currency": Currency.INR,
            },
        )
        assert form_on.is_valid(), form_on.errors
        assert form_on.cleaned_data["availability_mode"] == AvailabilityMode.IN_STOCK
        assert form_on.cleaned_data["is_available"] is True

        # Legacy checkbox unchecked
        form_off = ProductForm(
            merchant=merchant_alpha,
            data={
                "name": "Legacy Unavailable Item",
                "is_available": False,
                "currency": Currency.INR,
            },
        )
        assert form_off.is_valid(), form_off.errors
        assert form_off.cleaned_data["availability_mode"] == AvailabilityMode.OUT_OF_STOCK
        assert form_off.cleaned_data["is_available"] is False

    def test_form_published_product_without_price_in_show_price_mode_rejected(
        self, merchant_alpha, owner_user
    ):
        prod = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Live Published Item",
            price=Decimal("100.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
        )
        prod.status = ProductStatus.PUBLISHED
        prod.save()

        # Attempt to edit published item clearing price while in SHOW_PRICE mode
        form = ProductForm(
            merchant=merchant_alpha,
            product=prod,
            data={
                "name": prod.name,
                "price": "",
                "price_display_mode": PriceDisplayMode.SHOW_PRICE,
                "currency": Currency.INR,
            },
        )
        assert not form.is_valid()
        assert "price" in form.errors
        assert "required when Show Price is selected" in form.errors["price"][0]

    def test_form_published_product_without_price_in_contact_for_price_accepted(
        self, merchant_alpha, owner_user
    ):
        prod = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Live Enquiry Item",
            price=Decimal("100.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
        )
        prod.status = ProductStatus.PUBLISHED
        prod.save()

        form = ProductForm(
            merchant=merchant_alpha,
            product=prod,
            data={
                "name": prod.name,
                "price": "",
                "price_display_mode": PriceDisplayMode.CONTACT_FOR_PRICE,
                "currency": Currency.INR,
            },
        )
        assert form.is_valid(), form.errors

    def test_form_structured_attributes_valid_specifications(self, merchant_alpha):
        structured_payload = {
            "specifications": [
                {"key": "fabric", "label": "Fabric", "type": "text", "value": "Cotton"},
                {"key": "weight", "label": "Weight", "type": "number", "value": 250, "unit": "g"},
                {
                    "key": "fit",
                    "label": "Fit",
                    "type": "single_select",
                    "options": ["Slim", "Regular"],
                    "value": "Slim",
                },
                {
                    "key": "features",
                    "label": "Features",
                    "type": "multi_select",
                    "options": ["Waterproof", "Breathable"],
                    "values": ["Waterproof"],
                },
                {
                    "key": "colors",
                    "label": "Colors",
                    "type": "color",
                    "values": [{"name": "Navy Blue", "hex": "#191970"}],
                },
            ]
        }
        form = ProductForm(
            merchant=merchant_alpha,
            data={
                "name": "High Tech Parka",
                "currency": Currency.INR,
                "attributes_json": json.dumps(structured_payload),
            },
        )
        assert form.is_valid(), form.errors
        assert len(form.cleaned_data["attributes_json"]["specifications"]) == 5

    def test_form_structured_attributes_exceeding_15_rejected(self, merchant_alpha):
        too_many_specs = {
            "specifications": [
                {"key": f"spec_{i:02d}", "label": f"Spec {i}", "type": "text", "value": "Sample"}
                for i in range(16)
            ]
        }
        form = ProductForm(
            merchant=merchant_alpha,
            data={
                "name": "Overloaded Item",
                "currency": Currency.INR,
                "attributes_json": json.dumps(too_many_specs),
            },
        )
        assert not form.is_valid()
        assert "attributes_json" in form.errors
        assert "cannot have more than 15" in form.errors["attributes_json"][0]


@pytest.mark.django_db
class TestProductViewsStageB:
    """Verifies Product creation and editing views with Stage B fields and tenant isolation."""

    def test_create_product_post_with_stage_b_fields(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)

        structured_specs = {
            "specifications": [
                {
                    "key": "material",
                    "label": "Material",
                    "type": "text",
                    "value": "100% Merino Wool",
                },
                {"key": "weight", "label": "Weight", "type": "number", "value": 320, "unit": "gsm"},
                {
                    "key": "color",
                    "label": "Color",
                    "type": "color",
                    "values": [{"name": "Charcoal", "hex": "#36454f"}],
                },
            ]
        }

        payload = {
            "name": "Merino Wool Sweater",
            "slug": "merino-wool-sweater",
            "sku": "MWS-001",
            "description": "Luxurious soft thermal sweater.",
            "price": "120.00",
            "mrp": "180.00",
            "price_display_mode": PriceDisplayMode.SHOW_PRICE,
            "currency": Currency.INR,
            "availability_mode": AvailabilityMode.MADE_TO_ORDER,
            "attributes_json": json.dumps(structured_specs),
        }

        response = client.post(reverse("products:product_create"), data=payload)
        assert response.status_code == 302

        product = Product.objects.get(merchant=merchant_alpha, slug="merino-wool-sweater")
        assert response.url == reverse("products:product_edit", kwargs={"product_id": product.id})
        assert product.name == "Merino Wool Sweater"
        assert product.price == Decimal("120.00")
        assert product.mrp == Decimal("180.00")
        assert product.price_display_mode == PriceDisplayMode.SHOW_PRICE
        assert product.availability_mode == AvailabilityMode.MADE_TO_ORDER
        assert product.is_available is True
        assert len(product.attributes["specifications"]) == 3

    def test_edit_product_get_renders_stage_b_fields(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)

        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Tailored Blazer",
            price=Decimal("250.00"),
            mrp=Decimal("350.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
            availability_mode=AvailabilityMode.MADE_TO_ORDER,
            attributes={
                "specifications": [
                    {"key": "fit", "label": "Fit", "type": "text", "value": "Custom"}
                ]
            },
        )

        response = client.get(reverse("products:product_edit", kwargs={"product_id": product.id}))
        assert response.status_code == 200

        content = response.content.decode()
        assert 'value="250.00"' in content
        assert 'value="350.00"' in content
        assert "MADE_TO_ORDER" in content
        assert "Custom Specifications &amp; Attributes" in content
        assert "specifications" in content

    def test_edit_product_post_updates_stage_b_fields(self, client, owner_user, merchant_alpha):
        set_active_merchant(client, owner_user, merchant_alpha)

        product = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Silk Scarf",
            price=Decimal("45.00"),
            mrp=Decimal("60.00"),
            price_display_mode=PriceDisplayMode.SHOW_PRICE,
            availability_mode=AvailabilityMode.IN_STOCK,
        )

        update_payload = {
            "name": "Silk Scarf Premium",
            "price": "50.00",
            "mrp": "75.00",
            "price_display_mode": PriceDisplayMode.SHOW_PRICE,
            "currency": Currency.INR,
            "availability_mode": AvailabilityMode.OUT_OF_STOCK,
            "attributes_json": json.dumps(
                {
                    "specifications": [
                        {
                            "key": "fabric",
                            "label": "Fabric",
                            "type": "text",
                            "value": "Mulberry Silk",
                        }
                    ]
                }
            ),
        }

        response = client.post(
            reverse("products:product_edit", kwargs={"product_id": product.id}),
            data=update_payload,
        )
        assert response.status_code == 302

        product.refresh_from_db()
        assert product.name == "Silk Scarf Premium"
        assert product.price == Decimal("50.00")
        assert product.mrp == Decimal("75.00")
        assert product.availability_mode == AvailabilityMode.OUT_OF_STOCK
        assert product.is_available is False
        assert product.attributes["specifications"][0]["value"] == "Mulberry Silk"

    def test_tenant_isolation_cannot_access_other_merchant_product(
        self, client, owner_user, other_user, merchant_alpha, merchant_beta
    ):
        # Product owned by Alpha
        prod_alpha = create_product(
            merchant_id=merchant_alpha,
            actor=owner_user,
            name="Alpha Secret Design",
        )

        # User from Beta tries to access Alpha's product
        set_active_merchant(client, other_user, merchant_beta)

        get_resp = client.get(
            reverse("products:product_edit", kwargs={"product_id": prod_alpha.id})
        )
        assert get_resp.status_code == 404

        post_resp = client.post(
            reverse("products:product_edit", kwargs={"product_id": prod_alpha.id}),
            data={"name": "Hacked Name"},
        )
        assert post_resp.status_code == 404
        prod_alpha.refresh_from_db()
        assert prod_alpha.name == "Alpha Secret Design"
