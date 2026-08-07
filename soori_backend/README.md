# Soori — Phase 1 Scaffold (Models + Auth/Role Structure)

This is models, custom auth, and basic viewsets only — no invite/registration
flows, no subscription billing, no ticket business logic beyond CRUD. Verified
end-to-end: `manage.py check`, `makemigrations`, `migrate`, and a full ORM
smoke test all pass against a real sqlite DB in this scaffold.

## App layout

- **accounts/** — the custom `User` model and nothing else. Deliberately
  small: identity, auth, role, tenant FK. No business logic.
- **clients/** — `Client` (the tenant itself), `SupportStaffProfile`,
  `SubClientProfile`. These three live together because they're the
  "who belongs to this org" data, and SupportStaff/SubClient profiles
  are meaningless without their parent Client.
- **tickets/** — `Ticket`, `TicketComment`. Split from `clients/` because
  ticket volume and query patterns evolve independently of org/roster
  management, and this is where most future feature work will land.
- **audit/** — `AuditLog`. Split out because it's cross-cutting (every
  app will eventually write to it) and read-only from the API.
- **core/** — shared, app-agnostic pieces: `TenantScopedQuerySetMixin`
  and the role permission classes. Nothing here imports from
  `accounts`/`clients`/`tickets` — it only depends on `request.user`
  duck-typing (`.is_soori_admin`, `.client_id`, etc).

## Running it

```
pip install django djangorestframework
python manage.py migrate
python manage.py createsuperuser   # create a Soori Admin manually the first time
python manage.py runserver
```

## What's intentionally NOT here yet (later phases)

- Registration/invite flows (Soori Admin creating a Client + its first
  Client Admin; Client Admin creating Support Staff/Sub-Clients with
  generated credentials) — these need atomic User+Profile creation and
  probably email/notification hooks.
- Token/JWT auth wiring (settings.py currently only has
  SessionAuthentication for the browsable API in local dev).
- Actual audit log *writing* (signals or explicit calls in
  perform_create/update across the other apps).
- Fine-grained business rules layered on top of tenant scoping (e.g.
  "Support Staff only sees tickets assigned to them" vs a shared queue —
  flagged as a one-line toggle in `TicketViewSet.get_queryset`).
- Subscription enforcement (e.g. blocking access when `Client.status`
  is `suspended`/`cancelled`) — likely a permission class or middleware.
