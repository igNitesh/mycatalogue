import pytest
from django.contrib.auth import authenticate, get_user_model
from django.test import RequestFactory

User = get_user_model()


@pytest.mark.django_db
class TestAuthenticationBackend:
    """Explicit tests for CaseInsensitiveEmailBackend."""

    @pytest.fixture
    def user(self):
        return User.objects.create_user(
            email="merchant.seller@example.com",
            password="SecureMerchantPassword123!",
            is_active=True,
        )

    def test_case_insensitive_authentication(self, user):
        """User can authenticate with lowercase, uppercase, or mixed-case email."""
        rf = RequestFactory()
        request = rf.get("/")

        # Lowercase
        auth1 = authenticate(
            request,
            email="merchant.seller@example.com",
            password="SecureMerchantPassword123!",
        )
        assert auth1 == user

        # Uppercase
        auth2 = authenticate(
            request,
            email="MERCHANT.SELLER@EXAMPLE.COM",
            password="SecureMerchantPassword123!",
        )
        assert auth2 == user

        # Mixed Case
        auth3 = authenticate(
            request,
            email="Merchant.Seller@Example.Com",
            password="SecureMerchantPassword123!",
        )
        assert auth3 == user

    def test_authentication_invalid_password(self, user):
        """Incorrect password fails authentication."""
        rf = RequestFactory()
        request = rf.get("/")
        result = authenticate(
            request,
            email="merchant.seller@example.com",
            password="WrongPassword!",
        )
        assert result is None

    def test_authentication_non_existent_email(self):
        """Non-existent email returns None gracefully."""
        rf = RequestFactory()
        request = rf.get("/")
        result = authenticate(
            request,
            email="ghost@example.com",
            password="SomePassword123!",
        )
        assert result is None

    def test_inactive_user_cannot_authenticate(self, user):
        """Inactive user account is rejected by authentication backend."""
        user.is_active = False
        user.save(update_fields=["is_active"])

        rf = RequestFactory()
        request = rf.get("/")
        result = authenticate(
            request,
            email="merchant.seller@example.com",
            password="SecureMerchantPassword123!",
        )
        assert result is None
