import json
from decimal import Decimal
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.merchants.models import Merchant

from .choices import Currency
from .exceptions import InvalidProductAttributeError, InvalidProductImageError
from .models import Category, Product
from .validators import (
    validate_and_normalize_slug,
    validate_attributes,
    validate_product_image,
)

FORM_CONTROL_CLASS = (
    "w-full px-3 py-2 border border-slate-300 rounded-md shadow-xs "
    "focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm "
    "disabled:bg-slate-50 disabled:text-slate-500 disabled:cursor-not-allowed"
)


class ProductForm(forms.Form):
    """
    Form for creating and editing a Product.
    Category choices are strictly scoped to the active merchant.
    Custom attributes are validated server-side from JSON.
    """

    name = forms.CharField(
        label=_("Product Name"),
        max_length=255,
        min_length=2,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("e.g. Classic Cotton T-Shirt"),
                "autocomplete": "off",
            }
        ),
    )
    slug = forms.CharField(
        label=_("URL Slug (Optional)"),
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("Auto-generated from name if left blank"),
                "autocomplete": "off",
                "spellcheck": "false",
            }
        ),
        help_text=_(
            "Identifier for storefront URL: lowercase letters, numbers, and hyphens. Generated from name if empty."
        ),
    )
    sku = forms.CharField(
        label=_("SKU / Stock Keeping Unit (Optional)"),
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("e.g. TSH-COT-001"),
                "autocomplete": "off",
            }
        ),
        help_text=_("Unique alphanumeric inventory code within your business."),
    )
    description = forms.CharField(
        label=_("Description (Optional)"),
        max_length=5000,
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "rows": 4,
                "placeholder": _("Describe materials, features, sizing, or styling notes..."),
            }
        ),
    )
    price = forms.DecimalField(
        label=_("Price"),
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": "0.00",
                "step": "0.01",
                "min": "0.00",
            }
        ),
        help_text=_("Leave blank if price is on request."),
    )
    currency = forms.ChoiceField(
        label=_("Currency"),
        choices=Currency.choices,
        initial=Currency.INR,
        required=True,
        widget=forms.Select(attrs={"class": FORM_CONTROL_CLASS}),
    )
    is_available = forms.BooleanField(
        label=_("Available for purchase"),
        initial=True,
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            }
        ),
        help_text=_("Uncheck if temporarily out of stock (item remains visible in catalogue)."),
    )
    categories = forms.ModelMultipleChoiceField(
        label=_("Categories"),
        queryset=Category.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(
            attrs={
                "class": "h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            }
        ),
        help_text=_("Select one or more categories for this product."),
    )
    attributes_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    def __init__(
        self,
        *args: Any,
        merchant: Merchant,
        product: Product | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.merchant = merchant
        self.product = product

        # Dynamically scope categories to active merchant
        base_cats = Category.objects.filter(merchant=merchant)
        if product:
            cat_qs = base_cats.filter(
                Q(is_active=True) | Q(id__in=product.categories.values_list("id", flat=True))
            ).order_by("display_order", "name")
            self.fields["categories"].queryset = cat_qs
            if not self.is_bound:
                self.fields["categories"].initial = list(
                    product.categories.values_list("id", flat=True)
                )
                if product.attributes:
                    self.fields["attributes_json"].initial = json.dumps(product.attributes)
        else:
            self.fields["categories"].queryset = base_cats.filter(is_active=True).order_by(
                "display_order", "name"
            )

    def clean_name(self) -> str:
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise ValidationError(_("Product name cannot be empty."))
        return name

    def clean_slug(self) -> str | None:
        slug = self.cleaned_data.get("slug", "").strip()
        if not slug:
            return None
        return validate_and_normalize_slug(slug, max_length=255)

    def clean_sku(self) -> str | None:
        sku = self.cleaned_data.get("sku", "").strip()
        return sku if sku else None

    def clean_attributes_json(self) -> dict[str, Any]:
        raw_json = self.cleaned_data.get("attributes_json", "").strip()
        if not raw_json or raw_json in ("{}", "null", "undefined"):
            return {}

        try:
            parsed = json.loads(raw_json)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValidationError(
                _("Custom attributes must be valid JSON: %(error)s") % {"error": str(exc)}
            ) from exc

        try:
            return validate_attributes(parsed)
        except InvalidProductAttributeError as exc:
            raise ValidationError(str(exc)) from exc


class CategoryForm(forms.Form):
    """
    Form for creating and editing a Category.
    """

    name = forms.CharField(
        label=_("Category Name"),
        max_length=255,
        min_length=2,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("e.g. Footwear"),
                "autocomplete": "off",
            }
        ),
    )
    slug = forms.CharField(
        label=_("URL Slug (Optional)"),
        max_length=160,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("Auto-generated from name if left blank"),
                "autocomplete": "off",
                "spellcheck": "false",
            }
        ),
        help_text=_(
            "Lowercase letters, numbers, and hyphens. Generated automatically from name if left blank."
        ),
    )
    description = forms.CharField(
        label=_("Description (Optional)"),
        max_length=1000,
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "rows": 3,
                "placeholder": _("Optional category description for customers..."),
            }
        ),
    )
    image = forms.FileField(
        label=_("Category Image (Max 5 MB, JPEG/PNG/WebP)"),
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": (
                    "block w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 "
                    "file:rounded-md file:border-0 file:text-xs file:font-semibold "
                    "file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 "
                    "cursor-pointer focus:outline-none"
                ),
                "accept": "image/jpeg,image/png,image/webp",
            }
        ),
    )
    clear_image = forms.BooleanField(
        label=_("Remove category image"),
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            }
        ),
    )
    display_order = forms.IntegerField(
        label=_("Display Order"),
        min_value=0,
        initial=0,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "min": "0",
                "placeholder": "0",
            }
        ),
        help_text=_("Lower numbers appear first in lists and menus (0 is highest priority)."),
    )
    is_active = forms.BooleanField(
        label=_("Active in catalogue"),
        initial=True,
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            }
        ),
        help_text=_("Active categories appear on your storefront and in filter menus."),
    )

    def __init__(
        self,
        *args: Any,
        merchant: Merchant | None = None,
        category: Category | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.merchant = merchant
        self.category = category

    def clean_name(self) -> str:
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise ValidationError(_("Category name cannot be empty."))
        return name

    def clean_slug(self) -> str | None:
        slug = self.cleaned_data.get("slug", "").strip()
        if not slug:
            return None
        return validate_and_normalize_slug(slug, max_length=160)

    def clean_image(self) -> Any:
        image = self.cleaned_data.get("image")
        if image:
            try:
                validate_product_image(image)
            except InvalidProductImageError as exc:
                raise ValidationError(str(exc)) from exc
        return image


class ProductImageUploadForm(forms.Form):
    """
    Form for uploading an image to a product's gallery.
    """

    image = forms.FileField(
        label=_("Product Image (Max 5 MB, JPEG/PNG/WebP)"),
        required=True,
        widget=forms.FileInput(
            attrs={
                "class": (
                    "block w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 "
                    "file:rounded-md file:border-0 file:text-xs file:font-semibold "
                    "file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 "
                    "cursor-pointer focus:outline-none"
                ),
                "accept": "image/jpeg,image/png,image/webp",
            }
        ),
    )
    alt_text = forms.CharField(
        label=_("Alt Text / Image Description (Optional)"),
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("e.g. Front view of classic cotton t-shirt in white"),
            }
        ),
        help_text=_("Accessible description of the image for screen readers and search engines."),
    )
    is_primary = forms.BooleanField(
        label=_("Set as primary thumbnail"),
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            }
        ),
    )
    display_order = forms.IntegerField(
        label=_("Display Order"),
        min_value=0,
        initial=0,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "min": "0",
                "placeholder": "0",
            }
        ),
    )

    def clean_image(self) -> Any:
        image = self.cleaned_data.get("image")
        if image:
            try:
                validate_product_image(image)
            except InvalidProductImageError as exc:
                raise ValidationError(str(exc)) from exc
        return image
