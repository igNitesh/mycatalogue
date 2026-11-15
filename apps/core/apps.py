import sys

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self) -> None:
        """Initialize core application and runtime compatibility fixes."""
        # Python 3.14+ compatibility fix for Django BaseContext.__copy__
        if sys.version_info >= (3, 14):
            from django.template import context as django_context

            def _base_context_copy(self):
                duplicate = object.__new__(self.__class__)
                duplicate.__dict__.update(self.__dict__)
                duplicate.dicts = self.dicts[:]
                return duplicate

            django_context.BaseContext.__copy__ = _base_context_copy

