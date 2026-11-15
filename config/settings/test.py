"""
Test settings for mycatalogue.

Optimized for test execution speed and isolation:
- Fast MD5 password hasher
- In-memory database support for unit tests
- Silenced logging during test runs
"""

from .base import *  # noqa: F403
from .base import STORAGES

DEBUG = False
SECRET_KEY = "django-insecure-test-key-for-automated-testing-only"

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

# Fast password hashing to speed up tests significantly
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Use in-memory SQLite if no specific DATABASE_URL is set in test environment
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# In tests, avoid manifest static file storage
STORAGES["staticfiles"] = {
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
}

# Silence logging during tests
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {
        "null": {
            "class": "logging.NullHandler",
        },
    },
    "root": {
        "handlers": ["null"],
    },
}
