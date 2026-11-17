import io
import json
import re
from typing import Any

from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from PIL import Image

from .exceptions import InvalidProductAttributeError, InvalidProductImageError

MAX_PRODUCT_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_PRODUCT_IMAGE_DIMENSION = 5000  # 5000 px
MAX_PRODUCT_IMAGE_PIXELS = 25_000_000  # 25M pixels
ALLOWED_PRODUCT_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}

MAX_ATTRIBUTE_COUNT = 20
MAX_ATTRIBUTE_KEY_LENGTH = 50
MAX_ATTRIBUTE_VALUE_LENGTH = 255
MAX_ATTRIBUTE_SERIALIZED_BYTES = 10 * 1024  # 10 KB

# Regex for detecting C0/C1 control characters (excluding standard whitespace)
CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
# Standard slug pattern: lowercase letters, numbers, and hyphens (no consecutive or leading/trailing hyphens)
SLUG_REGEX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_attributes(attributes: Any) -> dict[str, Any]:
    """
    Validates custom product attributes against multi-tenant catalogue specifications:
    - Must be a dictionary.
    - At most 20 attributes.
    - Keys: non-empty string, 1-50 chars, no control characters.
    - Values: scalar only (str, int, float, bool).
    - String values: max 255 chars, no control characters.
    - Total serialized JSON size <= 10 KB.
    """
    if attributes is None:
        return {}

    if not isinstance(attributes, dict):
        raise InvalidProductAttributeError(
            _("Product attributes must be provided as a dictionary/object.")
        )

    if len(attributes) > MAX_ATTRIBUTE_COUNT:
        raise InvalidProductAttributeError(
            _("Product cannot have more than %(max)d custom attributes (received %(count)d).")
            % {"max": MAX_ATTRIBUTE_COUNT, "count": len(attributes)}
        )

    cleaned: dict[str, Any] = {}

    for key, value in attributes.items():
        if not isinstance(key, str):
            raise InvalidProductAttributeError(
                _("Attribute key must be a string, got %(type)s.") % {"type": type(key).__name__}
            )

        if CONTROL_CHAR_REGEX.search(key):
            raise InvalidProductAttributeError(
                _("Attribute key '%(key)s' contains forbidden control characters.") % {"key": key}
            )

        clean_key = key.strip()
        if not clean_key or len(clean_key) > MAX_ATTRIBUTE_KEY_LENGTH:
            raise InvalidProductAttributeError(
                _("Attribute key '%(key)s' must be between 1 and %(max)d characters.")
                % {"key": key, "max": MAX_ATTRIBUTE_KEY_LENGTH}
            )

        # Value validation: scalar only (str, int, float, bool)
        # Note: bool is a subclass of int in Python, so isinstance(value, (str, int, float, bool)) is safe
        if value is None or isinstance(value, (list, dict, set, tuple)):
            raise InvalidProductAttributeError(
                _(
                    "Attribute '%(key)s' value must be a scalar (string, number, or boolean). "
                    "Nested collections and nulls are not permitted."
                )
                % {"key": clean_key}
            )

        if not isinstance(value, (str, int, float, bool)):
            raise InvalidProductAttributeError(
                _("Attribute '%(key)s' has an unsupported value type: %(type)s.")
                % {"key": clean_key, "type": type(value).__name__}
            )

        if isinstance(value, str):
            if CONTROL_CHAR_REGEX.search(value):
                raise InvalidProductAttributeError(
                    _("Attribute '%(key)s' value contains forbidden control characters.")
                    % {"key": clean_key}
                )
            clean_value = value.strip()
            if len(clean_value) > MAX_ATTRIBUTE_VALUE_LENGTH:
                raise InvalidProductAttributeError(
                    _("Attribute '%(key)s' value exceeds maximum length of %(max)d characters.")
                    % {"key": clean_key, "max": MAX_ATTRIBUTE_VALUE_LENGTH}
                )
            cleaned[clean_key] = clean_value
        else:
            cleaned[clean_key] = value

    # Check serialized size
    try:
        serialized = json.dumps(cleaned)
        if len(serialized.encode("utf-8")) > MAX_ATTRIBUTE_SERIALIZED_BYTES:
            raise InvalidProductAttributeError(
                _("Total serialized attributes payload exceeds the 10 KB limit.")
            )
    except (TypeError, ValueError) as exc:
        raise InvalidProductAttributeError(
            _("Attributes could not be safely serialized to JSON: %(error)s") % {"error": str(exc)}
        ) from exc

    return cleaned


