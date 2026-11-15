from typing import Any

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """
    Custom user manager where email is the unique identifier
    for authentication instead of usernames, with strict lowercase
    email normalization.
    """

    def normalize_email(self, email: str | None) -> str:
        """Normalize email and enforce lowercasing."""
        email = super().normalize_email(email or "")
        return email.lower().strip()

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> Any:
        """Create and save a standard user with the given email and password."""
        if not email:
            raise ValueError("The Email address must be provided.")

        email = self.normalize_email(email)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_verified", False)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)

        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> Any:
        """Create and save a SuperUser with the given email and password."""
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_verified", True)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        if extra_fields.get("is_verified") is not True:
            raise ValueError("Superuser must have is_verified=True.")

        return self.create_user(email, password, **extra_fields)
