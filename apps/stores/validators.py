import re
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils.translation import gettext_lazy as _

from .exceptions import SlugValidationError

# Slugs must contain only lowercase alphanumeric characters separated by single hyphens
SLUG_REGEX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SLUG_LENGTH = 100

RESERVED_SLUGS = frozenset(
    {
        "about",
        "account",
        "accounts",
        "admin",
        "api",
        "app",
        "auth",
        "billing",
        "cart",
        "checkout",
        "contact",
        "dashboard",
        "health",
        "help",
        "login",
        "logout",
        "media",
        "null",
        "order",
        "orders",
        "pricing",
        "privacy",
        "public",
        "register",
        "root",
        "s",
        "settings",
        "signin",
        "signout",
        "signup",
        "static",
        "store",
        "stores",
        "support",
        "system",
        "terms",
        "undefined",
        "webhook",
        "webhooks",
    }
)

ALLOWED_SOCIAL_PLATFORMS = frozenset(
    {"instagram", "facebook", "youtube", "twitter_x", "pinterest", "website"}
)
_https_url_validator = URLValidator(schemes=["https"])


def normalize_slug(value: str | None) -> str:
    """Trim surrounding whitespace and convert to lowercase."""
    if not value:
        return ""
    return value.strip().lower()


def validate_store_slug(value: str) -> None:
    """
    Validates store slug format and checks against reserved slugs.
    Django-compatible validator raising django.core.exceptions.ValidationError.
    """
    normalized = normalize_slug(value)

    if not normalized:
        raise ValidationError(_("Store slug cannot be empty."))

    if len(normalized) > MAX_SLUG_LENGTH:
        raise ValidationError(
            _("Store slug cannot exceed %(max)d characters.") % {"max": MAX_SLUG_LENGTH}
        )

    if not SLUG_REGEX.match(normalized):
        raise ValidationError(
            _(
                "Store slug must contain only lowercase letters, numbers, and single hyphens. "
                "It cannot start or end with a hyphen, contain spaces, underscores, or consecutive hyphens."
            )
        )

    if normalized in RESERVED_SLUGS:
        raise ValidationError(
            _("The slug '%(slug)s' is reserved and cannot be used.") % {"slug": normalized}
        )


def validate_and_normalize_slug(value: str) -> str:
    """
    Normalizes and validates a store slug for domain services,
    raising domain SlugValidationError on failure.
    """
    normalized = normalize_slug(value)

    if not normalized:
        raise SlugValidationError("Store slug cannot be empty.")

    if len(normalized) > MAX_SLUG_LENGTH:
        raise SlugValidationError(f"Store slug cannot exceed {MAX_SLUG_LENGTH} characters.")

    if not SLUG_REGEX.match(normalized):
        raise SlugValidationError(
            "Store slug must contain only lowercase letters, numbers, and single hyphens. "
            "It cannot start or end with a hyphen, contain spaces, underscores, or consecutive hyphens."
        )

    if normalized in RESERVED_SLUGS:
        raise SlugValidationError(f"The slug '{normalized}' is reserved and cannot be used.")

    return normalized


def validate_social_links(social_links: Any) -> dict[str, str]:
    """
    Validates social media links dictionary:
    - Must be a dictionary.
    - Platforms restricted to allowlist.
    - Values must be valid HTTPS URLs.
    - Empty string values are stripped.
    """
    if social_links is None:
        return {}
    if not isinstance(social_links, dict):
        raise ValidationError(_("Social links must be a dictionary/object."))

    cleaned: dict[str, str] = {}
    for platform, url in social_links.items():
        if platform not in ALLOWED_SOCIAL_PLATFORMS:
            raise ValidationError(
                _("Unsupported social platform '%(platform)s'. Allowed platforms: %(allowed)s.")
                % {"platform": platform, "allowed": ", ".join(sorted(ALLOWED_SOCIAL_PLATFORMS))}
            )
        if url is None:
            continue
        if not isinstance(url, str):
            raise ValidationError(
                _("URL for platform '%(platform)s' must be a string.") % {"platform": platform}
            )
        clean_url = url.strip()
        if not clean_url:
            continue
        try:
            _https_url_validator(clean_url)
        except ValidationError as exc:
            raise ValidationError(
                _("Invalid HTTPS URL for '%(platform)s': %(url)s.")
                % {"platform": platform, "url": clean_url}
            ) from exc
        cleaned[platform] = clean_url

    return cleaned
