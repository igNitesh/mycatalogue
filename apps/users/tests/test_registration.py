import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestRegistration:
    """Test suite for user registration workflow."""

    def test_successful_registration(self, client: Client):
        """Registering a new account creates an unverified user and sends verification email."""
        url = reverse("users:register")
        data = {
            "email": "NewUser@Example.Com",
            "first_name": "New",
            "last_name": "User",
            "password": "StrongPassword987!",
            "password_confirm": "StrongPassword987!",
        }

        response = client.post(url, data)
        assert response.status_code == 200
        assert b"Check your inbox" in response.content

        user = User.objects.get(email="newuser@example.com")
        assert user.is_verified is False
        assert user.is_active is True
        assert user.check_password("StrongPassword987!") is True

        # Verify email was dispatched
        assert len(mail.outbox) == 1
        sent_email = mail.outbox[0]
        assert "Verify your email address" in sent_email.subject
        assert user.email in sent_email.to
        assert "/auth/verify-email/" in sent_email.body

    def test_duplicate_email_registration_rejected(self, client: Client):
        """Attempting to register with an existing email fails."""
        User.objects.create_user(
            email="existing@example.com",
            password="ExistingPassword123!",
        )

        url = reverse("users:register")
        data = {
            "email": "EXISTING@example.com",
            "password": "NewPassword123!",
            "password_confirm": "NewPassword123!",
        }

        response = client.post(url, data)
        assert response.status_code == 200
        assert b"An account with this email address already exists." in response.content

    def test_password_mismatch_rejected(self, client: Client):
        """Mismatched passwords return form validation error."""
        url = reverse("users:register")
        data = {
            "email": "mismatch@example.com",
            "password": "Password123!",
            "password_confirm": "DifferentPassword123!",
        }

        response = client.post(url, data)
        assert response.status_code == 200
        assert b"The two passwords do not match." in response.content
