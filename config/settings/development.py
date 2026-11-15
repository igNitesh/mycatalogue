"""
Development settings for mycatalogue.

Optimized for developer ergonomics:
- DEBUG enabled by default
- Unhashed static file serving for live reloading
- Console email backend
"""

from .base import *  # noqa: F403
from .base import STORAGES, env

DEBUG = env.bool("DEBUG", default=True)

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1", "0.0.0.0", "web", "testserver"],
)

CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:8000", "http://127.0.0.1:8000"],
)

# Email output to console in development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# In local development, avoid manifest hashing requirement on every template/CSS edit
STORAGES["staticfiles"] = {
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
}
