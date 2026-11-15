import time
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.http import HttpRequest
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .tokens import email_verification_token_generator

User = get_user_model()


def check_rate_limit(request: HttpRequest, action_key: str, cooldown_seconds: int = 60) -> bool:
    """
    Check if a sensitive action is within cooldown rate limits.
    Returns True if allowed, False if rate limited.
    """
    session_key = f"rate_limit_{action_key}"
    last_action_time = request.session.get(session_key)
    current_time = time.time()

    if last_action_time and (current_time - last_action_time) < cooldown_seconds:
        return False

    request.session[session_key] = current_time
    return True


def register_user(
    email: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
    request: HttpRequest | None = None,
) -> Any:
    """
    Create a new unverified user and send the initial verification email.
    """
    user = User.objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        is_verified=False,
        is_active=True,
    )
    send_verification_email(user, request=request)
    return user


def send_verification_email(user: Any, request: HttpRequest | None = None) -> bool:
    """
    Generate email verification token and send verification link.
    """
    token = email_verification_token_generator.make_token(user)
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))

    path = reverse("users:verify_email", kwargs={"uidb64": uidb64, "token": token})
    if request:
        verification_url = request.build_absolute_uri(path)
    else:
        verification_url = f"http://localhost:8000{path}"

    subject = "Verify your email address for mycatalogue"
    message = (
        f"Hello {user.get_short_name()},\n\n"
        f"Thank you for signing up with mycatalogue. Please verify your email by clicking the link below:\n\n"
        f"{verification_url}\n\n"
        f"This link will expire in 24 hours. If you did not create an account, you can safely ignore this email.\n"
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL
        if hasattr(settings, "DEFAULT_FROM_EMAIL")
        else "no-reply@mycatalogue.local",
        recipient_list=[user.email],
        fail_silently=False,
    )
    return True


def verify_email_token(uidb64: str, token: str) -> tuple[bool, Any | None, str]:
    """
    Validate verification token and activate verified status.

    Returns:
        (is_valid, user, status_code)
        status_code: "verified" | "already_verified" | "invalid_or_expired"
    """
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return False, None, "invalid_or_expired"

    if user.is_verified:
        return True, user, "already_verified"

    if email_verification_token_generator.check_token(user, token):
        user.is_verified = True
        user.save(update_fields=["is_verified", "updated_at"])
        return True, user, "verified"

    return False, None, "invalid_or_expired"


def send_password_reset_email(email: str, request: HttpRequest | None = None) -> None:
    """
    Dispatch password reset email if account exists.
    Maintains anti-enumeration safety: always executes silently.
    """
    normalized_email = email.lower().strip()
    try:
        user = User.objects.get(email__iexact=normalized_email, is_active=True)
    except User.DoesNotExist:
        # User does not exist or is inactive; return silently to prevent enumeration
        return

    token = default_token_generator.make_token(user)
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))

    path = reverse(
        "users:password_reset_confirm",
        kwargs={"uidb64": uidb64, "token": token},
    )
    if request:
        reset_url = request.build_absolute_uri(path)
    else:
        reset_url = f"http://localhost:8000{path}"

    subject = "Reset your mycatalogue password"
    message = (
        f"Hello {user.get_short_name()},\n\n"
        f"We received a request to reset your password. Click the link below to set a new password:\n\n"
        f"{reset_url}\n\n"
        f"This link will expire in 24 hours. If you did not make this request, please disregard this email.\n"
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL
        if hasattr(settings, "DEFAULT_FROM_EMAIL")
        else "no-reply@mycatalogue.local",
        recipient_list=[user.email],
        fail_silently=False,
    )


def reset_user_password(user: Any, new_password: str) -> None:
    """Set new password and save user."""
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
