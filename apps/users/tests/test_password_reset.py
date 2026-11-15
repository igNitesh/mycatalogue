import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

User = get_user_model()


@pytest.mark.django_db
class TestPasswordReset:
    """Test suite for password reset workflow and anti-enumeration."""

    @pytest.fixture
    def user(self):
        return User.objects.create_user(
            email="reset.user@example.com",
            password="OldPassword123!",
            is_active=True,
        )

    def test_request_reset_existing_user(self, client: Client, user):
        """Existing active user receives password reset email."""
        url = reverse("users:password_reset")
        response = client.post(url, {"email": "RESET.USER@example.com"})

        assert response.status_code == 200
        assert b"Check your email" in response.content
        assert len(mail.outbox) == 1
        assert "Reset your mycatalogue password" in mail.outbox[0].subject

    def test_request_reset_non_existent_email_anti_enumeration(self, client: Client):
        """Non-existent email returns generic success screen without sending email."""
        url = reverse("users:password_reset")
        response = client.post(url, {"email": "does.not.exist@example.com"})

        assert response.status_code == 200
        assert b"Check your email" in response.content
        assert len(mail.outbox) == 0

    def test_confirm_password_reset_success(self, client: Client, user):
        """Valid token allows user to set a new password."""
        token = default_token_generator.make_token(user)
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        url = reverse("users:password_reset_confirm", kwargs={"uidb64": uidb64, "token": token})

        # Submit new password
        response = client.post(
            url,
            {
                "new_password": "BrandNewPassword999!",
                "confirm_password": "BrandNewPassword999!",
            },
            follow=True,
        )
        assert response.status_code == 200
        assert b"Your password has been reset successfully." in response.content

        user.refresh_from_db()
        assert user.check_password("BrandNewPassword999!") is True
        assert user.check_password("OldPassword123!") is False

    def test_confirm_password_reset_invalid_token(self, client: Client, user):
        """Invalid or tampered token renders invalid link screen."""
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        url = reverse(
            "users:password_reset_confirm", kwargs={"uidb64": uidb64, "token": "invalid-token"}
        )

        response = client.get(url)
        assert response.status_code == 200
        assert b"Invalid or Expired Link" in response.content
