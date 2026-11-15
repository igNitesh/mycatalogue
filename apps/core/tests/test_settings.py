from django.conf import settings


def test_core_installed_apps():
    """Verify essential applications are installed."""
    assert "apps.core" in settings.INSTALLED_APPS
    assert "django.contrib.staticfiles" in settings.INSTALLED_APPS


def test_middleware_order():
    """Verify security middleware precedes staticfiles and sessions."""
    middleware = list(settings.MIDDLEWARE)
    security_index = middleware.index("django.middleware.security.SecurityMiddleware")
    whitenoise_index = middleware.index("whitenoise.middleware.WhiteNoiseMiddleware")
    assert security_index < whitenoise_index


def test_base_dir_resolution():
    """Ensure BASE_DIR correctly resolves to project root."""
    assert (settings.BASE_DIR / "manage.py").exists()
    assert (settings.BASE_DIR / "templates").is_dir()
