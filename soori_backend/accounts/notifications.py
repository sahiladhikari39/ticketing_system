import logging
import threading

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def run_in_background(fn, *args, **kwargs):
    """
    Runs `fn` off the request thread, so a slow network call (SMTP,
    typically ~1s per message) doesn't hold up the HTTP response.

    Shared by every email path in the app -- both the notification
    helper below and the account-provisioning email in
    provisioning.py, which previously called send_mail directly and so
    missed the async fix entirely. One dispatcher means there's exactly
    one place that decides sync vs async, and no path can quietly
    forget to use it.

    Honours EMAIL_SEND_ASYNC so tests can run synchronously and check
    mail.outbox deterministically instead of racing the thread.
    """
    if not getattr(settings, "EMAIL_SEND_ASYNC", True):
        fn(*args, **kwargs)
        return
    # daemon=True so a pending send never blocks process shutdown --
    # important for clean restarts and deploys.
    threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()


def _deliver(to_email, subject, message):
    """The actual blocking send. Always called on a background thread."""
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            fail_silently=False,
        )
    except Exception as exc:
        # Logged AND printed. This runs off the request thread, so
        # there's no HTTP response left to attach an error to -- and
        # once sending became async, a silent failure meant no email,
        # no console output, and no error anywhere the person would
        # look. Printing makes it impossible to miss in the server
        # terminal, matching what the account-provisioning email
        # already did.
        logger.exception("Failed to send email notification to %s", to_email)
        print(
            f"\n{'=' * 62}\n"
            f"  EMAIL FAILED TO SEND\n"
            f"{'=' * 62}\n"
            f"  To:      {to_email}\n"
            f"  Subject: {subject}\n"
            f"\n"
            f"  Reason: {type(exc).__name__}: {exc}\n"
            f"\n"
            f"  Check your setup with:  python manage.py mail_check\n"
            f"{'=' * 62}\n"
        )


def send_email_notification(to_email, subject, message):
    """
    Thin wrapper so every notification email in the app goes through
    ONE place. Uses whatever EMAIL_BACKEND is configured (the console
    backend today -- see settings.py) -- swapping to a real provider
    later is a one-line settings change, nothing here has to change.

    Sends on a BACKGROUND THREAD, which matters a lot in practice.
    Real SMTP takes roughly a second per message, and several actions
    here notify multiple people at once -- assigning a ticket emails
    the engineer AND every service manager. Sending inline meant the
    HTTP response couldn't return until all of them finished, so the
    UI sat frozen for ~2 seconds on what should be an instant action.
    Measured before this change: 1.75s for a single assignment.

    Threads rather than a task queue (Celery/Redis) on purpose: a queue
    is the more robust answer at high volume, but it needs another
    service running and another thing to deploy and monitor. At this
    scale a thread gets essentially all of the benefit for none of that
    operational cost.

    The honest tradeoff: if the server process is killed mid-send, an
    in-flight email is lost with no retry. That's acceptable for
    notifications ("you've been assigned a ticket") which are
    convenience, not correctness -- the assignment itself is already
    safely in the database either way. Worth revisiting if email ever
    becomes something the business depends on being delivered.
    """
    if not to_email:
        return

    run_in_background(_deliver, to_email, subject, message)


def send_sms_notification(to_phone, message):
    """
    No real SMS provider is wired up yet -- this function is the seam
    where one goes later (Twilio, a local telecom gateway, etc.).
    Every OTHER part of the app that wants to send an SMS calls this
    one function; when a real provider exists, only this function's
    body changes, nothing that calls it.

    For now, it does the one useful thing it genuinely can: print
    clearly to the console, the same way the console email backend
    does, so you can see exactly what would have been sent, and to
    which number, without needing a real SMS account to test the flow.
    """
    if not to_phone:
        return
    print(f"\n=== SMS (no provider configured yet) ===\nTo: {to_phone}\n{message}\n===\n")
    logger.info("SMS (no provider configured) to %s: %s", to_phone, message)


def notify_ticket_assigned(ticket, assigned_staff):
    """
    Notifies two audiences the moment a ticket is assigned (or
    reassigned) to a Support Staff member:
    1. The Support Staff member themselves -- "you've got a new ticket"
    2. Every Client Admin at that company -- "here's who's handling it"

    Called from TicketViewSet.perform_update() at the exact point a
    real assignment change is detected -- not on every update, only
    when assigned_to actually changes to someone.
    """
    from accounts.models import Role, User

    subject = f"Soori: ticket assigned - {ticket.title}"

    staff_message = (
        f"Hi {assigned_staff.username},\n\n"
        f"You've been assigned a ticket:\n\n"
        f"  \"{ticket.title}\"\n"
        f"  Priority: {ticket.get_priority_display()}\n"
        f"  Raised by: {ticket.created_by.username}\n\n"
        f"Log in to Soori to view the full details and respond.\n"
    )
    send_email_notification(assigned_staff.email, subject, staff_message)
    staff_profile = getattr(assigned_staff, "staff_profile", None)
    send_sms_notification(getattr(staff_profile, "phone", None), staff_message)

    admin_message = (
        f"Ticket \"{ticket.title}\" at {ticket.client.name} has been "
        f"assigned to {assigned_staff.username}.\n"
    )
    client_admins = User.objects.filter(client=ticket.client, role=Role.CLIENT_ADMIN)
    for admin in client_admins:
        send_email_notification(admin.email, subject, admin_message)

    # No per-Client-Admin phone number exists yet (User itself has no
    # phone field -- only role-specific profiles do, and Client Admin
    # doesn't have one of those). The Client's own contact phone is the
    # best available number today; a dedicated Client Admin phone field
    # would be a reasonable next step if this needs to be more precise.
    if ticket.client.contact_person_phone:
        send_sms_notification(ticket.client.contact_person_phone, admin_message)


