import re

from django.core.exceptions import ValidationError
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
