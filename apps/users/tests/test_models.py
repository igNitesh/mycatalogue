import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    """Unit tests for custom User model and UserManager."""

    def test_create_user_normalizes_email_to_lowercase(self):
        """User creation normalizes email to strict lowercase."""
        user = User.objects.create_user(
            email="TEST.User@EXAMPLE.COM",
            password="A_Very_Secure_Password_123!",
            first_name="Test",
            last_name="User",
        )
        assert user.email == "test.user@example.com"
        assert user.is_active is True
        assert user.is_verified is False
        assert user.is_staff is False
        assert user.is_superuser is False
        assert user.check_password("A_Very_Secure_Password_123!") is True

    def test_create_user_without_email_raises_value_error(self):
        """Attempting to create a user without an email raises ValueError."""
        with pytest.raises(ValueError, match="The Email address must be provided."):
            User.objects.create_user(email="", password="password123")

    def test_duplicate_email_rejected_at_database_level(self):
        """Database enforces case-insensitive uniqueness on email."""
        User.objects.create_user(
            email="merchant@example.com",
            password="StrongPassword123!",
        )

        with pytest.raises(IntegrityError):
            User.objects.create_user(
                email="MERCHANT@example.com",
                password="AnotherPassword123!",
            )

    def test_create_superuser(self):
        """Superuser creation sets is_staff, is_superuser, and is_verified to True."""
        admin_user = User.objects.create_superuser(
            email="admin@example.com",
            password="AdminPassword123!",
        )
        assert admin_user.email == "admin@example.com"
        assert admin_user.is_active is True
        assert admin_user.is_verified is True
        assert admin_user.is_staff is True
        assert admin_user.is_superuser is True

    def test_flags_remain_separate_concepts(self):
        """Verifies is_active, is_verified, is_staff and is_superuser operate independently."""
        user = User.objects.create_user(
            email="custom@example.com",
            password="Password123!",
            is_active=False,
            is_verified=True,
            is_staff=False,
        )
        assert user.is_active is False
        assert user.is_verified is True
        assert user.is_staff is False
        assert user.is_superuser is False

    def test_helper_methods(self):
        """Tests full_name, short_name, and string representation."""
        user = User.objects.create_user(
            email="john.doe@example.com",
            password="Password123!",
            first_name="John",
            last_name="Doe",
        )
        assert user.get_full_name() == "John Doe"
        assert user.get_short_name() == "John"
        assert str(user) == "john.doe@example.com"
