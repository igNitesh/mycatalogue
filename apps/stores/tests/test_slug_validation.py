import pytest
from django.core.exceptions import ValidationError

from apps.stores.exceptions import SlugValidationError
from apps.stores.validators import (
    normalize_slug,
    validate_and_normalize_slug,
    validate_store_slug,
)


class TestSlugValidation:
    @pytest.mark.parametrize(
        ("input_slug", "expected"),
        [
            ("store", "store"),
            ("MY-STORE", "my-store"),
            ("  spaces-trimmed  ", "spaces-trimmed"),
            ("Alpha-Beta-123", "alpha-beta-123"),
            ("a-b-c", "a-b-c"),
        ],
    )
    def test_normalize_slug(self, input_slug, expected):
        assert normalize_slug(input_slug) == expected

    @pytest.mark.parametrize(
        "valid_slug",
        [
            "shop",
            "my-shop",
            "super-store-99",
            "brand-123-outlet",
            "a",
            "1",
            "shop-1",
        ],
    )
    def test_valid_slugs_pass_validation(self, valid_slug):
        # Should not raise
        validate_store_slug(valid_slug)
        result = validate_and_normalize_slug(valid_slug)
        assert result == valid_slug.lower()

    @pytest.mark.parametrize(
        "invalid_slug",
        [
            "store name with spaces",
            "store_with_underscore",
            "-leading-hyphen",
            "trailing-hyphen-",
            "double--hyphen",
            "triple---hyphen",
            "special@char",
            "special#char",
            "store.dot",
            "store!bang",
            "store/slash",
            "store\\backslash",
        ],
    )
    def test_invalid_characters_and_formats_rejected(self, invalid_slug):
        with pytest.raises(ValidationError):
            validate_store_slug(invalid_slug)

        with pytest.raises(SlugValidationError):
            validate_and_normalize_slug(invalid_slug)

    def test_empty_slug_rejected(self):
        with pytest.raises(ValidationError):
            validate_store_slug("")

        with pytest.raises(SlugValidationError):
            validate_and_normalize_slug("")

        with pytest.raises(ValidationError):
            validate_store_slug("   ")

        with pytest.raises(SlugValidationError):
            validate_and_normalize_slug("   ")

    def test_exceeding_max_length_rejected(self):
        long_slug = "a" * 101
        with pytest.raises(ValidationError):
            validate_store_slug(long_slug)

        with pytest.raises(SlugValidationError):
            validate_and_normalize_slug(long_slug)

    @pytest.mark.parametrize(
        "reserved_word",
        [
            "admin",
            "api",
            "auth",
            "login",
            "logout",
            "register",
            "signup",
            "dashboard",
            "settings",
            "static",
            "media",
            "health",
            "s",
            "cart",
            "checkout",
            "orders",
            "account",
            "support",
        ],
    )
    def test_reserved_slugs_rejected(self, reserved_word):
        with pytest.raises(ValidationError):
            validate_store_slug(reserved_word)

        with pytest.raises(SlugValidationError):
            validate_and_normalize_slug(reserved_word)

        # Case-insensitive reserved check
        with pytest.raises(ValidationError):
            validate_store_slug(reserved_word.upper())

        with pytest.raises(SlugValidationError):
            validate_and_normalize_slug(reserved_word.upper())
