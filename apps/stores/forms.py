import io
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from PIL import Image

from .validators import validate_social_links, validate_store_slug

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
    tagline = forms.CharField(
        label=_("Store Tagline (Optional)"),
        max_length=120,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("e.g. Handcrafted goods made with passion"),
            }
        ),
        help_text=_("A short customer-facing slogan (up to 120 characters)."),
    )
    whatsapp_number = forms.CharField(
        label=_("WhatsApp Number (Optional)"),
        max_length=20,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("+91 98765 43210"),
            }
        ),
        help_text=_("International phone number with country code for direct customer enquiries."),
    )
    allow_whatsapp_fallback = forms.BooleanField(
        label=_("Enable WhatsApp Fallback"),
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            }
        ),
        help_text=_("Allow customers to enquire or place orders via WhatsApp on your storefront."),
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

    def clean_tagline(self) -> str:
        tagline = (self.cleaned_data.get("tagline") or "").strip()
        if len(tagline) > 120:
            raise ValidationError(_("Store tagline cannot exceed 120 characters."))
        return tagline

    def clean_whatsapp_number(self) -> str:
        whatsapp = (self.cleaned_data.get("whatsapp_number") or "").strip()
        if len(whatsapp) > 20:
            raise ValidationError(_("WhatsApp number cannot exceed 20 characters."))
        return whatsapp

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

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        social_dict: dict[str, str] = {}

        # 1. Direct social_links passed in data (if any dict or JSON)
        raw_social = self.data.get("social_links")
        if isinstance(raw_social, dict):
            for k, v in raw_social.items():
                if v and isinstance(v, str) and v.strip():
                    social_dict[k] = v.strip()
        elif isinstance(raw_social, str) and raw_social.strip():
            try:
                import json

                parsed = json.loads(raw_social)
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        if v and isinstance(v, str) and v.strip():
                            social_dict[k] = v.strip()
            except Exception:
                pass

        # 2. Individual social fields
        for platform in ("instagram", "facebook", "youtube", "twitter_x", "pinterest", "website"):
            field_name = f"social_{platform}"
            val = cleaned_data.get(field_name)
            if val and isinstance(val, str) and val.strip():
                clean_url = val.strip()
                if clean_url.startswith("http://"):
                    self.add_error(field_name, _("Social links must use secure HTTPS (https://)."))
                    continue
                social_dict[platform] = clean_url

        try:
            cleaned_data["social_links"] = validate_social_links(social_dict)
        except ValidationError as exc:
            self.add_error(None, exc)

        return cleaned_data


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
    tagline = forms.CharField(
        label=_("Store Tagline"),
        max_length=120,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("e.g. Artisanal fashion crafted with care"),
            }
        ),
        help_text=_("A short customer-facing slogan (up to 120 characters)."),
    )
    whatsapp_number = forms.CharField(
        label=_("WhatsApp Contact Number"),
        max_length=20,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": FORM_CONTROL_CLASS,
                "placeholder": _("+91 98765 43210"),
            }
        ),
        help_text=_("International phone number with country code for direct customer enquiries."),
    )
    allow_whatsapp_fallback = forms.BooleanField(
        label=_("Enable WhatsApp Fallback"),
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            }
        ),
        help_text=_("Allow customers to enquire or place orders via WhatsApp on your storefront."),
    )
    social_instagram = forms.URLField(
        label=_("Instagram URL"),
        assume_scheme="https",
        required=False,
        widget=forms.URLInput(
            attrs={"class": FORM_CONTROL_CLASS, "placeholder": "https://instagram.com/yourhandle"}
        ),
    )
    social_facebook = forms.URLField(
        label=_("Facebook URL"),
        assume_scheme="https",
        required=False,
        widget=forms.URLInput(
            attrs={"class": FORM_CONTROL_CLASS, "placeholder": "https://facebook.com/yourpage"}
        ),
    )
    social_youtube = forms.URLField(
        label=_("YouTube URL"),
        assume_scheme="https",
        required=False,
        widget=forms.URLInput(
            attrs={"class": FORM_CONTROL_CLASS, "placeholder": "https://youtube.com/@yourchannel"}
        ),
    )
    social_twitter_x = forms.URLField(
        label=_("X / Twitter URL"),
        assume_scheme="https",
        required=False,
        widget=forms.URLInput(
            attrs={"class": FORM_CONTROL_CLASS, "placeholder": "https://x.com/yourhandle"}
        ),
    )
    social_pinterest = forms.URLField(
        label=_("Pinterest URL"),
        assume_scheme="https",
        required=False,
        widget=forms.URLInput(
            attrs={"class": FORM_CONTROL_CLASS, "placeholder": "https://pinterest.com/yourprofile"}
        ),
    )
    social_website = forms.URLField(
        label=_("Official Website URL"),
        assume_scheme="https",
        required=False,
        widget=forms.URLInput(
            attrs={"class": FORM_CONTROL_CLASS, "placeholder": "https://yourwebsite.com"}
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

    def clean_tagline(self) -> str:
        tagline = (self.cleaned_data.get("tagline") or "").strip()
        if len(tagline) > 120:
            raise ValidationError(_("Store tagline cannot exceed 120 characters."))
        return tagline

    def clean_whatsapp_number(self) -> str:
        whatsapp = (self.cleaned_data.get("whatsapp_number") or "").strip()
        if len(whatsapp) > 20:
            raise ValidationError(_("WhatsApp number cannot exceed 20 characters."))
        return whatsapp

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

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        social_dict: dict[str, str] = {}

        # 1. Direct social_links passed in data (if any dict or JSON)
        raw_social = self.data.get("social_links")
        if isinstance(raw_social, dict):
            for k, v in raw_social.items():
                if v and isinstance(v, str) and v.strip():
                    social_dict[k] = v.strip()
        elif isinstance(raw_social, str) and raw_social.strip():
            try:
                import json

                parsed = json.loads(raw_social)
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        if v and isinstance(v, str) and v.strip():
                            social_dict[k] = v.strip()
            except Exception:
                pass

        # 2. Individual social fields
        for platform in ("instagram", "facebook", "youtube", "twitter_x", "pinterest", "website"):
            field_name = f"social_{platform}"
            val = cleaned_data.get(field_name)
            if val and isinstance(val, str) and val.strip():
                clean_url = val.strip()
                if clean_url.startswith("http://"):
                    self.add_error(field_name, _("Social links must use secure HTTPS (https://)."))
                    continue
                social_dict[platform] = clean_url

        try:
            cleaned_data["social_links"] = validate_social_links(social_dict)
        except ValidationError as exc:
            self.add_error(None, exc)

        return cleaned_data


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
