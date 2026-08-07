# Soori Phase 2 — JWT Auth + CORS

This phase makes the API usable by a real frontend (React, on a
different origin/port than this API) instead of only the Django admin
and DRF's browsable API. Nothing from Phase 1 changed behavior-wise —
tenant scoping and role filtering work exactly as before, just now
provable with Bearer tokens instead of only session cookies.

Everything below was actually run against a live database while
building this phase: token issuance, the refresh flow, tenant scoping
over pure Bearer auth (zero cookies), and CORS header behavior for
both an allowed and a disallowed origin.

---

## 1. What was added

- `djangorestframework-simplejwt` for JWT issuance/verification
- `django-cors-headers` so a frontend running on a different port can
  actually call this API from the browser
- `accounts/serializers.py` — `SooriTokenObtainPairSerializer`,
  `UserSerializer`
- `accounts/views.py` — `SooriTokenObtainPairView`, `MeView`
- `accounts/urls.py` — `/api/token/`, `/api/token/refresh/`,
  `/api/token/verify/`, `/api/me/`
- Settings changes: `SIMPLE_JWT` config, `CORS_ALLOWED_ORIGINS`,
  `DEFAULT_AUTHENTICATION_CLASSES` now tries JWT first, falls back to
  session auth

## 2. Why JWT, and why these specific choices

**Why not just keep session auth?** Session auth relies on a cookie
tied to server-side session state and the same origin (or careful
cross-origin cookie config, which gets messy fast). A React SPA
talking to a separately-hosted API is the textbook case for token
auth instead: the frontend gets a token once at login, stores it, and
sends it as an `Authorization: Bearer <token>` header on every request
— no cookies, no CSRF dance, works the same whether the frontend is on
`localhost:3000` or a deployed domain later.

**Why keep session auth too** (`DEFAULT_AUTHENTICATION_CLASSES` has
both)? DRF tries each authentication class in order and uses the first
one that succeeds — there's no conflict. Session auth staying in the
list is what keeps the Django admin and the browsable API's "Log in"
link working for local development, without which you'd lose a
convenient way to poke at the API manually.

**Why 30-minute access tokens + 7-day refresh tokens with rotation?**
A leaked access token (e.g. via browser dev tools, an XSS bug, a
compromised dependency) is only useful for 30 minutes. The frontend is
expected to silently call `/api/token/refresh/` when it gets a 401,
rather than forcing a re-login every 30 minutes. `ROTATE_REFRESH_TOKENS
= True` issues a new refresh token on every refresh call — combined
with token blacklisting (not set up yet, flagged below), that's what
would let you actually revoke a specific session instead of it quietly
working for the full 7 days no matter what.

