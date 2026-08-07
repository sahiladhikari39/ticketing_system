"""
Tells you exactly how email is configured right now, and optionally
sends a real test message so you can confirm delivery end to end.

Usage:
    python manage.py mail_check
    python manage.py mail_check --to you@example.com

Why this exists: "no email arrived" has several very different causes
that look identical from the outside -- no .env file at all (so it's
printing to the terminal instead of sending), a .env that isn't being
read, or a real send that Gmail rejected. This distinguishes them in
one command instead of guessing.
"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

CONSOLE_BACKEND = "django.core.mail.backends.console.EmailBackend"


class Command(BaseCommand):
    help = "Report the active email configuration and optionally send a test message."

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            help="Send a real test email to this address. Without it, this command only reports config.",
        )

    def handle(self, *args, **options):
        backend = settings.EMAIL_BACKEND
        self.stdout.write("")
        self.stdout.write(f"EMAIL_BACKEND:    {backend}")
        self.stdout.write(f"EMAIL_HOST_USER:  {settings.EMAIL_HOST_USER or '(not set)'}")
        password_set = bool(getattr(settings, "EMAIL_HOST_PASSWORD", ""))
        self.stdout.write(f"Password set:     {'yes' if password_set else 'no'}")
        self.stdout.write(f"DEFAULT_FROM:     {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write("")

        if getattr(settings, "EMAIL_CREDENTIALS_ARE_PLACEHOLDERS", False):
            self.stdout.write(self.style.ERROR(
                "Your .env still contains the PLACEHOLDER values from .env.example."
            ))
            self.stdout.write(
                "That usually means .env got overwritten by a copy of the template.\n"
                "Real emails can't send until you put your actual Gmail address and\n"
                "App Password back in .env. Falling back to terminal printing for now."
            )
            self.stdout.write("")

        if backend == CONSOLE_BACKEND:
            self.stdout.write(self.style.WARNING(
                "Emails are being PRINTED TO THIS TERMINAL, not actually sent."
            ))
            self.stdout.write(
                "That's the automatic fallback when EMAIL_HOST_USER / EMAIL_HOST_PASSWORD\n"
                "aren't set. To send real email, EDIT the .env file next to manage.py\n"
                "and add these two lines:\n"
                "\n"
                "    EMAIL_HOST_USER=you@gmail.com\n"
                "    EMAIL_HOST_PASSWORD=your16charapppassword\n"
                "\n"
                "The password must be a Google APP PASSWORD, not your normal Gmail\n"
                "password (myaccount.google.com/apppasswords). Then restart runserver.\n"
                "\n"
                "Edit .env directly rather than copying .env.example over it -- that\n"
                "copy replaces any real credentials already in there."
            )
            self.stdout.write("")
            return

        self.stdout.write(self.style.SUCCESS("Real SMTP sending is ACTIVE -- emails will not appear in this terminal."))
        self.stdout.write("")

        to_address = options.get("to")
        if not to_address:
            self.stdout.write("To actually test delivery, re-run with an address:")
            self.stdout.write(self.style.NOTICE("    python manage.py mail_check --to you@example.com"))
            self.stdout.write("")
            return

        self.stdout.write(f"Sending a test email to {to_address} ...")
        try:
            send_mail(
                subject="Soori test email",
                message="If you're reading this, Soori's email configuration is working correctly.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to_address],
                fail_silently=False,
            )
        except Exception as exc:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(f"FAILED: {type(exc).__name__}: {exc}"))
            self.stdout.write("")
            self.stdout.write("Most common causes, in order:")
            self.stdout.write("  1. Using your normal Gmail password instead of an App Password.")
            self.stdout.write("     Google blocks the former for apps. Generate one at:")
            self.stdout.write("     https://myaccount.google.com/apppasswords")
            self.stdout.write("     (only available once 2-Step Verification is ON)")
            self.stdout.write("  2. App Password pasted WITH spaces -- it must have none.")
            self.stdout.write("  3. EMAIL_HOST_USER isn't the same Gmail account the App Password came from.")
            self.stdout.write("")
            return

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Sent. Check the inbox for {to_address} (including spam)."))
        self.stdout.write("")
