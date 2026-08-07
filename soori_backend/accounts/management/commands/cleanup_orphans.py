"""
Finds -- and optionally cleans up -- "orphaned" user accounts: login
accounts whose role says they should have a profile (Support Staff or
Sub-Client) but whose profile no longer exists.

These are leftovers from a bug where deleting someone from the Team
page removed only their profile, not their actual login account. The
result is an account that is INVISIBLE in the UI (nothing lists it,
because listing is driven by profiles) yet still holds its username
and email -- which is why re-registering the same person fails with
"That username is already taken".

That delete bug is fixed going forward, but the fix can't retroactively
clean up accounts already orphaned before it existed. That's what this
command is for.

Usage:
    python manage.py cleanup_orphans          # just LIST them, change nothing
    python manage.py cleanup_orphans --fix    # actually clean them up

Cleanup uses the same safe soft-delete as the Team page does now:
the login is disabled and the username/email are freed for reuse, but
the row is kept so any ticket or comment history pointing at that
person still resolves. See User.soft_delete().
"""

from django.core.management.base import BaseCommand

from accounts.models import Role, User


class Command(BaseCommand):
    help = "Find (and optionally clean up) login accounts whose role-profile is missing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Actually clean up the orphans found. Without this, the command only reports.",
        )

    def handle(self, *args, **options):
        orphans = []

        for user in User.objects.filter(role=Role.SUPPORT_STAFF, is_active=True):
            if not hasattr(user, "staff_profile"):
                orphans.append(user)

        for user in User.objects.filter(role=Role.SUB_CLIENT, is_active=True):
            if not hasattr(user, "sub_client_profile"):
                orphans.append(user)

        if not orphans:
            self.stdout.write(self.style.SUCCESS("No orphaned accounts found -- nothing to clean up."))
            return

        self.stdout.write(self.style.WARNING(f"Found {len(orphans)} orphaned account(s):"))
        for user in orphans:
            self.stdout.write(
                f"  - {user.username}  ({user.email or 'no email'})  "
                f"role={user.role}  client={user.client.name if user.client else 'none'}"
            )

        if not options["fix"]:
            self.stdout.write("")
            self.stdout.write("Nothing was changed. Re-run with --fix to clean these up:")
            self.stdout.write(self.style.NOTICE("    python manage.py cleanup_orphans --fix"))
            return

        for user in orphans:
            original = user.username
            user.soft_delete()
            self.stdout.write(self.style.SUCCESS(f"  Cleaned up '{original}' -- username and email are now free to reuse."))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Done. {len(orphans)} account(s) cleaned up."))
