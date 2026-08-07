# Soori Phase 1 — Full Guide: What Was Built, Why, and How to Test It

This covers the same ground as our conversation, written up as one
reference document: the design decisions behind every model and
permission choice, and a step-by-step way to prove to yourself that
tenant isolation actually works — not just read about it.

Everything in this guide was actually run against a real SQLite
database while building it (migrations, a superuser, a full demo
dataset, and live API calls as 7 different logged-in users). The
outputs you see under "Expected results" below are real, not
hypothetical.

---

## 1. The mental model

Four roles, one hierarchy:

```
Soori Admin (platform owner)
   └── Client (a subscribing company)              <- the tenant boundary
         ├── Client Admin(s)                        <- manages the org
         ├── Support Staff (agent, senior agent...)
         └── Sub-Client(s)                          <- the Client's own customers
```

The one rule that matters more than any other: **a Client only ever
sees its own Support Staff, Sub-Clients, and Tickets. Soori Admin sees
across all Clients.** Everything else in the design serves that rule.

---

## 2. App structure, and why it's split this way

| App | Contains | Why it's separate |
|---|---|---|
| `accounts` | `User`, `Role`, custom `UserManager` | Pure identity/auth. No business logic, so it never needs to change when ticket or billing logic changes. |
| `clients` | `Client`, `SupportStaffProfile`, `SubClientProfile` | The "who's in this org" data — roster management as a unit. |
| `tickets` | `Ticket`, `TicketComment` | Highest-churn part of the product; isolated so ticket features don't ripple into roster/auth code. |
| `audit` | `AuditLog` | Cross-cutting (every app will eventually write to it) and read-only from the API, so it's cleanest as its own app. |
| `core` | `TenantScopedQuerySetMixin`, role permission classes | Shared plumbing with zero dependency on the other apps — it only assumes `request.user` has `.is_soori_admin`, `.client_id`, etc. |

---

## 3. Why one `User` model instead of four

Django/DRF's entire auth stack — sessions, password hashing, tokens,
`request.user`, permission checks — is built around **one** user
table. Four separate models (`SooriAdminUser`, `ClientAdminUser`,
`SupportStaffUser`, `SubClientUser`) would mean either:
- four separate authentication backends, or
- one shadow "identity" table anyway, just with extra steps.

It also means every relation elsewhere (`Ticket.created_by`,
`Ticket.assigned_to`, `AuditLog.actor`) is a single, simple FK type.
With four user models those FKs would need to be polymorphic (generic
foreign keys, or four nullable FK columns per relation) — worse for
both query performance and migrations.

**The trade-off you accept:** the `User` table carries a `client` FK
that's always `None` for Soori Admins. Two safeguards enforce this
stays correct:
- `User.clean()` raises `ValidationError` if a Soori Admin has a
  client, or if anyone else doesn't.
- A DB-level `CheckConstraint` (`soori_admin_has_no_client_others_require_client`)
  enforces the same rule even if application code forgets to call
  `full_clean()` — this is what caught the `createsuperuser` bug
  described in section 6.

Role-specific fields (a Support Staff's seniority tier, a Sub-Client's
company name) don't live on `User` at all — they're on one-to-one
**profile** models (`SupportStaffProfile`, `SubClientProfile`) in the
`clients` app. This is the standard "shared identity + role profile"
pattern: `User` stays thin, and role data lives where it's relevant.

**When would separate models per role actually be better?** If the
four roles never shared an authentication method at all — e.g.
Sub-Clients log in via a magic email link while staff use company SSO
— and you never needed to query "all users regardless of role."
Your spec has all four roles doing username/password against one
platform, so a single model is the simpler, more idiomatic choice.

---

## 4. Multi-tenant query scoping — the part to actually understand

This is two **separate layers**. Conflating them is the most common
mistake in multi-tenant systems, so keeping them distinct is the
actual design insight here, not an implementation detail.

### Layer 1 — Tenant scoping (security boundary)

`core/permissions.py` → `TenantScopedQuerySetMixin`:

```python
def get_queryset(self):
    qs = super().get_queryset()
    user = self.request.user

    if not user.is_authenticated:
        return qs.none()
    if user.is_soori_admin:
        return qs                      # cross-tenant, by design
    if user.client_id is None:
        return qs.none()               # never fall back to "everything"
    return qs.filter(**{self.tenant_field: user.client_id})
```

