from django.apps import apps
from django.core.checks import Warning, register
from django.db.models import FloatField, ForeignKey, OneToOneField, UUIDField

# Our own apps only -- Django's own internal tables (sessions, admin
# log entries, permissions/groups) are expected to use plain integers,
# and that's correct: those are local bookkeeping tables you'd never
# merge across separate database instances the way you would real
# business data (Clients, Users, Tickets, ...).
OUR_APPS = {"accounts", "clients", "tickets", "audit"}

# Field-name fragments that strongly suggest "this holds money" --
# heuristic, not exhaustive, but catches the overwhelmingly common
# naming patterns for a price/amount/fee/total column.
MONEY_NAME_HINTS = ("price", "amount", "cost", "fee", "total", "balance", "payment", "invoice")


def _pk_is_effectively_uuid(field):
    """
    True for a plain UUIDField, but ALSO true for a primary key that's
    a OneToOneField/ForeignKey pointing at something with a UUID PK --
    e.g. SupportStaffProfile.user is `OneToOneField(User, primary_key=True)`.
    That's not a mistake: the stored value there genuinely IS the
    related User's UUID, just reached through a relation field instead
    of a plain UUIDField declared directly on this model. Confirmed
    this exact case with a real (harmless) false-positive from this
    check before this fix -- worth knowing this class of edge case
    exists in Django's field system.
    """
    if isinstance(field, UUIDField):
        return True
    if isinstance(field, (OneToOneField, ForeignKey)):
        return isinstance(field.target_field, UUIDField)
    return False


@register()
def check_primary_keys_are_uuids(app_configs, **kwargs):
    """
    Runs on every `manage.py check` -- and therefore on `runserver`,
    `migrate`, and every test run too, since Django runs checks before
    all of those. Flags any of OUR OWN models whose primary key isn't
    a UUID (or a relation field pointing at one).

    This is the automated backstop for core.models.UUIDModel: even if
    a future model forgets to inherit from it, this surfaces the
    mistake immediately as a warning at startup, instead of silently
    shipping an auto-incrementing integer ID that would only reveal
    itself as a problem much later -- at the exact moment two
    databases actually need to be merged, when it's expensive to fix.
    """
    errors = []
    for model in apps.get_models():
        if model._meta.app_label not in OUR_APPS:
            continue
        if not _pk_is_effectively_uuid(model._meta.pk):
            errors.append(
                Warning(
                    f"{model._meta.app_label}.{model.__name__} has a non-UUID primary key "
                    f"({type(model._meta.pk).__name__}). Inherit from core.models.UUIDModel instead.",
                    id="core.W001",
                )
            )
    return errors


@register()
def check_money_fields_use_decimal(app_configs, **kwargs):
    """
    No money/currency field exists anywhere in this project yet
    (checked directly) -- this check exists so that changes the moment
    one is added, not sometime after a bug report about totals being
    off by a fraction of a cent.

    A FloatField is binary floating-point -- the same representation
    that makes 0.1 + 0.1 + ... (ten times) come out to
    0.9999999999999999 instead of exactly 1.0 (confirmed directly:
    that's a real, reproducible result, not a hypothetical). That kind
    of tiny error is invisible in a test but compounds over enough
    transactions to produce genuinely wrong totals. DecimalField
    stores an exact decimal value and doesn't have this problem --
    it's also what DRF serializes as a clean string like "10000.00"
    by default, rather than a raw float that can print misleadingly
    (confirmed: DecimalField -> '10000.00', FloatField -> 10000.0).

    Purely a naming heuristic (checks for "price"/"amount"/"cost"/etc
    in the field name) -- not exhaustive, but catches the overwhelming
    majority of real cases without needing to guess field intent from
    nothing.
    """
    errors = []
    for model in apps.get_models():
        if model._meta.app_label not in OUR_APPS:
            continue
        for field in model._meta.get_fields():
            if not isinstance(field, FloatField):
                continue
            if any(hint in field.name.lower() for hint in MONEY_NAME_HINTS):
                errors.append(
                    Warning(
                        f"{model._meta.app_label}.{model.__name__}.{field.name} looks like a money field "
                        f"but is a FloatField. Use models.DecimalField(max_digits=..., decimal_places=2) instead.",
                        id="core.W002",
                    )
                )
    return errors
