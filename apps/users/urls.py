from django.urls import path

from .views import (
    LoginView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
    ResendVerificationView,
    VerificationRequiredView,
    VerifyEmailView,
)

app_name = "users"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path(
        "verify-email/<str:uidb64>/<str:token>/",
        VerifyEmailView.as_view(),
        name="verify_email",
    ),
    path(
        "resend-verification/",
        ResendVerificationView.as_view(),
        name="resend_verification",
    ),
    path(
        "verification-required/",
        VerificationRequiredView.as_view(),
        name="verification_required",
    ),
    path(
        "password-reset/",
        PasswordResetRequestView.as_view(),
        name="password_reset",
    ),
    path(
        "password-reset-confirm/<str:uidb64>/<str:token>/",
        PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
]