This answers exactly one question: **"which org can this user see
data from at all?"** Get this wrong and it's a data breach — Client A
seeing Client B's tickets.

It's a **viewset** mixin, not a custom model manager. A manager
can't see `request.user` without smuggling the current user into
thread-local/global state via middleware — a well-known Django
anti-pattern: it silently changes what a queryset returns based on
invisible ambient context, and breaks in Celery tasks, management
commands, the shell, and tests. A viewset mixin keeps scoping explicit
and tied to a real request you can trace and unit test.

**The trade-off you accept:** you must remember to apply this mixin
(or equivalent manual filtering) to every viewset touching tenant
data. That's why every tenant-scoped viewset in this scaffold
(`TicketViewSet`, `SupportStaffViewSet`, `SubClientViewSet`,
`AuditLogViewSet`) includes it, and why section 7 below gives you a
literal test proving cross-tenant access fails.

### Layer 2 — Role-based row filtering (business rule)

Inside each viewset's own `get_queryset()`, layered on top of Layer 1.
Example from `TicketViewSet`:

```python
def get_queryset(self):
    qs = super().get_queryset()   # already tenant-scoped by Layer 1
    user = self.request.user
    if user.is_sub_client:
        return qs.filter(created_by=user)   # only their own tickets
    if user.is_support_staff:
        return qs                            # shared queue (business choice)
    return qs                                # client_admin / soori_admin: everything in scope
```

This answers a different question: **"within an org this user is
already allowed into, which specific rows should they see?"** Get this
wrong and it's a UX/business bug (e.g. a Sub-Client sees another
Sub-Client's ticket) — still bad, but it can never cross the tenant
boundary, because Layer 1 already constrained the queryset before
Layer 2 runs.

### Layer 3 — Object-level defense in depth

`IsSameTenant` (a DRF permission class) re-checks `obj.client_id ==
request.user.client_id` on `retrieve`/`update`/`destroy`. This exists
for the case where a queryset override gets forgotten on some future
viewset, or a custom `@action` route does a raw `Model.objects.get(pk=...)`
that bypasses `get_queryset()` entirely. Cheap to include, so it's on
every tenant-scoped viewset here.

### Why `Ticket.client` is denormalized

`Ticket.client` is technically derivable via `created_by.client`, but
it's stored directly on `Ticket` anyway:
1. Every tenant-scoped model having a **direct** `client` column means
   `TenantScopedQuerySetMixin`'s default `tenant_field = "client"`
   works with zero per-model configuration.
2. It's a real indexed column (see `Ticket.Meta.indexes`) you can
   filter/aggregate on directly for dashboards, instead of paying for
   a join on every query.

It's kept in sync automatically in `Ticket.save()`, so it can't drift
from `created_by`.

---

## 5. Model-by-model summary

- **`Client`** — the tenant itself. `plan`/`status` are plain
  `TextChoices` for now (`basic`/`pro`/`enterprise`,
  `trial`/`active`/`suspended`/`cancelled`) — enough to build billing
  logic against later without overengineering it now.
- **`SupportStaffProfile`** — one-to-one with `User`. `staff_role` is
  a `CharField` with choices (`agent`, `senior_agent`, `supervisor`)
  rather than a hardcoded set of booleans, so adding a new tier is a
  migration adding a choice, not a schema change. If it ever needs to
  be fully client-configurable, swap it for a FK to a small lookup
  table — nothing else in the system cares that `staff_role` is
  currently a string.
- **`SubClientProfile`** — one-to-one with `User`, holds
  `company_name`/`phone`.
- **`Ticket`** — `created_by` is constrained to `role=sub_client`,
  `assigned_to` to `role=support_staff` via `limit_choices_to` (a UI/
  admin hint, not a hard DB constraint — worth tightening with a
  `CheckConstraint` or `clean()` validation later if you want it
  enforced at the DB level too).
- **`TicketComment`** — `is_internal_note` distinguishes staff-only
  notes from customer-visible replies. This is filtered out in
  `TicketCommentViewSet.get_queryset()` for Sub-Clients — enforced
  server-side, not just hidden in the frontend, which matters because
  a Sub-Client could otherwise call the API directly and read staff
  notes about them.
