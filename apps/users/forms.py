from typing import Any

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class UserRegistrationForm(forms.ModelForm):
    """Registration form with email normalization and password validation."""

    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 text-sm",
                "placeholder": "••••••••",
                "autocomplete": "new-password",
            }
        ),
    )
    password_confirm = forms.CharField(
        label=_("Confirm Password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 text-sm",
                "placeholder": "••••••••",
                "autocomplete": "new-password",
            }
        ),
    )

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name")
        widgets = {
            "email": forms.EmailInput(
                attrs={
                    "class": "w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 text-sm",
                    "placeholder": "you@example.com",
                    "autocomplete": "email",
                }
            ),
            "first_name": forms.TextInput(
                attrs={
                    "class": "w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 text-sm",
                    "placeholder": "First name",
                    "autocomplete": "given-name",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "class": "w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 text-sm",
                    "placeholder": "Last name",
                    "autocomplete": "family-name",
                }
            ),
        }

    def clean_email(self) -> str:
        email = self.cleaned_data.get("email", "").lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(_("An account with this email address already exists."))
        return email

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm:
            if password != password_confirm:
                self.add_error("password_confirm", _("The two passwords do not match."))
            else:
                user_instance = User(
                    email=cleaned_data.get("email", ""),
                    first_name=cleaned_data.get("first_name", ""),
                    last_name=cleaned_data.get("last_name", ""),
                )
                validate_password(password, user=user_instance)

        return cleaned_data


class UserLoginForm(forms.Form):
    """Session login form supporting case-insensitive email lookup."""

    email = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(
            attrs={
                "class": "w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 text-sm",
                "placeholder": "you@example.com",
                "autocomplete": "email",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 text-sm",
                "placeholder": "••••••••",
                "autocomplete": "current-password",
            }
        ),
    )

    def __init__(self, request: Any = None, *args: Any, **kwargs: Any) -> None:
        self.request = request
        self.user_cache: Any = None
        super().__init__(*args, **kwargs)

    def clean_email(self) -> str:
        return self.cleaned_data.get("email", "").lower().strip()

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")

        if email and password:
            self.user_cache = authenticate(
                self.request,
                email=email,
                password=password,
            )
            if self.user_cache is None:
                raise ValidationError(
                    _("Invalid email address or password."),
                    code="invalid_login",
                )
            if not self.user_cache.is_active:
                raise ValidationError(
                    _("This account is inactive. Please contact support."),
                    code="inactive",
                )

        return cleaned_data

    def get_user(self) -> Any:
        return self.user_cache


class PasswordResetRequestForm(forms.Form):
    """Password reset request form with lowercase email normalization."""

    email = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(
            attrs={
                "class": "w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 text-sm",
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }
        ),
    )

    def clean_email(self) -> str:
        return self.cleaned_data.get("email", "").lower().strip()


class UserSetPasswordForm(forms.Form):
    """Set new password confirmation form."""

    new_password = forms.CharField(
        label=_("New password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 text-sm",
                "placeholder": "••••••••",
                "autocomplete": "new-password",
            }
        ),
    )
    confirm_password = forms.CharField(
        label=_("Confirm new password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 text-sm",
                "placeholder": "••••••••",
                "autocomplete": "new-password",
            }
        ),
    )

    def __init__(self, user: Any, *args: Any, **kwargs: Any) -> None:
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")

        if new_password and confirm_password:
            if new_password != confirm_password:
                self.add_error("confirm_password", _("The two passwords do not match."))
            else:
                validate_password(new_password, user=self.user)

        return cleaned_data
