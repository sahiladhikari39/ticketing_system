import logging
import secrets
import string

from django.conf import settings
from django.core.mail import send_mail

from .notifications import run_in_background

logger = logging.getLogger(__name__)


def generate_temporary_password(length=14):
    """
    Uses `secrets`, not `random` -- `random` is a Mersenne Twister,
    predictable enough to eventually guess given enough output. It's
    fine for shuffling a deck of cards, not for issuing credentials.
    `secrets` is Python's own standard-library recommendation for
    exactly this use case.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def send_credentials_email(user, password, role_label, org_name=None):
    """
    Sends a brand-new account's login details. Account creation should
    NOT be rolled back just because the email failed to send (e.g. a
    transient hiccup once this points at a real provider) -- the
    account still exists and someone can hand the person their password
    another way. So failures here are logged, not raised.
    """
    org_line = f" at {org_name}" if org_name else ""
    message = (
        f"Hi {user.username},\n\n"
        f"An account has been created for you on Soori as a {role_label}{org_line}.\n\n"
        f"Username: {user.username}\n"
        f"Temporary password: {password}\n\n"
        f"Log in and change your password as soon as possible.\n"
    )
    def _send():
        """
        The blocking part. Runs off the request thread -- creating a
        staff member or customer previously waited the full ~1s SMTP
        round trip before the UI updated, because this called send_mail
        directly and so never picked up the async fix applied to
        notifications.
        """
        try:
            send_mail(
                subject="Your Soori account has been created",
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception as exc:
            # Deliberately NOT re-raised: the account genuinely was
            # created, and rolling that back over a mail hiccup would
            # be worse -- and by the time this runs the HTTP response
            # has already gone out anyway, so there's nobody to raise
            # to. Logging alone made a failed send easy to miss, so
            # this also prints the credentials: without them the new
            # account is stranded with a password nobody knows.
            logger.exception("Failed to send credentials email to %s", user.email)
            print(
                f"\n{'=' * 62}\n"
                f"  EMAIL FAILED TO SEND -- the account WAS still created.\n"
                f"{'=' * 62}\n"
                f"  To:       {user.email}\n"
                f"  Username: {user.username}\n"
                f"  Password: {password}\n"
                f"\n"
                f"  Reason: {type(exc).__name__}: {exc}\n"
                f"\n"
                f"  Check your email setup with:  python manage.py mail_check\n"
                f"{'=' * 62}\n"
            )

    run_in_background(_send)
