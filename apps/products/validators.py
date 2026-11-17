import io
import json
import math
import re
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from PIL import Image

from .choices import PriceDisplayMode, ProductStatus
from .exceptions import InvalidProductAttributeError, InvalidProductImageError

MAX_PRODUCT_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_PRODUCT_IMAGE_DIMENSION = 5000  # 5000 px
MAX_PRODUCT_IMAGE_PIXELS = 25_000_000  # 25M pixels
ALLOWED_PRODUCT_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}

MAX_ATTRIBUTE_COUNT = 20
MAX_SPECIFICATION_COUNT = 15
MAX_ATTRIBUTE_KEY_LENGTH = 50
MAX_ATTRIBUTE_VALUE_LENGTH = 255
MAX_ATTRIBUTE_SERIALIZED_BYTES = 10 * 1024  # 10 KB

# Regex for detecting C0/C1 control characters (excluding standard whitespace)
CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
# Standard slug pattern: lowercase letters, numbers, and hyphens (no consecutive or leading/trailing hyphens)
SLUG_REGEX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Structured specification key pattern: lowercase alphanumeric and underscores
SPEC_KEY_REGEX = re.compile(r"^[a-z0-9_]{2,30}$")
# Hex color code pattern
HEX_COLOR_REGEX = re.compile(r"^#[0-9a-fA-F]{6}$")

ALLOWED_ATTRIBUTE_TYPES = {"text", "number", "single_select", "multi_select", "color"}

ALLOWED_FIELDS_PER_TYPE = {
    "text": {"key", "label", "type", "value"},
    "number": {"key", "label", "type", "value", "unit"},
    "single_select": {"key", "label", "type", "options", "value"},
    "multi_select": {"key", "label", "type", "options", "values"},
    "color": {"key", "label", "type", "values"},
}


def validate_product_pricing(
    *,
    price: Decimal | None,
    mrp: Decimal | None,
    price_display_mode: str,
    status: str = ProductStatus.DRAFT,
) -> None:
    """
    Centralized multi-tier domain validator for product pricing:
    - Enforces valid price_display_mode choices.
    - Enforces non-negative price and mrp.
    - Enforces mrp >= price when both are provided.
    - Enforces that published products in SHOW_PRICE mode must have a non-null price.
    """
    if price_display_mode not in PriceDisplayMode.values:
        raise ValidationError(
            {
                "price_display_mode": _("Invalid price display mode '%(val)s'.")
                % {"val": price_display_mode}
            }
        )

    if price is not None and price < Decimal("0.00"):
        raise ValidationError({"price": _("Selling price cannot be negative.")})

    if mrp is not None and mrp < Decimal("0.00"):
        raise ValidationError({"mrp": _("MRP cannot be negative.")})

    if price is not None and mrp is not None and mrp < price:
        raise ValidationError({"mrp": _("MRP cannot be less than selling price.")})

    if status == ProductStatus.PUBLISHED and price_display_mode == PriceDisplayMode.SHOW_PRICE:
        if price is None:
            raise ValidationError(
                {
                    "price": _(
                        "Selling price is required when Show Price is selected for a published product."
                    )
                }
            )


def validate_attributes(attributes: Any) -> dict[str, Any]:
    """
    Validates custom product attributes against multi-tenant catalogue specifications.
    Supports two formats:
    1. Structured Specification Contract: `{"specifications": [...]}`
    2. Legacy Flat Dictionary: `{"Key": "Value"}`
    """
    if attributes is None:
        return {}

    if not isinstance(attributes, dict):
        raise InvalidProductAttributeError(
            _("Product attributes must be provided as a dictionary/object.")
        )

    # Check for structured specifications format
    if "specifications" in attributes:
        return _validate_structured_specifications(attributes)

    return _validate_legacy_flat_attributes(attributes)


