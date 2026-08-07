from django.contrib.auth.models import UserManager as DjangoUserManager


class UserManager(DjangoUserManager):
    """
    Django's `createsuperuser` command only ever sets fields in
    USERNAME_FIELD / REQUIRED_FIELDS interactively -- it doesn't know
    our `role` field exists, and it would otherwise leave it blank.
    A blank role fails our `soori_admin_has_no_client_others_require_client`
    CheckConstraint (blank != "soori_admin", but client is also null),
    so the INSERT would be rejected by the database.

    Overriding create_superuser to force role=soori_admin (and
    client=None) is the fix: a Django superuser IS conceptually a Soori
    Admin in this system, so this is also just... correct.
    """

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        from .models import Role  # local import avoids a circular import at module load time

        extra_fields.setdefault("role", Role.SOORI_ADMIN)
        extra_fields["client"] = None
        return super().create_superuser(username, email, password, **extra_fields)