- **`AuditLog`** — append-only, read-only from the API
  (`ReadOnlyModelViewSet`). Nothing in this phase writes to it yet —
  see the "not yet built" list at the end.

---

## 6. The bug this guide's testing found (and fixed)

While preparing this guide, running `python manage.py createsuperuser`
against the scaffold **failed** — the `soori_admin_has_no_client_others_require_client`
constraint rejected it. Django's `createsuperuser` command only fills
in `USERNAME_FIELD` and `REQUIRED_FIELDS` interactively; it had no
idea our `role` field exists, so it left it blank — which satisfies
neither branch of the constraint.

Fixed with a custom manager (`accounts/managers.py`):

```python
class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.SOORI_ADMIN)
        extra_fields["client"] = None
        return super().create_superuser(username, email, password, **extra_fields)
```

A Django superuser is conceptually a Soori Admin in this system, so
forcing that role on `createsuperuser` isn't a workaround — it's just
correct. This is already applied in the files you have; flagging it so
you know *why* it's there if you ever see it while reading the code.

---

## 7. How to run it

```bash
cd soori_backend
pip install django djangorestframework
python manage.py migrate
```

You have two options from here:

### Option A — quick exploration with real demo data (recommended first)

```bash
python manage.py seed_demo
python manage.py runserver
```

This creates 2 tenants (Acme Corp, Beta LLC), a Soori Admin, a Client
Admin + 2 Support Staff + 2 Sub-Clients per tenant, 3 tickets (one with
both a public and an internal-only comment), and 2 audit log entries.

**Every seeded user's password is `demo12345`.** Usernames:
`soori_admin`, `acme_admin`, `acme_agent`, `acme_senior_agent`,
`acme_customer1`, `acme_customer2`, `beta_admin`, `beta_agent`,
`beta_customer1`.

Re-running `seed_demo` is safe — it deletes and recreates the same
fixed set of demo users rather than piling up duplicates.

### Option B — start from a blank slate

```bash
python manage.py createsuperuser
python manage.py runserver
```

---

## 8. How to actually test tenant isolation

### Fastest way: the browsable API in your browser