def _validate_structured_specifications(data: dict[str, Any]) -> dict[str, Any]:
    """
    Validates the structured specifications JSON contract.
    """
    # Top-level allowlist: only 'specifications' key permitted
    unexpected_top_level = set(data.keys()) - {"specifications"}
    if unexpected_top_level:
        raise InvalidProductAttributeError(
            _("Unexpected top-level keys in attributes: %(keys)s.")
            % {"keys": ", ".join(sorted(unexpected_top_level))}
        )

    specs = data.get("specifications")
    if not isinstance(specs, list):
        raise InvalidProductAttributeError(
            _("'specifications' must be a list of attribute specification objects.")
        )

    if len(specs) > MAX_SPECIFICATION_COUNT:
        raise InvalidProductAttributeError(
            _("Product cannot have more than %(max)d custom specifications (received %(count)d).")
            % {"max": MAX_SPECIFICATION_COUNT, "count": len(specs)}
        )

    seen_keys: set[str] = set()
    cleaned_specs: list[dict[str, Any]] = []

    for idx, spec in enumerate(specs):
        if not isinstance(spec, dict):
            raise InvalidProductAttributeError(
                _("Specification at index %(idx)d must be an object.") % {"idx": idx}
            )

        # Basic identification fields
        key = spec.get("key")
        label = spec.get("label")
        attr_type = spec.get("type")

        if not isinstance(key, str) or not SPEC_KEY_REGEX.match(key):
            raise InvalidProductAttributeError(
                _(
                    "Specification at index %(idx)d has invalid key '%(key)s'. "
                    "Keys must be lowercase alphanumeric with underscores (2-30 characters)."
                )
                % {"idx": idx, "key": key}
            )

        if key in seen_keys:
            raise InvalidProductAttributeError(
                _("Duplicate specification key '%(key)s' found.") % {"key": key}
            )
        seen_keys.add(key)

        if not isinstance(label, str):
            raise InvalidProductAttributeError(
                _("Specification '%(key)s' must have a string label.") % {"key": key}
            )
        clean_label = label.strip()
        if len(clean_label) < 2 or len(clean_label) > 50:
            raise InvalidProductAttributeError(
                _("Specification '%(key)s' label must be between 2 and 50 characters.")
                % {"key": key}
            )
        if CONTROL_CHAR_REGEX.search(clean_label):
            raise InvalidProductAttributeError(
                _("Specification '%(key)s' label contains forbidden control characters.")
                % {"key": key}
            )

        if attr_type not in ALLOWED_ATTRIBUTE_TYPES:
            raise InvalidProductAttributeError(
                _(
                    "Specification '%(key)s' has invalid type '%(type)s'. Allowed types: %(allowed)s."
                )
                % {
                    "key": key,
                    "type": attr_type,
                    "allowed": ", ".join(sorted(ALLOWED_ATTRIBUTE_TYPES)),
                }
            )

        # Check allowed fields for this type
        allowed_fields = ALLOWED_FIELDS_PER_TYPE[attr_type]
        extra_fields = set(spec.keys()) - allowed_fields
        if extra_fields:
            raise InvalidProductAttributeError(
                _(
                    "Specification '%(key)s' contains unauthorized fields for type '%(type)s': %(extra)s."
                )
                % {"key": key, "type": attr_type, "extra": ", ".join(sorted(extra_fields))}
            )

        cleaned_item: dict[str, Any] = {
            "key": key,
            "label": clean_label,
            "type": attr_type,
        }

        # Type-specific validation
        if attr_type == "text":
            val = spec.get("value")
            if not isinstance(val, str) or not val.strip():
                raise InvalidProductAttributeError(
                    _("Text specification '%(key)s' must have a non-empty string value.")
                    % {"key": key}
                )
            clean_val = val.strip()
            if len(clean_val) > 500:
                raise InvalidProductAttributeError(
                    _("Text specification '%(key)s' value exceeds 500 characters.") % {"key": key}
                )
            if CONTROL_CHAR_REGEX.search(clean_val):
                raise InvalidProductAttributeError(
                    _("Text specification '%(key)s' value contains forbidden control characters.")
                    % {"key": key}
                )
            cleaned_item["value"] = clean_val

        elif attr_type == "number":
            val = spec.get("value")
            # In Python, bool is a subclass of int: explicitly reject booleans
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise InvalidProductAttributeError(
                    _(
                        "Number specification '%(key)s' value must be a valid number, not boolean or string."
                    )
                    % {"key": key}
                )
            if not math.isfinite(val):
                raise InvalidProductAttributeError(
                    _("Number specification '%(key)s' value must be a finite number.")
                    % {"key": key}
                )
            if val < -1_000_000_000 or val > 1_000_000_000:
                raise InvalidProductAttributeError(
                    _(
                        "Number specification '%(key)s' value must be between -1,000,000,000 and 1,000,000,000."
                    )
                    % {"key": key}
                )
            cleaned_item["value"] = val

            unit = spec.get("unit")
            if unit is not None:
                if not isinstance(unit, str):
                    raise InvalidProductAttributeError(
                        _("Number specification '%(key)s' unit must be a string.") % {"key": key}
                    )
                clean_unit = unit.strip()
                if len(clean_unit) > 15:
                    raise InvalidProductAttributeError(
                        _("Number specification '%(key)s' unit exceeds 15 characters.")
                        % {"key": key}
                    )
                if CONTROL_CHAR_REGEX.search(clean_unit):
                    raise InvalidProductAttributeError(
                        _(
                            "Number specification '%(key)s' unit contains forbidden control characters."
                        )
                        % {"key": key}
                    )
                if clean_unit:
                    cleaned_item["unit"] = clean_unit

        elif attr_type == "single_select":
            opts = spec.get("options")
            val = spec.get("value")
            clean_opts = _validate_options_list(opts, key, max_count=20)
            if not isinstance(val, str) or not val.strip():
                raise InvalidProductAttributeError(
                    _("Single-select specification '%(key)s' must have a non-empty string value.")
                    % {"key": key}
                )
            clean_val = val.strip()
            if clean_val not in clean_opts:
                raise InvalidProductAttributeError(
                    _("Value '%(val)s' for specification '%(key)s' is not in allowed options.")
                    % {"val": clean_val, "key": key}
                )
            cleaned_item["options"] = clean_opts
            cleaned_item["value"] = clean_val

        elif attr_type == "multi_select":
            opts = spec.get("options")
            vals = spec.get("values")
            clean_opts = _validate_options_list(opts, key, max_count=30)
            if not isinstance(vals, list) or not vals:
                raise InvalidProductAttributeError(
                    _(
                        "Multi-select specification '%(key)s' values must be a non-empty list of strings."
                    )
                    % {"key": key}
                )
            if len(vals) > 20:
                raise InvalidProductAttributeError(
                    _(
                        "Multi-select specification '%(key)s' cannot have more than 20 selected values."
                    )
                    % {"key": key}
                )
            seen_vals: set[str] = set()
            clean_vals: list[str] = []
            for v in vals:
                if not isinstance(v, str) or not v.strip():
                    raise InvalidProductAttributeError(
                        _(
                            "Multi-select specification '%(key)s' contains an empty or non-string value."
                        )
                        % {"key": key}
                    )
                cv = v.strip()
                if cv in seen_vals:
                    raise InvalidProductAttributeError(
                        _(
                            "Duplicate selected value '%(val)s' in multi-select specification '%(key)s'."
                        )
                        % {"val": cv, "key": key}
                    )
                if cv not in clean_opts:
                    raise InvalidProductAttributeError(
                        _(
                            "Selected value '%(val)s' for specification '%(key)s' is not in allowed options."
                        )
                        % {"val": cv, "key": key}
                    )
                seen_vals.add(cv)
                clean_vals.append(cv)
            cleaned_item["options"] = clean_opts
            cleaned_item["values"] = clean_vals

        elif attr_type == "color":
            vals = spec.get("values")
            if not isinstance(vals, list) or not vals:
                raise InvalidProductAttributeError(
                    _(
                        "Color specification '%(key)s' values must be a non-empty list of color items."
                    )
                    % {"key": key}
                )
            if len(vals) > 15:
                raise InvalidProductAttributeError(
                    _("Color specification '%(key)s' cannot have more than 15 colors.")
                    % {"key": key}
                )
            seen_hex: set[str] = set()
            seen_names: set[str] = set()
            clean_colors: list[dict[str, str]] = []
            for c_idx, c_item in enumerate(vals):
                if not isinstance(c_item, dict):
                    raise InvalidProductAttributeError(
                        _("Color item at index %(c_idx)d in '%(key)s' must be an object.")
                        % {"c_idx": c_idx, "key": key}
                    )
                extra_c_fields = set(c_item.keys()) - {"name", "hex"}
                if extra_c_fields:
                    raise InvalidProductAttributeError(
                        _("Unauthorized fields in color item of '%(key)s': %(extra)s.")
                        % {"key": key, "extra": ", ".join(sorted(extra_c_fields))}
                    )
                c_name = c_item.get("name")
                c_hex = c_item.get("hex")
                if not isinstance(c_name, str) or not c_name.strip():
                    raise InvalidProductAttributeError(
                        _("Color item in '%(key)s' must have a non-empty name string.")
                        % {"key": key}
                    )
                clean_name = c_name.strip()
                if len(clean_name) > 30 or CONTROL_CHAR_REGEX.search(clean_name):
                    raise InvalidProductAttributeError(
                        _(
                            "Color name in '%(key)s' must be between 1 and 30 characters without control characters."
                        )
                        % {"key": key}
                    )
                if not isinstance(c_hex, str) or not HEX_COLOR_REGEX.match(c_hex.strip()):
                    raise InvalidProductAttributeError(
                        _(
                            "Color hex in '%(key)s' must be a valid 6-character hex code (e.g. #191970)."
                        )
                        % {"key": key}
                    )
                clean_hex = c_hex.strip().lower()
                if clean_hex in seen_hex:
                    raise InvalidProductAttributeError(
                        _("Duplicate color hex '%(hex)s' in specification '%(key)s'.")
                        % {"hex": clean_hex, "key": key}
                    )
                if clean_name.lower() in seen_names:
                    raise InvalidProductAttributeError(
                        _("Duplicate color name '%(name)s' in specification '%(key)s'.")
                        % {"name": clean_name, "key": key}
                    )
                seen_hex.add(clean_hex)
                seen_names.add(clean_name.lower())
                clean_colors.append({"name": clean_name, "hex": clean_hex})
            cleaned_item["values"] = clean_colors

        cleaned_specs.append(cleaned_item)

    cleaned_result = {"specifications": cleaned_specs}
    _verify_serialized_size(cleaned_result)
    return cleaned_result


