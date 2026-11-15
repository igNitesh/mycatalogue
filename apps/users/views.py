from typing import Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.tokens import default_token_generator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views import View

from .forms import (
    PasswordResetRequestForm,
    UserLoginForm,
    UserRegistrationForm,
    UserSetPasswordForm,
)
from .models import User
from .services import (
    check_rate_limit,
    register_user,
    reset_user_password,
    send_password_reset_email,
    send_verification_email,
    verify_email_token,
)


class RegisterView(View):
    """Handle new user registration."""

    def get(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated:
            return redirect("core:index")
        form = UserRegistrationForm()
        return render(request, "users/register.html", {"form": form})

    def post(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated:
            return redirect("core:index")

        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = register_user(
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data.get("first_name", ""),
                last_name=form.cleaned_data.get("last_name", ""),
                request=request,
            )
            # Store registered email in session for convenient resend capability
            request.session["registered_email"] = user.email
            messages.success(
                request,
                "Registration successful! Please check your email to verify your account before logging in.",
            )
            return render(
                request,
                "users/verification_sent.html",
                {"email": user.email},
            )

        return render(request, "users/register.html", {"form": form})


class LoginView(View):
    """Handle session authentication."""

    def get(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated:
            return redirect("core:index")
        form = UserLoginForm(request=request)
        return render(
            request,
            "users/login.html",
            {"form": form, "next": request.GET.get("next", "")},
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated:
            return redirect("core:index")

        form = UserLoginForm(request=request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)

            messages.success(request, f"Welcome back, {user.get_short_name()}!")
            redirect_to = request.POST.get("next") or getattr(
                settings, "LOGIN_REDIRECT_URL", "core:index"
            )
            return redirect(redirect_to)

        return render(
            request,
            "users/login.html",
            {"form": form, "next": request.POST.get("next", "")},
        )


class LogoutView(View):
    """Handle session termination."""

    def post(self, request: HttpRequest) -> HttpResponse:
        auth_logout(request)
        messages.info(request, "You have been logged out successfully.")
        return redirect("users:login")


class VerifyEmailView(View):
    """
    Handle email verification token link.

    Session Specification:
    - If already authenticated in current session: mark verified and redirect to index.
    - If unauthenticated (e.g. cross-device or new browser): mark verified and redirect
      to login with confirmation message.
    """

    def get(self, request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
        is_valid, user, status_code = verify_email_token(uidb64, token)

        if not is_valid or not user:
            return render(
                request,
                "users/verify_email_status.html",
                {
                    "success": False,
                    "title": "Invalid or Expired Link",
                    "message": "This verification link is invalid or has expired. Please request a new one.",
                },
            )

        if status_code == "already_verified":
            messages.info(request, "Your email address is already verified.")
        else:
            messages.success(
                request,
                "Your email has been successfully verified!",
            )

        # Session decision:
        if request.user.is_authenticated and request.user.pk == user.pk:
            return redirect("core:index")

        return render(
            request,
            "users/verify_email_status.html",
            {
                "success": True,
                "title": "Email Verified Successfully",
                "message": "Your email address has been verified. You may now log in to access all storefront features.",
            },
        )


class ResendVerificationView(View):
    """
    Resend verification email. Enforces session rate limiting and
    anti-enumeration protection.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        # Rate limit verification resend
        if not check_rate_limit(request, "resend_verification", cooldown_seconds=60):
            messages.warning(
                request,
                "Please wait a minute before requesting another verification email.",
            )
            return redirect("users:verification_required")

        # Determine target email
        target_email = ""
        if request.user.is_authenticated:
            target_email = request.user.email
        else:
            target_email = request.POST.get("email") or request.session.get("registered_email", "")

        if target_email:
            try:
                user = User.objects.get(email__iexact=target_email.lower().strip())
                if not user.is_verified and user.is_active:
                    send_verification_email(user, request=request)
            except User.DoesNotExist:
                pass  # Anti-enumeration

        messages.success(
            request,
            "If an unverified account exists for that email, a fresh verification link has been sent.",
        )
        return redirect("users:verification_required")


class VerificationRequiredView(View):
    """Gate page presented to unverified accounts attempting access to protected areas."""

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(
            request,
            "users/verification_required.html",
            {
                "email": request.user.email
                if request.user.is_authenticated
                else request.session.get("registered_email", "")
            },
        )


class PasswordResetRequestView(View):
    """Request password reset link."""

    def get(self, request: HttpRequest) -> HttpResponse:
        form = PasswordResetRequestForm()
        return render(request, "users/password_reset_request.html", {"form": form})

    def post(self, request: HttpRequest) -> HttpResponse:
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            if check_rate_limit(request, "password_reset", cooldown_seconds=60):
                send_password_reset_email(form.cleaned_data["email"], request=request)
            return render(
                request,
                "users/password_reset_done.html",
                {"email": form.cleaned_data["email"]},
            )
        return render(request, "users/password_reset_request.html", {"form": form})


class PasswordResetConfirmView(View):
    """Confirm password reset and set new password."""

    def get_user(self, uidb64: str) -> Any | None:
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            return User.objects.get(pk=uid, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return None

    def get(self, request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
        user = self.get_user(uidb64)
        if user is None or not default_token_generator.check_token(user, token):
            return render(
                request,
                "users/password_reset_invalid.html",
            )
        form = UserSetPasswordForm(user=user)
        return render(
            request,
            "users/password_reset_confirm.html",
            {"form": form, "uidb64": uidb64, "token": token},
        )

    def post(self, request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
        user = self.get_user(uidb64)
        if user is None or not default_token_generator.check_token(user, token):
            return render(request, "users/password_reset_invalid.html")

        form = UserSetPasswordForm(user=user, data=request.POST)
        if form.is_valid():
            reset_user_password(user, form.cleaned_data["new_password"])
            messages.success(
                request,
                "Your password has been reset successfully. Please log in with your new password.",
            )
            return redirect("users:login")

        return render(
            request,
            "users/password_reset_confirm.html",
            {"form": form, "uidb64": uidb64, "token": token},
        )
