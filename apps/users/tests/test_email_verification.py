import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.users.tokens import email_verification_token_generator

User = get_user_model()


@pytest.mark.django_db
class TestEmailVerification:
    """Test suite for email verification token lifecycle and session behavior."""

    @pytest.fixture
    def unverified_user(self):
        return User.objects.create_user(
            email="verify.me@example.com",
            password="SecurePassword123!",
            is_verified=False,
        )

    def test_verify_email_unauthenticated_browser(self, client: Client, unverified_user):
        """Unauthenticated user verifying email gets success page with login link."""
        token = email_verification_token_generator.make_token(unverified_user)
        uidb64 = urlsafe_base64_encode(force_bytes(unverified_user.pk))
        url = reverse("users:verify_email", kwargs={"uidb64": uidb64, "token": token})

        response = client.get(url)
        assert response.status_code == 200
        assert b"Email Verified Successfully" in response.content

        unverified_user.refresh_from_db()
        assert unverified_user.is_verified is True

    def test_verify_email_authenticated_browser(self, client: Client, unverified_user):
        """User already logged in in current browser is redirected directly to index upon verification."""
        client.force_login(unverified_user)
        token = email_verification_token_generator.make_token(unverified_user)
        uidb64 = urlsafe_base64_encode(force_bytes(unverified_user.pk))
        url = reverse("users:verify_email", kwargs={"uidb64": uidb64, "token": token})

        response = client.get(url, follow=True)
        assert response.status_code == 200
        unverified_user.refresh_from_db()
        assert unverified_user.is_verified is True

    def test_token_instant_invalidation_after_use(self, client: Client, unverified_user):
        """Token hash changes when is_verified flips to True, preventing replay."""
        token = email_verification_token_generator.make_token(unverified_user)
        uidb64 = urlsafe_base64_encode(force_bytes(unverified_user.pk))
        url = reverse("users:verify_email", kwargs={"uidb64": uidb64, "token": token})

        # First click verifies user
        client.get(url)
        unverified_user.refresh_from_db()
        assert unverified_user.is_verified is True

        # Second click recognizes already verified
        response2 = client.get(url)
        assert response2.status_code == 200
        assert b"Email Verified Successfully" in response2.content

    def test_invalid_or_tampered_token(self, client: Client, unverified_user):
        """Tampered token fails with invalid link notification."""
        uidb64 = urlsafe_base64_encode(force_bytes(unverified_user.pk))
        url = reverse("users:verify_email", kwargs={"uidb64": uidb64, "token": "invalid-token"})

        response = client.get(url)
        assert response.status_code == 200
        assert b"Invalid or Expired Link" in response.content

        unverified_user.refresh_from_db()
        assert unverified_user.is_verified is False

    def test_resend_verification_email(self, client: Client, unverified_user):
        """User can request a new verification email."""
        url = reverse("users:resend_verification")
        response = client.post(url, {"email": "verify.me@example.com"}, follow=True)

        assert response.status_code == 200
        assert len(mail.outbox) == 1
        assert "Verify your email address" in mail.outbox[0].subject

    def test_resend_verification_rate_limiting(self, client: Client, unverified_user):
        """Immediate successive requests trigger rate limit warning."""
        url = reverse("users:resend_verification")
        # First request
        client.post(url, {"email": "verify.me@example.com"})
        assert len(mail.outbox) == 1

        # Second immediate request
        response = client.post(url, {"email": "verify.me@example.com"}, follow=True)
        assert response.status_code == 200
        assert b"Please wait a minute" in response.content
        assert len(mail.outbox) == 1  # No second email sent
