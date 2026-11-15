from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """
    Generate and validate secure, HMAC-signed email verification tokens.

    Includes the user's primary key, current email verification state,
    password hash, and last login in the HMAC digest. Once the user is verified,
    the hash signature changes immediately, rendering used tokens invalid.
    """

    def _make_hash_value(self, user, timestamp: int) -> str:
        return f"{user.pk}{user.is_verified}{user.password}{user.last_login}{timestamp}"


email_verification_token_generator = EmailVerificationTokenGenerator()
