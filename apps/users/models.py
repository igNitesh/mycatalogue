from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model for mycatalogue multi-tenant digital storefront SaaS.

    Email is the unique identifier for authentication. Separate boolean flags
    strictly partition:
    - is_active: Account status (enables/disables login entirely).
    - is_verified: Email verification status (gates protected storefront operations).
    - is_staff: Access to Django administration dashboard.
    - is_superuser: Unrestricted permissions across all models.
    """

    email = models.EmailField(
        _("email address"),
        unique=True,
        db_index=True,
        error_messages={
            "unique": _("A user with that email address already exists."),
        },
    )
    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)

    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this account should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )
    is_verified = models.BooleanField(
        _("email verified"),
        default=False,
        db_index=True,
        help_text=_("Designates whether this user has verified ownership of their email address."),
    )
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into the Django admin site."),
    )

    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-date_joined"]
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="unique_lowercase_user_email",
            )
        ]

    def clean(self) -> None:
        """Enforce lowercase email format before saving."""
        super().clean()
        if self.email:
            self.email = self.email.lower().strip()

    def get_full_name(self) -> str:
        """Return the first_name plus the last_name, with a space in between."""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.email

    def get_short_name(self) -> str:
        """Return the short name for the user."""
        return self.first_name or self.email.split("@")[0]

    def __str__(self) -> str:
        return self.email
