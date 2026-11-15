from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest


class CaseInsensitiveEmailBackend(ModelBackend):
    """
    Authenticate against the custom User model using case-insensitive email.

    Mitigates user-enumeration timing attacks by computing password hash even
    when the email is not found in the database.
    """

    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        email: str | None = None,
        **kwargs: Any,
    ) -> Any:
        candidate_email = email or username
        if not candidate_email or not password:
            return None

        normalized_email = candidate_email.lower().strip()
        user_model = get_user_model()

        try:
            user = user_model.objects.get(email__iexact=normalized_email)
        except user_model.DoesNotExist:
            # Run dummy password check to defend against timing attacks
            user_model().set_password(password)
            return None
        except user_model.MultipleObjectsReturned:
            user = user_model.objects.filter(email__iexact=normalized_email).order_by("id").first()

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
