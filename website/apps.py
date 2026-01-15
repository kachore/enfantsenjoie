from django.apps import AppConfig


class WebsiteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'website'
    verbose_name = 'Site'

    def ready(self):  # pragma: no cover
        from . import signals  # noqa: F401
