from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        # Registers the UUID-primary-key check (core/checks.py) --
        # `core` isn't its own installed app, so this is the hook that
        # actually makes Django discover and run it. Import only, no
        # side effects beyond the @register() decorator firing.
        import core.checks  # noqa: F401
