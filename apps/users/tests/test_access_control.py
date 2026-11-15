import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.users.decorators import verified_user_required

User = get_user_model()


@pytest.mark.django_db
class TestAccessControl:
    """Test suite ensuring unverified users cannot access protected functionality."""

    @pytest.fixture
    def unverified_user(self):
        return User.objects.create_user(
            email="unverified@example.com",
            password="Password123!",
            is_verified=False,
            is_active=True,
        )

    @pytest.fixture
    def verified_user(self):
        return User.objects.create_user(
            email="verified@example.com",
            password="Password123!",
            is_verified=True,
            is_active=True,
        )

    def test_unauthenticated_user_redirected_to_login(self, client: Client):
        """Anonymous user trying to access protected area is redirected to login with next param."""
        url = reverse("core:protected")
        response = client.get(url)

        assert response.status_code == 302
        assert response.url == f"/auth/login/?next={url}"

    def test_unverified_user_redirected_to_verification_required(
        self, client: Client, unverified_user
    ):
        """Logged-in user who is NOT verified cannot access protected area and is redirected."""
        client.force_login(unverified_user)
        url = reverse("core:protected")
        response = client.get(url)

        assert response.status_code == 302
        assert response.url == reverse("users:verification_required")

    def test_verified_user_can_access_protected_area(self, client: Client, verified_user):
        """Logged-in user who IS verified accesses protected area successfully."""
        client.force_login(verified_user)
        url = reverse("core:protected")
        response = client.get(url)

        assert response.status_code == 200
        assert b"Protected Storefront Area" in response.content
        assert b"Verified: True" in response.content

    def test_raise_exception_flag_raises_permission_denied(self, unverified_user):
        """When raise_exception=True, decorator raises PermissionDenied for unverified users."""

        @verified_user_required(raise_exception=True)
        def dummy_view(request):
            return HttpResponse("OK")

        rf = RequestFactory()
        request = rf.get("/dummy/")
        request.user = unverified_user

        with pytest.raises(PermissionDenied):
            dummy_view(request)
