import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .choices import BusinessType

PHONE_REGEX = re.compile(r"^\+?[0-9\s\-()]{7,20}$")
PIN_CODE_REGEX = re.compile(r"^[A-Za-z0-9\s\-]{3,15}$")

FORM_CONTROL_CLASS = (
    "w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm "
    "focus:ring-indigo-500 focus:border-indigo-500 text-sm"
)


class MerchantOnboardingForm(forms.Form):
    """
    Form for validating merchant business registration input during onboarding.
    Enforces required field validation, sanitization, and placeholder selection.
    """

    name = forms.CharField(
        label=_("Business Name"),
        max_length=255,
        min_length=2,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("e.g. Acme Retailers"),
                "autocomplete": "organization",
            }
        ),
    )
    business_type = forms.ChoiceField(
        label=_("Business Type"),
        choices=[("", _("Select business type"))] + list(BusinessType.choices),
        required=True,
        widget=forms.Select(
            attrs={
                "class": FORM_CONTROL_CLASS,
            }
        ),
    )
    description = forms.CharField(
        label=_("Business Description (Optional)"),
        required=False,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "rows": 3,
                "placeholder": _("Brief description of your products or business activity..."),
            }
        ),
    )
    contact_number = forms.CharField(
        label=_("Official Contact Number"),
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("e.g. +91 9876543210"),
                "autocomplete": "tel",
            }
        ),
    )
    email = forms.EmailField(
        label=_("Business Email"),
        widget=forms.EmailInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("contact@yourbusiness.com"),
                "autocomplete": "email",
            }
        ),
    )
    address = forms.CharField(
        label=_("Operating / Registered Address"),
        widget=forms.Textarea(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "rows": 2,
                "placeholder": _("Shop/Unit no., Building, Street name..."),
                "autocomplete": "street-address",
            }
        ),
    )
    city = forms.CharField(
        label=_("City"),
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("e.g. Mumbai"),
                "autocomplete": "address-level2",
            }
        ),
    )
    state = forms.CharField(
        label=_("State / Province"),
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("e.g. Maharashtra"),
                "autocomplete": "address-level1",
            }
        ),
    )
    pin_code = forms.CharField(
        label=_("Postal / PIN Code"),
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("e.g. 400001"),
                "autocomplete": "postal-code",
            }
        ),
    )
    form_token = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )

    def clean_name(self) -> str:
        name = self.cleaned_data.get("name", "").strip()
        if len(name) < 2:
            raise ValidationError(_("Business name must be at least 2 characters long."))
        return name

    def clean_business_type(self) -> str:
        b_type = self.cleaned_data.get("business_type", "").strip()
        if not b_type or b_type not in BusinessType.values:
            raise ValidationError(_("Please select a valid business type from the list."))
        return b_type

    def clean_email(self) -> str:
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email:
            raise ValidationError(_("Business email address is required."))
        return email

    def clean_contact_number(self) -> str:
        contact = self.cleaned_data.get("contact_number", "").strip()
        if not PHONE_REGEX.match(contact):
            raise ValidationError(
                _("Enter a valid phone number (7 to 20 digits, optionally starting with +).")
            )
        return contact

    def clean_address(self) -> str:
        address = self.cleaned_data.get("address", "").strip()
        if not address:
            raise ValidationError(_("Operating address is required."))
        return address

    def clean_city(self) -> str:
        city = self.cleaned_data.get("city", "").strip()
        if not city:
            raise ValidationError(_("City is required."))
        return city

    def clean_state(self) -> str:
        state = self.cleaned_data.get("state", "").strip()
        if not state:
            raise ValidationError(_("State is required."))
        return state

    def clean_pin_code(self) -> str:
        pin = self.cleaned_data.get("pin_code", "").strip()
        if not PIN_CODE_REGEX.match(pin):
            raise ValidationError(_("Enter a valid postal or PIN code."))
        return pin

    def clean_description(self) -> str:
        return self.cleaned_data.get("description", "").strip()