def _validate_options_list(opts: Any, key: str, max_count: int) -> list[str]:
    """Helper to validate option lists for single_select and multi_select."""
    if not isinstance(opts, list) or not opts:
        raise InvalidProductAttributeError(
            _("Specification '%(key)s' options must be a non-empty list of strings.") % {"key": key}
        )
    if len(opts) > max_count:
        raise InvalidProductAttributeError(
            _("Specification '%(key)s' cannot have more than %(max)d options (received %(count)d).")
            % {"key": key, "max": max_count, "count": len(opts)}
        )
    clean_opts: list[str] = []
    seen: set[str] = set()
    for o in opts:
        if not isinstance(o, str) or not o.strip():
            raise InvalidProductAttributeError(
                _("Options for specification '%(key)s' must be non-empty strings.") % {"key": key}
            )
        co = o.strip()
        if len(co) > 50 or CONTROL_CHAR_REGEX.search(co):
            raise InvalidProductAttributeError(
                _(
                    "Option '%(opt)s' in '%(key)s' must be between 1 and 50 characters without control characters."
                )
                % {"opt": co, "key": key}
            )
        if co.lower() in seen:
            raise InvalidProductAttributeError(
                _("Duplicate option '%(opt)s' in specification '%(key)s'.")
                % {"opt": co, "key": key}
            )
        seen.add(co.lower())
        clean_opts.append(co)
    return clean_opts


