import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestLoginLogout:
    """Test suite for session-based login and logout workflows."""

    @pytest.fixture
    def user(self):
        return User.objects.create_user(
            email="shopper@example.com",
            password="ShopperPassword123!",
            is_active=True,
            is_verified=True,
        )

    def test_successful_login(self, client: Client, user):
        """User can log in with valid credentials."""
        url = reverse("users:login")
        response = client.post(
            url,
            {"email": "shopper@example.com", "password": "ShopperPassword123!"},
            follow=True,
        )
        assert response.status_code == 200
        assert "_auth_user_id" in client.session
        assert client.session["_auth_user_id"] == str(user.pk)

    def test_case_insensitive_login(self, client: Client, user):
        """User can log in with uppercase email."""
        url = reverse("users:login")
        response = client.post(
            url,
            {"email": "SHOPPER@EXAMPLE.COM", "password": "ShopperPassword123!"},
            follow=True,
        )
        assert response.status_code == 200
        assert "_auth_user_id" in client.session
        assert client.session["_auth_user_id"] == str(user.pk)

    def test_invalid_password_rejected(self, client: Client, user):
        """Wrong password fails login."""
        url = reverse("users:login")
        response = client.post(
            url,
            {"email": "shopper@example.com", "password": "WrongPassword!"},
        )
        assert response.status_code == 200
        assert b"Invalid email address or password." in response.content
        assert "_auth_user_id" not in client.session

    def test_inactive_user_cannot_log_in(self, client: Client, user):
        """Deactivated account receives inactive account error."""
        user.is_active = False
        user.save(update_fields=["is_active"])

        url = reverse("users:login")
        response = client.post(
            url,
            {"email": "shopper@example.com", "password": "ShopperPassword123!"},
        )
        assert response.status_code == 200
        assert "_auth_user_id" not in client.session

    def test_logout(self, client: Client, user):
        """Logout flushes session and redirects to login page."""
        client.force_login(user)
        assert "_auth_user_id" in client.session

        logout_url = reverse("users:logout")
        response = client.post(logout_url, follow=True)

        assert response.status_code == 200
        assert "_auth_user_id" not in client.session
        assert b"You have been logged out successfully." in response.content
