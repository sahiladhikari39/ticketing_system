"""
Creates a realistic demo dataset so you can log in as each of the 4
roles and see tenant scoping happen in front of you, instead of having
to build fixtures by hand.

Usage:
    python manage.py seed_demo

Safe to re-run: it deletes and recreates the same fixed set of demo
users/orgs each time (matched by username), rather than piling up
duplicates.

Every user's password is: demo12345
"""

import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Role, User
from audit.models import AuditLog
from clients.models import Client, StaffPermission, StaffRole, SubClientProfile, SupportStaffProfile
from clients.serializers import compute_subscription_end
from tickets.models import Ticket, TicketComment

DEMO_PASSWORD = "demo12345"


class Command(BaseCommand):
    help = "Seed demo Soori/Acme/Beta data across all 4 roles for manual testing."

    @transaction.atomic
    def handle(self, *args, **options):
        # Wipe the previous demo run so this command is idempotent.
        #
        # Deletes EVERY user belonging to the demo companies, not just a
        # hardcoded username list. The list-only version broke as soon
        # as anyone added staff through the UI: those extra people
        # survived, still referenced the company's roles, and blocked
        # the company deletion entirely.
        demo_clients = Client.objects.filter(name__in=["Acme Corp", "Beta LLC"])
        User.objects.filter(client__in=demo_clients).delete()
        User.objects.filter(username="soori_admin").delete()
        demo_clients.delete()

        soori_admin = User.objects.create_superuser(
            username="soori_admin", email="admin@soori.com", password=DEMO_PASSWORD,
        )
        self.stdout.write(self.style.SUCCESS(f"Created Soori Admin: {soori_admin.username}"))

        acme = Client.objects.create(
            name="Acme Corp",
            registered_by=soori_admin,
            plan="pro",
            status="active",
            subscription_period="1_year",
            subscription_start=datetime.date.today(),
            subscription_end=compute_subscription_end(datetime.date.today(), "1_year"),
        )
        beta = Client.objects.create(
            name="Beta LLC",
            registered_by=soori_admin,
            plan="basic",
            status="trial",
            subscription_period="1_month",
            subscription_start=datetime.date.today(),
            subscription_end=compute_subscription_end(datetime.date.today(), "1_month"),
        )
        self.stdout.write(self.style.SUCCESS(f"Created Clients: {acme.name}, {beta.name}"))

        # Every company starts with the two default roles. These are
        # ordinary editable rows, not hardcoded values -- a Service
        # Manager can rename them, change their permissions, or add
        # entirely new roles alongside them.
        roles = {}
        for company in (acme, beta):
            roles[(company.id, "dept")] = StaffRole.objects.create(
                client=company, name="Service Department", is_system=True,
                description="Coordinates incoming tickets and assigns Field Engineers.",
                permissions=[
                    StaffPermission.ASSIGN_TICKETS,
                    StaffPermission.VIEW_REPORTS,
                    StaffPermission.APPROVE_SERVICE_REPORT,
                    StaffPermission.VIEW_ALL_SERVICE_REPORTS,
                    StaffPermission.VIEW_KNOWLEDGE_BASE,
                ],
            )
            roles[(company.id, "eng")] = StaffRole.objects.create(
                client=company, name="Field Engineer", is_system=True,
                description="Attends the customer site and resolves the ticket.",
                permissions=[
                    StaffPermission.RECEIVE_TICKETS,
                    StaffPermission.VIEW_REPORTS,
                    StaffPermission.WRITE_SERVICE_REPORT,
                ],
            )
        self.stdout.write(self.style.SUCCESS("Created default staff roles for both companies"))

        acme_admin = User.objects.create_user(
            username="acme_admin", email="admin@acme.com", password=DEMO_PASSWORD,
            role=Role.CLIENT_ADMIN, client=acme,
        )
        acme_agent_user = User.objects.create_user(
            username="acme_agent", email="agent@acme.com", password=DEMO_PASSWORD,
            role=Role.SUPPORT_STAFF, client=acme,
        )
        SupportStaffProfile.objects.create(
            user=acme_agent_user, role=roles[(acme.id, "eng")],
            department="Field Service", service_area="Kathmandu",
        )

        acme_senior_user = User.objects.create_user(
            username="acme_senior_agent", email="senior@acme.com", password=DEMO_PASSWORD,
            role=Role.SUPPORT_STAFF, client=acme,
        )
        SupportStaffProfile.objects.create(
            user=acme_senior_user, role=roles[(acme.id, "dept")],
            department="Service Desk",
        )

        acme_cust1 = User.objects.create_user(
            username="acme_customer1", email="cust1@acmeclient.com", password=DEMO_PASSWORD,
            role=Role.SUB_CLIENT, client=acme,
        )
        SubClientProfile.objects.create(user=acme_cust1, company_name="Widgets Inc", service_area="Kathmandu")

        acme_cust2 = User.objects.create_user(
            username="acme_customer2", email="cust2@acmeclient.com", password=DEMO_PASSWORD,
            role=Role.SUB_CLIENT, client=acme,
        )
        SubClientProfile.objects.create(user=acme_cust2, company_name="Gadgets LLC", service_area="Pokhara")

        beta_admin = User.objects.create_user(
            username="beta_admin", email="admin@beta.com", password=DEMO_PASSWORD,
            role=Role.CLIENT_ADMIN, client=beta,
        )
        beta_agent_user = User.objects.create_user(
            username="beta_agent", email="agent@beta.com", password=DEMO_PASSWORD,
            role=Role.SUPPORT_STAFF, client=beta,
        )
        SupportStaffProfile.objects.create(user=beta_agent_user, role=roles[(beta.id, "eng")], service_area="Lalitpur")

        beta_cust1 = User.objects.create_user(
            username="beta_customer1", email="cust1@betaclient.com", password=DEMO_PASSWORD,
            role=Role.SUB_CLIENT, client=beta,
        )
        SubClientProfile.objects.create(user=beta_cust1, company_name="Beta Test Co", service_area="Lalitpur")

        self.stdout.write(self.style.SUCCESS("Created Support Staff and Sub-Clients for both orgs"))

        t1 = Ticket.objects.create(
            title="Cannot reset my password",
            description="The reset email never arrives.",
            product_or_service="Acme Web App",
            priority="high",
            created_by=acme_cust1,
            assigned_to=acme_agent_user,
        )
        TicketComment.objects.create(
            ticket=t1, author=acme_cust1, body="Tried 3 times, still nothing in my inbox.",
        )
        TicketComment.objects.create(
            ticket=t1, author=acme_agent_user, body="Checking your account now.",
        )
        TicketComment.objects.create(
            ticket=t1, author=acme_agent_user,
            body="Internal: their email domain is on our bounce list, escalate to infra.",
            is_internal_note=True,
        )

        t2 = Ticket.objects.create(
            title="Feature request: dark mode",
            description="Would love a dark theme option.",
            product_or_service="Acme Web App",
            priority="low",
            created_by=acme_cust2,
        )

        t3 = Ticket.objects.create(
            title="Billing question",
            description="Why was I charged twice this month?",
            product_or_service="Beta Platform",
            priority="urgent",
            created_by=beta_cust1,
            assigned_to=beta_agent_user,
        )

        self.stdout.write(self.style.SUCCESS(f"Created {Ticket.objects.count()} tickets total"))

        AuditLog.objects.create(
            client=acme, actor=acme_admin, action="staff.role_changed",
            target_type="SupportStaffProfile", target_id=str(acme_senior_user.id),
            metadata={"new_role": "senior_agent"},
        )
        AuditLog.objects.create(
            client=beta, actor=beta_admin, action="ticket.assigned",
            target_type="Ticket", target_id=str(t3.id),
            metadata={"assigned_to": "beta_agent"},
        )

        self.stdout.write(self.style.SUCCESS("\nDone. All demo users share the password: demo12345"))
        self.stdout.write("  soori_admin       (Soori Admin, sees everything)")
        self.stdout.write("  acme_admin        (Service Manager @ Acme Corp)")
        self.stdout.write("  acme_agent        (Field Engineer @ Acme Corp, Kathmandu)")
        self.stdout.write("  acme_senior_agent (Service Department @ Acme Corp)")
        self.stdout.write("  acme_customer1    (Sub-Client @ Acme Corp, owns ticket 'Cannot reset my password')")
        self.stdout.write("  acme_customer2    (Sub-Client @ Acme Corp, owns ticket 'Feature request: dark mode')")
        self.stdout.write("  beta_admin        (Service Manager @ Beta LLC)")
        self.stdout.write("  beta_agent        (Field Engineer @ Beta LLC, Lalitpur)")
        self.stdout.write("  beta_customer1    (Sub-Client @ Beta LLC, owns ticket 'Billing question')")
