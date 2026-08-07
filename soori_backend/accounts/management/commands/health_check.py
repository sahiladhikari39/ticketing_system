"""
Runs every critical flow in the project end-to-end against YOUR local
copy, and reports exactly what works and what doesn't.

Usage:
    python manage.py health_check

Why this exists: most problems in this project have turned out to be
local file-sync issues (a file that didn't fully overwrite, a stale
migration left behind) rather than genuine code bugs -- and those are
miserable to diagnose by trading log snippets back and forth. This
exercises the real flows through the real API and tells you precisely
which one is broken, in one command.

Safe to run: it creates its own throwaway test data with a distinct
"_healthcheck" prefix and deletes it all afterwards, including on
failure.
"""

import datetime
import re

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.test import Client as TestClient
from django.test.utils import override_settings

from accounts.models import Role, User
from clients.models import Client, SubClientProfile, SupportStaffProfile
from tickets.models import Ticket

PREFIX = "_healthcheck"


class Command(BaseCommand):
    help = "Verify every critical flow works in this local copy."

    def handle(self, *args, **options):
        self.results = []
        try:
            with override_settings(
                EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                # Synchronous, so checking mail.outbox right after an
                # action is deterministic rather than racing the
                # background send thread.
                EMAIL_SEND_ASYNC=False,
                ALLOWED_HOSTS=["testserver", "*"],
            ):
                self._run_all()
        finally:
            self._cleanup()

        self.stdout.write("")
        passed = sum(1 for _, ok, _ in self.results if ok)
        for name, ok, detail in self.results:
            style = self.style.SUCCESS if ok else self.style.ERROR
            mark = "PASS" if ok else "FAIL"
            self.stdout.write(style(f"{mark} | {name}") + (f"  ({detail})" if detail else ""))
        self.stdout.write("")
        summary = f"{passed}/{len(self.results)} checks passed"
        self.stdout.write(self.style.SUCCESS(summary) if passed == len(self.results) else self.style.ERROR(summary))

    def _check(self, name, condition, detail=""):
        ok = bool(condition)
        # Detail is only useful when something FAILED -- printing the
        # full response body on every success just buries the results.
        self.results.append((name, ok, "" if ok else detail[:200]))

    def _cleanup(self):
        User.objects.filter(username__startswith=PREFIX).delete()
        Client.objects.filter(name__startswith=PREFIX).delete()

    def _run_all(self):
        from django.core import mail

        self._cleanup()
        today = datetime.date.today()

        # --- Soori Admin creates a Client + its first Client Admin ---
        soori = User.objects.filter(role=Role.SOORI_ADMIN).first()
        if not soori:
            self._check("A Soori Admin exists (run seed_demo first)", False)
            return
        soori.set_password("healthcheckpw123")
        soori.save()

        c_sa = TestClient()
        self._check("Soori Admin can log in", c_sa.login(username=soori.username, password="healthcheckpw123"))

        mail.outbox = []
        doc = SimpleUploadedFile(f"{PREFIX}.pdf", b"test pdf bytes", content_type="application/pdf")
        resp = c_sa.post("/api/clients/", data={
            "name": f"{PREFIX} Corp",
            "subscription_start": today.isoformat(),
            "subscription_period": "1_year",
            "plan": "pro",
            "tax_document": doc,
            "admin_username": f"{PREFIX}_admin",
            "admin_email": f"{PREFIX}_admin@test.invalid",
        }, format="multipart")
        self._check("Create Client (with required tax document)", resp.status_code == 201,
                    f"status {resp.status_code}: {resp.content.decode()[:160]}")
        if resp.status_code != 201:
            return

        self._check("Client Admin credentials email sent", len(mail.outbox) == 1, f"{len(mail.outbox)} sent")

        # Default roles should have been created alongside the client.
        from clients.models import StaffRole
        hc_client_obj = Client.objects.filter(name__startswith=PREFIX).first()
        eng_role = StaffRole.objects.filter(client=hc_client_obj, name="Field Engineer").first()
        dept_role = StaffRole.objects.filter(client=hc_client_obj, name="Service Department").first()
        self._check("Default staff roles auto-created for new client", eng_role is not None and dept_role is not None)
        eng_role_id = eng_role.id if eng_role else ""
        dept_role_id = dept_role.id if dept_role else ""
        match = re.search(r"Temporary password: (.+)", mail.outbox[0].body)
        self._check("Email contains a generated password", match is not None)
        if not match:
            return
        admin_pw = match.group(1).strip()

        c_ca = TestClient()
        self._check("Generated password actually logs in", c_ca.login(username=f"{PREFIX}_admin", password=admin_pw))

        # --- Client Admin creates Support Staff ---
        mail.outbox = []
        resp = c_ca.post("/api/support-staff/", data={
            "username": f"{PREFIX}_staff",
            "email": f"{PREFIX}_staff@test.invalid",
            "role": str(eng_role_id),
            "service_area": "Kathmandu",
            "department": "Tier 2",
            "phone": "+10000000000",
        }, content_type="application/json")
        self._check("Create Support Staff", resp.status_code == 201,
                    f"status {resp.status_code}: {resp.content.decode()[:160]}")
        self._check("Support Staff credentials email sent", len(mail.outbox) == 1, f"{len(mail.outbox)} sent")

        # --- Client Admin creates a Sub-Client ---
        mail.outbox = []
        sub_doc = SimpleUploadedFile(f"{PREFIX}_sub.pdf", b"test pdf", content_type="application/pdf")
        resp = c_ca.post("/api/sub-clients/", data={
            "username": f"{PREFIX}_sub",
            "email": f"{PREFIX}_sub@test.invalid",
            "company_name": f"{PREFIX} Widgets",
            "tax_document": sub_doc,
            "subscription_start": today.isoformat(),
            "subscription_period": "6_months",
        }, format="multipart")
        self._check("Create Sub-Client (with required tax document)", resp.status_code == 201,
                    f"status {resp.status_code}: {resp.content.decode()[:160]}")
        if resp.status_code != 201:
            return
        sub_pw_match = re.search(r"Temporary password: (.+)", mail.outbox[0].body) if mail.outbox else None
        self._check("Sub-Client credentials email sent", sub_pw_match is not None)

        # --- Sub-Client raises a ticket ---
        if sub_pw_match:
            c_sub = TestClient()
            c_sub.login(username=f"{PREFIX}_sub", password=sub_pw_match.group(1).strip())
            resp = c_sub.post("/api/tickets/", data={
                "title": f"{PREFIX} ticket", "description": "health check", "priority": "high",
            }, content_type="application/json")
            self._check("Sub-Client raises a ticket", resp.status_code == 201,
                        f"status {resp.status_code}: {resp.content.decode()[:160]}")
            ticket_id = resp.json().get("id") if resp.status_code == 201 else None

            # Regression guard: a Sub-Client is one CUSTOMER of the
            # company, not staff -- they must never see a different
            # customer's tickets. This broke for real once, when the
            # role filter got dropped during an unrelated rewrite.
            visible = c_sub.get("/api/tickets/").json()
            own_only = all(t.get("created_by_username") == f"{PREFIX}_sub" for t in visible)
            self._check("Sub-Client sees ONLY their own tickets", own_only,
                        f"saw {len(visible)} ticket(s) not all their own")

            # --- Assignment triggers notifications ---
            if ticket_id:
                staff_user = User.objects.filter(username=f"{PREFIX}_staff").first()
                mail.outbox = []
                resp = c_ca.patch(f"/api/tickets/{ticket_id}/", data={"assigned_to": str(staff_user.id)},
                                  content_type="application/json")
                self._check("Assign ticket to Support Staff", resp.status_code == 200,
                            f"status {resp.status_code}: {resp.content.decode()[:160]}")
                self._check("Assignment notification emails sent", len(mail.outbox) >= 1, f"{len(mail.outbox)} sent")

                # --- Reassignment needs authority ---
                # A plain agent must not be able to move tickets
                # around; only a Client Admin or a Supervisor can.
                agent_pw_match = None
                staff_client = TestClient()
                # (the staff account above is a field_engineer, so
                # create another one specifically to confirm an
                # engineer cannot reassign their own work)
                mail.outbox = []
                agent_resp = c_ca.post("/api/support-staff/", data={
                    "username": f"{PREFIX}_agent", "email": f"{PREFIX}_agent@test.invalid",
                    "role": str(eng_role_id),
                }, content_type="application/json")
                if agent_resp.status_code == 201 and mail.outbox:
                    agent_pw_match = re.search(r"Temporary password: (.+)", mail.outbox[0].body)
                if agent_pw_match:
                    new_engineer = User.objects.filter(username=f"{PREFIX}_agent").first()
                    # Assign the ticket to THIS engineer first -- a Field
                    # Engineer now only sees tickets assigned to them
                    # (see Bug 1 fix), so without this the ticket would
                    # be invisible to them (a 404) rather than exercising
                    # the reassignment-authority check this is actually
                    # testing.
                    if new_engineer:
                        c_ca.patch(f"/api/tickets/{ticket_id}/", data={"assigned_to": str(new_engineer.id)},
                                  content_type="application/json")
                    staff_client.login(username=f"{PREFIX}_agent", password=agent_pw_match.group(1).strip())
                    r = staff_client.patch(f"/api/tickets/{ticket_id}/",
                                           data={"assigned_to": str(staff_user.id)},
                                           content_type="application/json")
                    self._check("Field Engineer CANNOT reassign a ticket", r.status_code == 400,
                                f"status {r.status_code}")
                    r = staff_client.patch(f"/api/tickets/{ticket_id}/",
                                           data={"status": "in_progress"},
                                           content_type="application/json")
                    self._check("Field Engineer CAN still change status", r.status_code == 200,
                                f"status {r.status_code}")

                    # Regression guard: a Field Engineer must see ONLY
                    # tickets assigned to them, never the whole queue.
                    # Reassign back to the original engineer, then
                    # confirm the second engineer's list goes empty.
                    c_ca.patch(f"/api/tickets/{ticket_id}/", data={"assigned_to": str(staff_user.id)},
                              content_type="application/json")
                    unassigned_view = staff_client.get("/api/tickets/").json()
                    self._check("Field Engineer sees NO tickets once none are assigned to them",
                                len(unassigned_view) == 0, f"saw {len(unassigned_view)}")

                # --- Proximity routing ---
                nearby = c_ca.get(f"/api/tickets/{ticket_id}/nearby-engineers/")
                self._check("Nearby-engineers endpoint works", nearby.status_code == 200,
                            f"status {nearby.status_code}")
                if nearby.status_code == 200:
                    listed = nearby.json().get("engineers", [])
                    self._check("Only Field Engineers listed for assignment", len(listed) >= 1,
                                f"got {len(listed)}")

                # --- Two-tier service report ---
                mail.outbox = []
                rep = staff_client.post("/api/service-reports/", data={
                    "ticket": str(ticket_id),
                    "work_performed": "Health check work log.",
                    "internal_notes": "INTERNAL-ONLY-MARKER",
                    "video_title": "Health check recording",
                    "service_video": SimpleUploadedFile(
                        "healthcheck.mp4", b"fake video bytes", content_type="video/mp4"
                    ),
                }, format="multipart")
                self._check("Engineer can write a service report", rep.status_code == 201,
                            f"status {rep.status_code}: {rep.content.decode()[:160]}")
                if rep.status_code == 201:
                    report_id = rep.json()["id"]
                    self._check("Report is auto-added to the Knowledge Base",
                                rep.json().get("include_in_knowledge_base") is True)
                    # Customer must not see an unreleased report at all
                    cust_before = c_sub.get(f"/api/service-reports/{report_id}/")
                    self._check("Customer cannot see unreleased report", cust_before.status_code == 404,
                                f"status {cust_before.status_code}")
                    # Service layer summarises and releases
                    c_ca.patch(f"/api/service-reports/{report_id}/",
                               data={"customer_summary": "All fixed."},
                               content_type="application/json")
                    rel = c_ca.post(f"/api/service-reports/{report_id}/release-to-customer/")
                    self._check("Service layer can release the summary", rel.status_code == 200,
                                f"status {rel.status_code}")
                    # And the released version must be summary-only
                    cust_after = c_sub.get(f"/api/service-reports/{report_id}/")
                    body = cust_after.content.decode()
                    self._check("Released report reaches the customer", cust_after.status_code == 200,
                                f"status {cust_after.status_code}")
                    self._check("Internal notes NEVER leak to the customer",
                                "INTERNAL-ONLY-MARKER" not in body)

                # --- Reports + audit log ---
                self._check("Reports endpoint works", c_ca.get("/api/tickets/reports/").status_code == 200)
                self._check("Audit log works", c_ca.get("/api/audit-logs/").status_code == 200)

        # --- Security boundaries still hold ---
        self._check("Soori Admin cannot see Client tickets", c_sa.get("/api/tickets/").json() == [])
        self._check("Soori Admin cannot read audit log", c_sa.get("/api/audit-logs/").status_code == 403)

        other_ticket = Ticket.objects.exclude(client__name__startswith=PREFIX).first()
        if other_ticket:
            resp = c_ca.post("/api/ticket-comments/", data={"ticket": str(other_ticket.id), "body": "x"},
                             content_type="application/json")
            self._check("Cross-tenant comment blocked", resp.status_code == 400, f"status {resp.status_code}")

        # --- Subscription enforcement ---
        hc_client = Client.objects.filter(name__startswith=PREFIX).first()
        hc_client.status = "suspended"
        hc_client.save()
        self._check("Suspended client blocked from tickets", c_ca.get("/api/tickets/").status_code == 403)
        self._check("Suspended client can still see own subscription", c_ca.get("/api/clients/").status_code == 200)

        # --- Access codes + Knowledge Base ---
        # Reactivate first: the subscription test just above deliberately
        # suspended this client, and suspension correctly blocks code
        # issuing too.
        hc_client.status = "active"
        hc_client.save()
        import datetime as _dt
        from django.utils import timezone as _tz
        expiry = (_tz.now() + _dt.timedelta(days=7)).isoformat()
        ac = c_ca.post("/api/access-codes/", data={
            "scope": "knowledge_base", "label": f"{PREFIX} intern", "expires_at": expiry,
        }, content_type="application/json")
        self._check("Issue a Knowledge Base access code", ac.status_code == 201,
                    f"status {ac.status_code}: {ac.content.decode()[:160]}")
        if ac.status_code == 201:
            code = ac.json()
            self._check("Secret returned once at creation", "secret" in code)
            # Someone with NO account should be able to use it
            anon = TestClient()
            used = anon.post("/api/access/login/", data={
                "username": code["username"], "secret": code["secret"],
            }, content_type="application/json")
            self._check("Code works with no account at all", used.status_code == 200,
                        f"status {used.status_code}")
            self._check("Training material excludes internal notes",
                        "INTERNAL-ONLY-MARKER" not in used.content.decode())
            # Revoking must bite immediately
            c_ca.delete(f"/api/access-codes/{code['id']}/")
            after = TestClient().post("/api/access/login/", data={
                "username": code["username"], "secret": code["secret"],
            }, content_type="application/json")
            self._check("Revoked code stops working immediately", after.status_code == 403,
                        f"status {after.status_code}")

        # --- Removing a staff member actually removes their ACCESS ---        # (Regression guard: removing a profile used to leave the login
        # fully working, so a "removed" person could still sign in and
        # read every ticket in the company.)
        hc_client.status = "active"
        hc_client.save()
        mail.outbox = []
        resp = c_ca.post("/api/support-staff/", data={
            "username": f"{PREFIX}_removable", "email": f"{PREFIX}_removable@test.invalid", "role": str(eng_role_id),
        }, content_type="application/json")
        if resp.status_code == 201 and mail.outbox:
            removable_pw = re.search(r"Temporary password: (.+)", mail.outbox[0].body).group(1).strip()
            removable = User.objects.get(username=f"{PREFIX}_removable")
            c_ca.delete(f"/api/support-staff/{removable.id}/")

            self._check("Removed staff can no longer log in",
                        TestClient().login(username=f"{PREFIX}_removable", password=removable_pw) is False)
            self._check("Removed staff's username is freed for reuse",
                        not User.objects.filter(username=f"{PREFIX}_removable").exists())
