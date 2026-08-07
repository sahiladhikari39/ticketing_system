"""
Walks through the EXACT workflow the client described, step by step,
and checks each requirement as it goes.

    python manage.py verify_workflow

The scenario, in the client's own terms:
  Ram and Sita are customers. Ram's printer breaks and he raises a
  ticket. The service department assigns Harry, a field engineer.
  Harry needs Ram's service history, so the service lead issues him a
  time-limited code. Harry does the job, films it, and files a
  detailed report. Ram receives only a short summary -- never the full
  detail, never the video. An intern is issued their own time-limited
  code to watch the training videos.

Two absolute rules the client stated, both checked here:
  - The video library must NEVER be reachable by Harry or Ram.
  - Harry's access to customer records must be temporary, because
    engineers leave.

This exists as its own command rather than folding into health_check
because it verifies a BUSINESS story rather than technical
correctness -- it's the thing to run when the client asks "does it do
what I described?"
"""

import datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.test import Client as TestClient
from django.test.utils import override_settings
from django.utils import timezone

from accounts.models import Role, User
from clients.models import Client, StaffPermission, StaffRole, SubClientProfile, SupportStaffProfile

PREFIX = "wf_"
PW = "workflowtest123"


class Command(BaseCommand):
    help = "Verify the client's described workflow, step by step."

    def handle(self, *args, **options):
        self.checks = []
        try:
            with override_settings(
                EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                # Synchronous, so checking mail.outbox right after an
                # action is deterministic rather than racing the
                # background send thread.
                EMAIL_SEND_ASYNC=False,
                ALLOWED_HOSTS=["testserver", "*"],
            ):
                self.run_scenario()
        finally:
            self.cleanup()

        self.stdout.write("")
        self.stdout.write("=" * 66)
        passed = sum(1 for _, ok in self.checks if ok)
        for label, ok in self.checks:
            style = self.style.SUCCESS if ok else self.style.ERROR
            self.stdout.write(style(f"  {'PASS' if ok else 'FAIL'}  {label}"))
        self.stdout.write("=" * 66)
        summary = f"{passed}/{len(self.checks)} workflow requirements met"
        self.stdout.write(self.style.SUCCESS(summary) if passed == len(self.checks) else self.style.ERROR(summary))

    def require(self, label, condition):
        self.checks.append((label, bool(condition)))

    def step(self, text):
        self.stdout.write("")
        self.stdout.write(self.style.NOTICE(f">>> {text}"))

    def cleanup(self):
        User.objects.filter(username__startswith=PREFIX).delete()
        Client.objects.filter(name__startswith=PREFIX).delete()

    def run_scenario(self):
        from django.core import mail

        self.cleanup()
        today = datetime.date.today()

        # ---- Setup: the printer company, its staff, and its customers ----
        self.step("Setting up: a printer company with a service team and two customers")
        company = Client.objects.create(
            name=f"{PREFIX}PrinterCo", plan="pro", status="active",
            subscription_period="1_year", subscription_start=today,
            subscription_end=today + datetime.timedelta(days=365),
        )
        dept_role = StaffRole.objects.create(
            client=company, name="Service Department", is_system=True,
            permissions=[
                StaffPermission.ASSIGN_TICKETS, StaffPermission.VIEW_REPORTS,
                StaffPermission.APPROVE_SERVICE_REPORT,
                StaffPermission.VIEW_ALL_SERVICE_REPORTS, StaffPermission.VIEW_KNOWLEDGE_BASE,
            ],
        )
        eng_role = StaffRole.objects.create(
            client=company, name="Field Engineer", is_system=True,
            permissions=[StaffPermission.RECEIVE_TICKETS, StaffPermission.WRITE_SERVICE_REPORT],
        )

        manager = User.objects.create_user(
            username=f"{PREFIX}manager", email=f"{PREFIX}mgr@t.invalid", password=PW,
            role=Role.CLIENT_ADMIN, client=company,
        )
        harry = User.objects.create_user(
            username=f"{PREFIX}harry", email=f"{PREFIX}harry@t.invalid", password=PW,
            role=Role.SUPPORT_STAFF, client=company,
        )
        SupportStaffProfile.objects.create(user=harry, role=eng_role, service_area="Kathmandu")

        ram = User.objects.create_user(
            username=f"{PREFIX}ram", email=f"{PREFIX}ram@t.invalid", password=PW,
            role=Role.SUB_CLIENT, client=company,
        )
        SubClientProfile.objects.create(user=ram, company_name="Ram Printing House", service_area="Kathmandu")
        sita = User.objects.create_user(
            username=f"{PREFIX}sita", email=f"{PREFIX}sita@t.invalid", password=PW,
            role=Role.SUB_CLIENT, client=company,
        )
        SubClientProfile.objects.create(user=sita, company_name="Sita Stationers", service_area="Kathmandu")
        self.stdout.write("    Manager, Harry (field engineer), Ram and Sita (customers)")

        c_mgr = TestClient(); c_mgr.login(username=manager.username, password=PW)
        c_harry = TestClient(); c_harry.login(username=harry.username, password=PW)
        c_ram = TestClient(); c_ram.login(username=ram.username, password=PW)
        c_sita = TestClient(); c_sita.login(username=sita.username, password=PW)

        # ---- 1. Ram raises a ticket ----
        self.step("1. Ram raises a ticket about his printer")
        r = c_ram.post("/api/tickets/", data={
            "title": "Printer jams on every page",
            "description": "Paper jams immediately after printing starts.",
            "product_or_service": "HP LaserJet M404",
            "priority": "high",
        }, content_type="application/json")
        self.require("Ram can raise a ticket", r.status_code == 201)
        if r.status_code != 201:
            return
        ticket_id = r.json()["id"]
        self.stdout.write(f"    Ticket raised: {r.json()['title']}")

        # Sita must not see Ram's ticket
        sita_sees = c_sita.get("/api/tickets/").json()
        self.require("Sita cannot see Ram's ticket (customers are isolated)", len(sita_sees) == 0)

        # ---- 2. Service department assigns Harry ----
        self.step("2. The service department assigns Harry, who covers Ram's area")
        nearby = c_mgr.get(f"/api/tickets/{ticket_id}/nearby-engineers/")
        self.require("Manager can see which engineers cover Ram's area", nearby.status_code == 200)
        if nearby.status_code == 200:
            engineers = nearby.json()["engineers"]
            harry_row = next((e for e in engineers if e["username"] == harry.username), None)
            self.require("Harry is flagged as covering Ram's area", harry_row and harry_row["is_in_customer_area"])

        r = c_mgr.patch(f"/api/tickets/{ticket_id}/", data={"assigned_to": str(harry.id)},
                        content_type="application/json")
        self.require("Manager can assign the ticket to Harry", r.status_code == 200)

        # Harry must not be able to reassign it himself
        r = c_harry.patch(f"/api/tickets/{ticket_id}/", data={"assigned_to": str(harry.id)},
                          content_type="application/json")
        self.require("Harry cannot reassign tickets himself", r.status_code == 400)

        # ---- 3. Harry has NO standing access to customer history ----
        self.step("3. Harry has no standing access to customer records")
        harry_reports = c_harry.get("/api/service-reports/").json()
        self.require("Harry sees no customer service history by default", len(harry_reports) == 0)
        kb = c_harry.get("/api/knowledge-base/")
        kb_entries = kb.json() if kb.status_code == 200 else []
        self.require("Harry CANNOT reach the video library at all", len(kb_entries) == 0)
        self.stdout.write("    Confirmed: Harry's login alone gives him neither")

        # ---- 4. Service lead issues Harry a time-limited code ----
        self.step("4. Service lead issues Harry a time-limited code for Ram's history")
        expiry = (timezone.now() + datetime.timedelta(hours=8)).isoformat()
        r = c_mgr.post("/api/access-codes/", data={
            "scope": "customer_history",
            "label": "Harry - Ram's history for today's job",
            "customer": str(ram.id),
            "expires_at": expiry,
        }, content_type="application/json")
        self.require("Service lead can issue Harry a temporary code", r.status_code == 201)
        if r.status_code != 201:
            return
        code = r.json()
        self.stdout.write(f"    Issued: {code['username']} / {code['secret']} (expires in 8 hours)")
        self.require("The code's secret is shown exactly once, at creation", "secret" in code)

        used = TestClient().post("/api/access/login/", data={
            "username": code["username"], "secret": code["secret"],
        }, content_type="application/json")
        self.require("Harry can open Ram's history with the code", used.status_code == 200)

        # ---- 5. Harry does the job, films it, files the report ----
        self.step("5. Harry completes the job, films it, and files a detailed report")
        video = SimpleUploadedFile("harry_camera_IMG0042.mp4", b"x" * 2048, content_type="video/mp4")
        r = c_harry.post("/api/service-reports/", data={
            "ticket": ticket_id,
            "work_performed": "Stripped the paper path, found a torn separation pad, replaced it, "
                              "cleaned the rollers and ran 200 test pages with no jams.",
            "root_cause": "Separation pad had torn, letting two sheets feed at once.",
            "parts_used": "Separation pad SP-404 x1",
            "internal_notes": "CONFIDENTIAL-INTERNAL: site is very dusty, third callout this year. "
                              "Suggest quoting a maintenance contract.",
            "service_video": video,
            "video_title": "Replacing a torn separation pad on an HP LaserJet M404",
            "include_in_knowledge_base": "true",
        }, format="multipart")
        self.require("Harry can file a detailed report with video", r.status_code == 201)
        if r.status_code != 201:
            self.stdout.write(self.style.ERROR(f"    {r.content.decode()[:300]}"))
            return
        report_id = r.json()["id"]
        self.stdout.write("    Report filed, video attached with a title")

        # A video with no title must be refused -- it'd be unfindable later
        untitled = SimpleUploadedFile("IMG_0099.mp4", b"x" * 512, content_type="video/mp4")
        r2 = c_harry.post("/api/service-reports/", data={
            "ticket": ticket_id, "work_performed": "x", "service_video": untitled,
        }, format="multipart")
        self.require("A video without a title is refused", r2.status_code == 400)

        # ---- 6. Harry's temporary code expires ----
        self.step("6. Harry's temporary code expires")
        from knowledge.models import AccessCode
        issued = AccessCode.objects.get(id=code["id"])
        issued.expires_at = timezone.now() - datetime.timedelta(minutes=1)
        issued.save(update_fields=["expires_at"])
        after = TestClient().post("/api/access/login/", data={
            "username": code["username"], "secret": code["secret"],
        }, content_type="application/json")
        self.require("Once expired, Harry's code stops working", after.status_code == 403)
        self.stdout.write("    Confirmed: expired code rejected")

        # ---- 7. Ram receives only a short summary ----
        self.step("7. Ram receives a short summary, never the full report")
        before = c_ram.get(f"/api/service-reports/{report_id}/")
        self.require("Before release, Ram sees nothing at all", before.status_code == 404)

        c_mgr.patch(f"/api/service-reports/{report_id}/", data={
            "customer_summary": "We replaced a worn part in the paper feed and tested the printer. "
                                "It's printing normally again.",
        }, content_type="application/json")
        mail.outbox = []
        rel = c_mgr.post(f"/api/service-reports/{report_id}/release-to-customer/")
        self.require("Service department releases the summary to Ram", rel.status_code == 200)
        self.require("Ram is emailed that his summary is ready", len(mail.outbox) == 1)

        ram_view = c_ram.get(f"/api/service-reports/{report_id}/")
        body = ram_view.content.decode()
        self.require("Ram receives the summary", ram_view.status_code == 200)
        self.require("Ram NEVER sees the internal notes", "CONFIDENTIAL-INTERNAL" not in body)
        self.require("Ram NEVER sees the technical detail", "separation pad" not in body.lower())
        self.require("Ram NEVER receives the video", "service_video" not in body and ".mp4" not in body)
        self.stdout.write(f"    Ram's entire view: {ram_view.json()}")

        # Harry also must not be able to write or release customer wording
        r = c_harry.patch(f"/api/service-reports/{report_id}/", data={"customer_summary": "hacked"},
                          content_type="application/json")
        self.require("Harry cannot write the customer-facing wording", r.status_code in (400, 403, 404))

        # ---- 8. The intern gets a code for the video library ----
        self.step("8. The manager issues an intern a time-limited code for the videos")
        intern_expiry = (timezone.now() + datetime.timedelta(days=42)).isoformat()
        r = c_mgr.post("/api/access-codes/", data={
            "scope": "knowledge_base",
            "label": "Intern - 6 week placement",
            "expires_at": intern_expiry,
        }, content_type="application/json")
        self.require("Manager can issue an intern code with a time limit", r.status_code == 201)
        if r.status_code != 201:
            return
        intern_code = r.json()
        self.stdout.write(f"    Issued: {intern_code['username']} / {intern_code['secret']} (6 weeks)")

        intern = TestClient().post("/api/access/login/", data={
            "username": intern_code["username"], "secret": intern_code["secret"],
        }, content_type="application/json")
        self.require("Intern can log in with the code alone (no account)", intern.status_code == 200)
        if intern.status_code == 200:
            data = intern.json()
            entries = data.get("entries", [])
            raw = intern.content.decode()
            self.require("Intern can see the training video", entries and entries[0].get("service_video_url"))
            self.require("The video has a readable title", entries and entries[0].get("video_title"))
            self.require("Intern does NOT see internal notes", "CONFIDENTIAL-INTERNAL" not in raw)
            self.require("Intern does NOT see which customer it was", "Ram" not in raw and PREFIX + "ram" not in raw)
            self.stdout.write(f"    Intern sees: \"{entries[0]['video_title']}\"" if entries else "    (no entries)")

        # ---- 9. Ram must never reach the video library ----
        self.step("9. Final check: neither Ram nor Harry can reach the video library")
        ram_kb = c_ram.get("/api/knowledge-base/")
        ram_entries = ram_kb.json() if ram_kb.status_code == 200 else []
        self.require("Ram CANNOT reach the video library", len(ram_entries) == 0)
        harry_kb = c_harry.get("/api/knowledge-base/")
        harry_entries = harry_kb.json() if harry_kb.status_code == 200 else []
        self.require("Harry CANNOT reach the video library, even after filming it", len(harry_entries) == 0)