def _validate_legacy_flat_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """
    Validates legacy flat key-value attributes with normalization and collision checks.
    """
    if len(attributes) > MAX_ATTRIBUTE_COUNT:
        raise InvalidProductAttributeError(
            _("Product cannot have more than %(max)d custom attributes (received %(count)d).")
            % {"max": MAX_ATTRIBUTE_COUNT, "count": len(attributes)}
        )

    cleaned: dict[str, Any] = {}
    normalized_keys: set[str] = set()

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

        # Check normalization collision (e.g. 'Fabric' vs 'fabric' or 'Fabric-Type' vs 'Fabric_Type')
        norm_key = clean_key.lower().replace("-", "_")
        if norm_key in normalized_keys:
            raise InvalidProductAttributeError(
                _("Duplicate attribute key after normalization: '%(norm)s'.") % {"norm": norm_key}
            )
        normalized_keys.add(norm_key)

        # Value validation: scalar only (str, int, float, bool)
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

    _verify_serialized_size(cleaned)
    return cleaned


def _verify_serialized_size(payload: dict[str, Any]) -> None:
    """Verifies that total JSON payload does not exceed 10 KB."""
    try:
        serialized = json.dumps(payload)
        if len(serialized.encode("utf-8")) > MAX_ATTRIBUTE_SERIALIZED_BYTES:
            raise InvalidProductAttributeError(
                _("Total serialized attributes payload exceeds the 10 KB limit.")
            )
    except (TypeError, ValueError) as exc:
        raise InvalidProductAttributeError(
            _("Attributes could not be safely serialized to JSON: %(error)s") % {"error": str(exc)}
        ) from exc


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
