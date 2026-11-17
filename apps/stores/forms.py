import io
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from PIL import Image

from .validators import validate_store_slug

FORM_CONTROL_CLASS = (
    "w-full px-3 py-2 border border-slate-300 rounded-md shadow-xs "
    "focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm "
    "disabled:bg-slate-50 disabled:text-slate-500 disabled:cursor-not-allowed"
)

MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2 MB
MAX_COVER_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_IMAGE_DIMENSION = 5000
MAX_IMAGE_PIXELS = 25_000_000  # Decompression bomb protection


def validate_uploaded_image(file: Any, max_size: int, field_name: str) -> None:
    """
    Secure form-level image validation using Pillow.
    1. Checks file size against limits before processing.
    2. Verifies structural integrity of the image file.
    3. Whitelists image format (JPEG, PNG, WebP) based on actual file contents.
    4. Enforces maximum dimensions and total pixel count to prevent decompression bombs.
    5. Fully decodes the image data to reject truncated or corrupt payloads.
    6. Resets file pointer so subsequent operations can read the file cleanly.
    """
    if not file:
        return

    # 1. Size check
    if getattr(file, "size", 0) > max_size:
        max_mb = max_size // (1024 * 1024)
        raise ValidationError(
            _("%(field)s file size exceeds the %(limit)d MB limit.")
            % {"field": field_name, "limit": max_mb}
        )

    # 2. Structural verification
    try:
        file.seek(0)
        image_bytes = file.read()
        file.seek(0)
        byte_stream = io.BytesIO(image_bytes)

        with Image.open(byte_stream) as img:
            img.verify()
            fmt = img.format
    except Exception as exc:
        raise ValidationError(
            _("The uploaded %(field)s is not a valid or readable image file.")
            % {"field": field_name}
        ) from exc

    # 3. Format whitelist check (derived from image bytes, not client MIME or extension)
    if not fmt or fmt.upper() not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError(
            _("Unsupported image format: %(format)s. Allowed formats are JPEG, PNG, and WebP.")
            % {"format": fmt or _("Unknown")}
        )

    # 4. Decompression and dimension/pixel check
    try:
        byte_stream.seek(0)
        with Image.open(byte_stream) as img:
            width, height = img.size
            total_pixels = width * height
            if (
                width > MAX_IMAGE_DIMENSION
                or height > MAX_IMAGE_DIMENSION
                or total_pixels > MAX_IMAGE_PIXELS
            ):
                raise ValidationError(
                    _("%(field)s image dimensions are too large (maximum %(max_dim)d px).")
                    % {"field": field_name, "max_dim": MAX_IMAGE_DIMENSION}
                )
            # Force full decoding to detect corrupt image streams
            img.load()
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError(
            _("The uploaded %(field)s contains corrupt or unreadable image data.")
            % {"field": field_name}
        ) from exc
    finally:
        file.seek(0)


class StoreCreationForm(forms.Form):
    """Form for initial Store creation when a Merchant has no Store."""

    name = forms.CharField(
        label=_("Store Name"),
        max_length=255,
        min_length=2,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("e.g. Acme Emporium"),
                "autocomplete": "organization",
            }
        ),
    )
    slug = forms.CharField(
        label=_("Public URL Slug"),
        max_length=100,
        required=True,
        validators=[validate_store_slug],
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("e.g. acme-emporium"),
                "autocomplete": "off",
                "spellcheck": "false",
            }
        ),
        help_text=_(
            "Lowercase letters, numbers, and hyphens. This forms your public URL: /s/your-slug/"
        ),
    )
    description = forms.CharField(
        label=_("Store Description (Optional)"),
        max_length=1000,
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "rows": 3,
                "placeholder": _("Tell customers what your store offers..."),
            }
        ),
    )
    logo = forms.FileField(
        label=_("Store Logo (Max 2 MB, JPEG/PNG/WebP)"),
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
    cover_image = forms.FileField(
        label=_("Store Cover Image (Max 5 MB, JPEG/PNG/WebP)"),
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

    def clean_name(self) -> str:
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise ValidationError(_("Store name cannot be empty."))
        return name

    def clean_slug(self) -> str:
        slug = self.cleaned_data.get("slug", "").strip().lower()
        if not slug:
            raise ValidationError(_("Store slug cannot be empty."))
        return slug

    def clean_logo(self) -> Any:
        logo = self.cleaned_data.get("logo")
        if logo:
            validate_uploaded_image(logo, MAX_LOGO_SIZE, _("Logo"))
        return logo

    def clean_cover_image(self) -> Any:
        cover = self.cleaned_data.get("cover_image")
        if cover:
            validate_uploaded_image(cover, MAX_COVER_SIZE, _("Cover image"))
        return cover


class StoreProfileForm(forms.Form):
    """Form for editing store branding details (name, description, logo, cover image)."""

    name = forms.CharField(
        label=_("Store Name"),
        max_length=255,
        min_length=2,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("e.g. Acme Emporium"),
                "autocomplete": "organization",
            }
        ),
    )
    description = forms.CharField(
        label=_("Store Description"),
        max_length=1000,
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "rows": 3,
                "placeholder": _("Tell customers what your store offers..."),
            }
        ),
    )
    logo = forms.FileField(
        label=_("Upload New Logo (Max 2 MB, JPEG/PNG/WebP)"),
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
    clear_logo = forms.BooleanField(
        label=_("Remove current logo"),
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            }
        ),
    )
    cover_image = forms.FileField(
        label=_("Upload New Cover Image (Max 5 MB, JPEG/PNG/WebP)"),
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
    clear_cover_image = forms.BooleanField(
        label=_("Remove current cover image"),
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            }
        ),
    )

    def clean_name(self) -> str:
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise ValidationError(_("Store name cannot be empty."))
        return name

    def clean_logo(self) -> Any:
        logo = self.cleaned_data.get("logo")
        if logo:
            validate_uploaded_image(logo, MAX_LOGO_SIZE, _("Logo"))
        return logo

    def clean_cover_image(self) -> Any:
        cover = self.cleaned_data.get("cover_image")
        if cover:
            validate_uploaded_image(cover, MAX_COVER_SIZE, _("Cover image"))
        return cover


class StoreSlugForm(forms.Form):
    """Form for updating store public URL slug with required confirmation."""

    slug = forms.CharField(
        label=_("New Store URL Slug"),
        max_length=100,
        required=True,
        validators=[validate_store_slug],
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("e.g. acme-emporium"),
                "autocomplete": "off",
                "spellcheck": "false",
            }
        ),
        help_text=_(
            "Lowercase letters, numbers, and hyphens. Changing this alters your public storefront URL."
        ),
    )
    confirm_slug_change = forms.BooleanField(
        label=_("I understand that changing my store slug will break previously shared links."),
        required=True,
        error_messages={
            "required": _(
                "You must acknowledge that previously shared links will stop working before changing the slug."
            )
        },
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            }
        ),
    )

    def clean_slug(self) -> str:
        slug = self.cleaned_data.get("slug", "").strip().lower()
        if not slug:
            raise ValidationError(_("Store slug cannot be empty."))
        return slug