def validate_and_normalize_slug(slug: str, max_length: int = 255) -> str:
    """
    Normalizes and validates a product or category slug.
    Converts to lowercase, strips leading/trailing hyphens/spaces,
    and enforces slug formatting constraints.
    """
    if not slug or not slug.strip():
        raise ValidationError(_("Slug cannot be empty."))

    normalized = slugify(slug.strip()).lower()
    if not normalized:
        raise ValidationError(_("Slug contains no valid alphanumeric characters."))

    if len(normalized) > max_length:
        normalized = normalized[:max_length].rstrip("-")

    if not SLUG_REGEX.match(normalized):
        raise ValidationError(
            _(
                "Slug may only contain lowercase letters, numbers, and hyphens without consecutive hyphens."
            )
        )

    return normalized


def validate_product_image(file: Any) -> None:
    """
    Pillow binary verification and decoding for product images.
    - Max 5 MB.
    - Allowed formats: JPEG, PNG, WebP.
    - Max dimension: 5000 px.
    - Max pixels: 25M pixels.
    - Fully decodes image via img.load() to reject corrupt streams.
    - Resets file seek pointer to 0.
    """
    if not file:
        raise InvalidProductImageError(_("No image file provided."))

    # Size check
    file_size = getattr(file, "size", 0)
    if file_size > MAX_PRODUCT_IMAGE_SIZE:
        max_mb = MAX_PRODUCT_IMAGE_SIZE // (1024 * 1024)
        raise InvalidProductImageError(
            _("Product image file size exceeds the %(limit)d MB limit.") % {"limit": max_mb}
        )

    # Binary verification
    try:
        file.seek(0)
        image_bytes = file.read()
        file.seek(0)
        byte_stream = io.BytesIO(image_bytes)

        with Image.open(byte_stream) as img:
            img.verify()
            fmt = img.format
    except Exception as exc:
        raise InvalidProductImageError(
            _("The uploaded file is not a valid or readable image.")
        ) from exc

    if not fmt or fmt.upper() not in ALLOWED_PRODUCT_IMAGE_FORMATS:
        raise InvalidProductImageError(
            _("Unsupported image format: %(format)s. Allowed formats are JPEG, PNG, and WebP.")
            % {"format": fmt or _("Unknown")}
        )

    # Decompression bomb and full decoding
    try:
        byte_stream.seek(0)
        with Image.open(byte_stream) as img:
            width, height = img.size
            total_pixels = width * height
            if (
                width > MAX_PRODUCT_IMAGE_DIMENSION
                or height > MAX_PRODUCT_IMAGE_DIMENSION
                or total_pixels > MAX_PRODUCT_IMAGE_PIXELS
            ):
                raise InvalidProductImageError(
                    _(
                        "Product image dimensions exceed allowed limit (max %(max_dim)d px, max %(max_px)d total pixels)."
                    )
                    % {"max_dim": MAX_PRODUCT_IMAGE_DIMENSION, "max_px": MAX_PRODUCT_IMAGE_PIXELS}
                )
            img.load()
    except InvalidProductImageError:
        raise
    except Exception as exc:
        raise InvalidProductImageError(
            _("The uploaded image contains corrupt or unreadable image data.")
        ) from exc
    finally:
        file.seek(0)