def send_password_reset_code(user, code):
    """
    Sends the 6-digit reset code.

    No link in here at all, deliberately -- a link has to embed an
    absolute URL to the frontend, which breaks whenever the frontend
    moves and looks broken in development. A code works identically
    regardless of where anything is hosted.
    """
    message = (
        f"Hi {user.username},\n\n"
        f"Someone (hopefully you) asked to reset the password on your Soori account.\n\n"
        f"Your verification code is:\n\n"
        f"    {code}\n\n"
        f"Enter it on the password reset page to choose a new password.\n"
        f"The code expires in 10 minutes and can only be used once.\n\n"
        f"If you didn't ask for this, you can safely ignore this email -- "
        f"your password hasn't changed.\n"
    )
    send_email_notification(user.email, "Your Soori password reset code", message)


def notify_service_report_released(report):
    """
    Tells the customer their service summary is available.

    Deliberately does NOT include the summary text in the email body.
    The summary can reference equipment, faults, and site details, and
    email isn't a place to assume privacy -- inboxes get shared,
    forwarded, and left open. A short "it's ready, log in to read it"
    keeps the content behind the login that already governs it.
    """
    customer = report.ticket.created_by
    message = (
        f"Hi {customer.username},\n\n"
        f"The service summary for your ticket is now available:\n\n"
        f"  \"{report.ticket.title}\"\n\n"
        f"Log in to Soori to read it.\n"
    )
    send_email_notification(customer.email, f"Service summary ready - {report.ticket.title}", message)


def notify_history_access_requested(history_request):
    """Tells the Service Manager/Department a new access request needs a decision."""
    from clients.models import StaffPermission
    from accounts.models import User

    subject = f"Access request: {history_request.requested_by.username} needs {history_request.customer.username}'s history"
    message = (
        f"{history_request.requested_by.username} is working ticket \"{history_request.ticket.title}\" "
        f"and has requested temporary access to {history_request.customer.username}'s service history"
        f"{f' -- reason given: {history_request.reason}' if history_request.reason else ''}.\n\n"
        f"Log in to Soori to approve or deny this request.\n"
    )
    approvers = User.objects.filter(client=history_request.ticket.client, role="client_admin")
    for approver in approvers:
        send_email_notification(approver.email, subject, message)
    # Anyone with an approval-capable staff role should hear about this
    # too, not only the Client Admin.
    from clients.models import SupportStaffProfile
    staff_approvers = SupportStaffProfile.objects.filter(
        user__client=history_request.ticket.client
    ).select_related("user", "role")
    for profile in staff_approvers:
        if profile.role and profile.role.has_perm(StaffPermission.APPROVE_SERVICE_REPORT):
            send_email_notification(profile.user.email, subject, message)


def notify_history_access_approved(history_request, code, secret):
    """
    Sends the engineer their temporary login. Same reasoning as every
    other credential email in this project: printed here (console
    backend) until real SMTP is configured, same as account creation.
    """
    message = (
        f"Hi {history_request.requested_by.username},\n\n"
        f"Your request for {history_request.customer.username}'s service history has been approved.\n\n"
        f"Temporary login:\n"
        f"  Username: {code.username}\n"
        f"  Code: {secret}\n\n"
        f"This expires at {code.expires_at.strftime('%Y-%m-%d %H:%M')} and can only be used until then.\n"
    )
    send_email_notification(
        history_request.requested_by.email, "Your access request was approved", message
    )


def notify_history_access_denied(history_request):
    message = (
        f"Hi {history_request.requested_by.username},\n\n"
        f"Your request for {history_request.customer.username}'s service history was not approved.\n"
    )
    send_email_notification(
        history_request.requested_by.email, "Your access request was not approved", message
    )


def notify_access_code_issued(code, secret):
    """
    Emails a freshly-issued access code directly to whoever it's for --
    an intern's personal email, say -- instead of relying entirely on
    the issuer relaying it by hand from the one-time on-screen reveal.
    Only sent when an email was actually provided at issue time.
    """
    if not code.recipient_email:
        return
    message = (
        f"You've been given temporary access to Soori.\n\n"
        f"  Username: {code.username}\n"
        f"  Code: {secret}\n\n"
        f"This expires at {code.expires_at.strftime('%Y-%m-%d %H:%M')} and can only be used until then.\n\n"
        f"Enter these at the access code login page (not the regular account login).\n"
    )
    send_email_notification(code.recipient_email, f"Your Soori access code: {code.label}", message)