**Why custom claims (`role`, `client_id`) baked into the JWT itself,**
not just returned once in the login response? The frontend can decode
the JWT locally (it's just base64 — no network call) to know the
user's role and tenant immediately on page load or after a browser
refresh, without waiting on a round trip to `/api/me/`. Every
authenticated request already carries the token, so anything that
wants "who is this, what tenant" (logging, per-tenant rate limiting,
etc.) can read it straight off the validated token with no DB hit.

The trade-off: this data is only as fresh as the token. If someone's
role changes mid-session, they won't see that reflected until their
access token refreshes — a bounded 30-minute staleness window here,
not a permanent one. If you ever need instant role-change propagation,
that requires blacklisting their existing tokens on the change, which
isn't built yet.

**Why a `/api/me/` endpoint at all, if the JWT already has role/client
in it?** The token payload only carries what you explicitly put there
— it doesn't have email, full name, etc. `/api/me/` is a convenience
so the frontend can fetch the full profile without you having to keep
stuffing more fields into every JWT (which also makes tokens bigger on
every single request, not just the one time you need the extra data).

## 3. Why CORS needed configuring at all

Your React dev server (`localhost:3000` for Create React App,
`localhost:5173` for Vite) is a **different origin** than this API
(`localhost:8000`), even though both are "localhost." Browsers block
cross-origin requests by default unless the server explicitly opts
in via CORS headers — this isn't a Django-specific restriction, it's
built into every browser. `CORS_ALLOWED_ORIGINS` is the explicit
allow-list; anything not on it gets silently blocked by the browser
itself, which is what the test in section 5 demonstrates.

**Update this list** once you know your frontend's actual dev port —
if it's not 3000 or 5173, add it — and again when you deploy, with
your real frontend domain.

## 4. How to run it

Same as before, plus the two new dependencies:

```bash
pip install djangorestframework-simplejwt django-cors-headers
# or: pip install -r requirements.txt
python manage.py migrate     # no new migrations this phase, but harmless to run
python manage.py seed_demo   # if you haven't already
python manage.py runserver
```

## 5. How to test the JWT flow

### Get a token

```bash
curl -X POST http://127.0.0.1:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "acme_customer1", "password": "demo12345"}'
```

Expected response shape:

```json
{
  "refresh": "eyJ...",
  "access": "eyJ...",
  "user": {
    "id": "...",
    "username": "acme_customer1",
    "email": "cust1@acmeclient.com",
    "first_name": "",
    "last_name": "",
    "role": "sub_client",
    "client": "..."
  }
}
```

### Use the access token

```bash
curl http://127.0.0.1:8000/api/me/ \
  -H "Authorization: Bearer <paste the access token here>"
```

```bash
curl http://127.0.0.1:8000/api/tickets/ \
  -H "Authorization: Bearer <access token>"
```

**Expected results (confirmed while building this phase) — this
should match Phase 1's table exactly, just via Bearer token instead of
a session cookie:**

| User | `/api/tickets/` via Bearer token |
|---|---|
| `acme_customer1` | only *"Cannot reset my password"* |
| `acme_admin` | both Acme tickets |
| `soori_admin` | all 3 tickets, both tenants |

If you ever see different results between session-auth testing
(Phase 1) and JWT testing (this phase) for the *same* user, that's a
bug in the auth wiring, not in the tenant-scoping logic itself — the
scoping mixin doesn't care which authentication class authenticated
the request.

### Refresh a token

```bash
curl -X POST http://127.0.0.1:8000/api/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh": "<paste refresh token here>"}'
```

Returns a new `access` token (and, because `ROTATE_REFRESH_TOKENS` is
on, a new `refresh` token too — the frontend should store the new one
and discard the old).

### Confirm the custom claims are actually in the token

JWTs are just base64-encoded JSON with a signature — you can decode
the payload (2nd of the 3 dot-separated segments) without any library:

```bash
python3 -c "
import json, base64
token = '<paste access token here>'
payload_b64 = token.split('.')[1]
payload_b64 += '=' * (-len(payload_b64) % 4)
print(json.loads(base64.urlsafe_b64decode(payload_b64)))
"
```

You should see `"role"` and `"client_id"` in the decoded output
alongside the standard JWT fields (`exp`, `iat`, `user_id`, etc.).

### Confirm CORS is actually doing something

```bash
curl -I http://127.0.0.1:8000/api/tickets/ \
  -H "Authorization: Bearer <access token>" \
  -H "Origin: http://localhost:3000"
```

Look for `Access-Control-Allow-Origin: http://localhost:3000` in the
response headers. Now try an origin that's NOT in
`CORS_ALLOWED_ORIGINS`:

```bash
curl -I http://127.0.0.1:8000/api/tickets/ \
  -H "Authorization: Bearer <access token>" \
  -H "Origin: http://evil-site.com"
```

That header should be **absent** — confirmed while building this: a
disallowed origin gets no `Access-Control-Allow-Origin` header at all,
which is what makes the browser block the response from ever reaching
frontend JS, even though the server technically still processed the
request server-side.

## 6. What's still not done (updated from Phase 1's list)

- ~~Token/JWT auth~~ — done this phase.
- **Token blacklisting on logout/role-change** — right now, a refresh
  token is valid for its full 7-day lifetime no matter what; there's
  no way to forcibly invalidate one early (e.g. on password change, or
  an admin revoking access). `rest_framework_simplejwt.token_blacklist`
  is the standard add-on for this — flag if you want it next.
- **Registration/invite flows** — still nothing lets a Soori Admin
  onboard a new Client, or a Client Admin create Support
  Staff/Sub-Clients, through the API. All demo users exist only
  because `seed_demo` created them directly via the ORM.
- **Audit log writing** — still nothing calls
  `AuditLog.objects.create(...)` from application code.
- **Subscription enforcement** — a `Client` with `status=suspended`
  still has fully working API access for its users.
- **Rate limiting on `/api/token/`** — login endpoints are a common
  brute-force target; nothing throttles repeated failed attempts yet.