1. `python manage.py runserver`
2. Visit `http://127.0.0.1:8000/api/tickets/` — you'll be prompted to
   log in (DRF's browsable API has a Log In link top-right).
3. Log in as `acme_customer1` / `demo12345` → you should see exactly
   one ticket: *"Cannot reset my password"*.
4. Log out, log in as `acme_admin` / `demo12345` → you should see
   **both** Acme tickets, but never Beta's *"Billing question"*.
5. Log out, log in as `soori_admin` / `demo12345` → you should see
   **all three** tickets across both tenants.

Also try `http://127.0.0.1:8000/api/clients/`,
`/api/support-staff/`, `/api/sub-clients/`, `/api/ticket-comments/`,
and `/api/audit-logs/` the same way.

### Precise way: a scripted check (what I actually ran)

This is the exact check used to validate the scaffold — run it via
`python manage.py shell` (paste the body) or save as a one-off script:

```python
from django.test import Client as TestClient

def check(username, password="demo12345"):
    c = TestClient()
    assert c.login(username=username, password=password), f"login failed for {username}"
    tickets = c.get("/api/tickets/").json()
    clients = c.get("/api/clients/").json()
    print(username, "-> tickets:", [t["title"] for t in tickets],
          "| clients:", [cl["name"] for cl in clients])

for u in ["soori_admin", "acme_admin", "acme_agent", "acme_customer1",
          "acme_customer2", "beta_admin", "beta_customer1"]:
    check(u)
```

**Expected results (confirmed while building this):**

| User | Tickets visible | Clients visible |
|---|---|---|
| `soori_admin` | all 3 (both tenants) | Acme Corp, Beta LLC |
| `acme_admin` | both Acme tickets, never Beta's | Acme Corp only |
| `acme_agent` | both Acme tickets | Acme Corp only |
| `acme_customer1` | only *"Cannot reset my password"* (their own) | Acme Corp only |
| `acme_customer2` | only *"Feature request: dark mode"* (their own) | Acme Corp only |
| `beta_admin` | only *"Billing question"* | Beta LLC only |
| `beta_customer1` | only *"Billing question"* (their own) | Beta LLC only |

If your results differ from this table, something regressed in the
tenant scoping — treat that as a stop-the-line bug.

### Checking internal-note filtering specifically

```python
from tickets.models import Ticket
from django.test import Client as TestClient

t = Ticket.objects.get(title="Cannot reset my password")

for username in ["acme_customer1", "acme_agent"]:
    c = TestClient()
    c.login(username=username, password="demo12345")
    comments = c.get(f"/api/ticket-comments/?ticket={t.id}").json()
    print(username, "->", [(cm["body"], cm["is_internal_note"]) for cm in comments])
```

Expected: `acme_customer1` sees 2 comments, both `is_internal_note:
False`. `acme_agent` sees all 3, including the one marked
`is_internal_note: True`. If a Sub-Client ever sees an internal note,
that's a security bug, not a display bug — it means the API is leaking
staff-only data, not just that the frontend forgot to hide it.

### Using curl / Postman instead

DRF's `SessionAuthentication` needs a CSRF token for anything other
than GET once you're outside the browsable API's own forms, which gets
fiddly with raw curl. For manual testing outside the browser, it's
much less friction to add token auth for now:

```bash
pip install djangorestframework-simplejwt
```

Add to `REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]` and wire up
`/api/token/` — this is exactly what I'd build in the "auth wiring"
phase, so mention if you want it prioritized next.

### Django admin

`http://127.0.0.1:8000/admin/`, log in as `soori_admin`. `UserAdmin` is
already customized to show/filter by `role` and `client` — useful for
eyeballing the seeded data without going through the API at all.

---

## 9. What's intentionally not built yet

- Registration/invite flows (Soori Admin onboarding a Client + its
  first Client Admin; Client Admin provisioning Support Staff/
  Sub-Clients with generated credentials) — needs atomic User+Profile
  creation, probably email/notification hooks.
- Token/JWT auth wiring for the React frontend (currently
  `SessionAuthentication` only, fine for local dev/admin, not for a
  real SPA).
- Audit log **writing** — nothing calls `AuditLog.objects.create(...)`
  from application code yet; that belongs in `perform_create`/
  `perform_update` hooks or signal handlers across the other apps.
- Fine-grained business rules on top of tenant scoping — e.g. whether
  Support Staff see a shared ticket queue or only tickets assigned to
  them is a one-line toggle in `TicketViewSet.get_queryset`, currently
  left as "shared queue."
- Subscription enforcement (blocking access when `Client.status` is
  `suspended`/`cancelled`) — likely a permission class or middleware
  checking `request.user.client.status`.

Tell me which of these you want next and I'll build it the same way —
scaffolded, explained, and actually tested before I hand it to you.

---

## Fixes applied after initial testing (both confirmed working)

Two real bugs were found while separately building a parallel
teaching version of this project, and were then fixed here too:

1. **`accounts/admin.py` — Django's two-step user creation.** Django's
   stock "Add user" admin page only asks for username + password.
   `User.clean()` requires `role`/`client` to already be consistent on
   *every* save, including that very first one — so creating any user
   through `/admin/` (other than via `createsuperuser`, which already
   had its own fix) failed immediately with `"... users must belong to
   a Client."` before you ever reached the page where you could set
   them. Fixed with a custom `add_form`/`add_fieldsets` that puts
   `role`/`client` on that first page.

2. **`tickets/serializers.py` — nested `comments` field bypassing
   scoping.** `TicketSerializer` originally nested `TicketCommentSerializer`
   directly (`comments = TicketCommentSerializer(many=True, read_only=True)`).
   That reads straight off `ticket.comments.all()` — it has no
   knowledge of `TicketCommentViewSet`'s own `is_internal_note`
   filtering, so a Sub-Client fetching a ticket *directly* (rather than
   through `/api/ticket-comments/`) would see internal-only staff
   notes about themselves. Fixed by replacing it with a
   `SerializerMethodField` that does the same filtering by hand, using
   the request available via serializer context.

Both are now covered by the test suite you can re-run yourself using
the same commands from section 8 of this guide.
