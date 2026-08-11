import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

import secrets

# ---------------------------------------------------------------------
# Core security settings.
#
# All three read from the environment and default to the SAFE choice,
# so a deployment that forgets to configure something fails loudly
# rather than silently running wide open. Local development opts IN to
# the relaxed behaviour via .env -- see .env.example.
# ---------------------------------------------------------------------

# DEBUG defaults to FALSE. This is the important direction: a
# misconfigured production box runs safely, while a developer who
# forgets to set it just gets a less chatty error page. The reverse
# default (True) leaks tracebacks, settings, and SQL to the internet
# the first time anything errors.
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() in ("1", "true", "yes")

# The SECRET_KEY signs sessions, password-reset tokens and JWTs -- if
# it leaks or is guessable, those can all be forged. It was previously
# the literal string "test", which is exactly as weak as it looks.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        # Ephemeral key for local dev. Regenerated per process, so
        # restarting the server logs everyone out -- harmless locally,
        # and a nudge that this isn't a real key.
        SECRET_KEY = secrets.token_urlsafe(64)
    else:
        raise RuntimeError(
            "DJANGO_SECRET_KEY must be set when DEBUG is off. "
            "Generate one with:\n"
            "  python -c \"import secrets; print(secrets.token_urlsafe(64))\"\n"
            "then put it in your .env file as DJANGO_SECRET_KEY=..."
        )

# Which hostnames this site will answer to. "*" accepts anything, which
# enables Host-header poisoning (an attacker can make password-reset
# links point at their own domain). Comma-separated in .env, e.g.
#   DJANGO_ALLOWED_HOSTS=soori.example.com,www.soori.example.com
_allowed = os.environ.get("DJANGO_ALLOWED_HOSTS", "")
if _allowed:
    ALLOWED_HOSTS = [h.strip() for h in _allowed.split(",") if h.strip()]
elif DEBUG:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"]
else:
    raise RuntimeError(
        "DJANGO_ALLOWED_HOSTS must be set when DEBUG is off, e.g.\n"
        "  DJANGO_ALLOWED_HOSTS=your-domain.com,www.your-domain.com"
    )

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    # local apps
    "accounts",
    "clients",
    "tickets",
    "audit",
    "knowledge",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Must sit before CommonMiddleware (and as early as possible overall)
    # so CORS headers get added before any other middleware can short-
    # circuit the response.
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Sends X-Frame-Options, which stops another site embedding Soori in
    # a hidden iframe and tricking a logged-in user into clicking things
    # they can't see (clickjacking).
    #
    # Swapped for FrameAncestorsMiddleware below when an embedding host
    # IS configured -- see the FRAME_ANCESTORS block further down.
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Origins allowed to embed Soori in an iframe, e.g.
#   DJANGO_FRAME_ANCESTORS=https://globalnepalgroup.com
# Unset (the default) means nothing may frame us at all.
_frame_ancestors = os.environ.get("DJANGO_FRAME_ANCESTORS", "")
FRAME_ANCESTORS = [o.strip() for o in _frame_ancestors.split(",") if o.strip()]

if FRAME_ANCESTORS:
    # REPLACE rather than append: X-Frame-Options: DENY and a CSP that
    # permits framing are contradictory instructions, and which one wins
    # varies by browser. Only one framing header should ever be sent.
    MIDDLEWARE = [
        "core.middleware.FrameAncestorsMiddleware"
        if m == "django.middleware.clickjacking.XFrameOptionsMiddleware"
        else m
        for m in MIDDLEWARE
    ]

if DEBUG:
    # Prints the ACTUAL body of any rejected API request to the
    # terminal, instead of Django's default "400 43" which tells you
    # nothing about what was wrong. Dev only -- see core/middleware.py.
    MIDDLEWARE.append("core.middleware.LogBadRequestBodyMiddleware")

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ]},
    },
]

# ---------------------------------------------------------------------
# Database.
#
# Defaults to SQLite so a fresh clone runs with no database to install
# and no configuration at all. Switching to Postgres is a .env change,
# never a code change:
#
#   DB_ENGINE=django.db.backends.postgresql
#   DB_NAME=soori_db
#   DB_USER=postgres
#   DB_PASSWORD=...
#   DB_HOST=localhost
#   DB_PORT=5432
#
# Why a branch instead of one dict: SQLite is a FILE, so NAME is a
# filesystem path (hence BASE_DIR /) and user/password/host/port are
# meaningless. Every other backend is a network service where NAME is
# just a database name and the connection details are what matter.
# Passing a BASE_DIR path to Postgres, or credentials to SQLite, is
# how you get errors that don't say what's actually wrong.
#
# SQLite is fine for local development, but NOT for a real deployment:
# most hosts wipe the disk on redeploy (taking every ticket with it),
# and it locks the whole database on writes, so concurrent users hit
# "database is locked".
# ---------------------------------------------------------------------
DB_ENGINE = os.environ.get("DB_ENGINE", "django.db.backends.sqlite3")
DB_NAME = os.environ.get("DB_NAME", "db.sqlite3")

if DB_ENGINE == "django.db.backends.sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": DB_ENGINE,
            "NAME": BASE_DIR / DB_NAME,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": DB_ENGINE,
            "NAME": DB_NAME,
            "USER": os.environ.get("DB_USER", ""),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", ""),
            "PORT": os.environ.get("DB_PORT", ""),
            # Hold connections open for reuse instead of opening a new
            # one per request. Negligible for SQLite (it's a file open),
            # but every Postgres connection is a TCP handshake plus
            # authentication -- paying that on every request is a real,
            # measurable cost.
            "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "600")),
        }
    }

# Locale. TIME_ZONE is worth setting deliberately: it decides what
# timezone ticket timestamps are displayed in. Left at UTC, a ticket
# raised at 3pm in Kathmandu reads as 09:15 -- set TIME_ZONE=Asia/Kathmandu
# in .env if the people using this are there.
LANGUAGE_CODE = os.environ.get("LANGUAGE_CODE", "en-us")
TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")
USE_I18N = True
# Timestamps are stored in UTC and converted on display. Keep this on.
USE_TZ = True

AUTH_USER_MODEL = "accounts.User"

# Enforced whenever a password is set via Django's normal validate_password()
# call -- including the new change-password endpoint below. Standard
# Django defaults: rejects passwords too similar to the user's own
# username/email, too short, too common (checked against a known list
# of the most-used passwords), or purely numeric.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Console backend prints emails to the terminal instead of really
# sending them -- used automatically whenever real email credentials
# (below) aren't set, so local dev never NEEDS a Gmail account just to
# run the project.
#
# When EMAIL_HOST_USER + EMAIL_HOST_PASSWORD ARE set (via a .env file
# -- see .env.example), this switches to Gmail's real SMTP server
# instead. Two things about that password specifically, since this is
# the #1 way real Gmail SMTP fails:
# 1. It must be a Gmail "App Password", NOT your normal account
#    password -- Google has blocked regular-password SMTP login since
#    2022. An App Password only exists once 2-Step Verification is
#    turned on for that Google account (Google Account -> Security ->
#    2-Step Verification -> App passwords).
# 2. It's a 16-character code with no spaces when you paste it into
#    .env, even though Google displays it with spaces on their site.
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")

# Treat the template's placeholder values as "not configured".
#
# Copying .env.example over a working .env used to substitute these
# literal placeholders, which are non-empty and so looked configured:
# the app switched to real SMTP, stopped printing emails to the
# terminal, and then silently failed against Gmail. Worst of both --
# no console output AND no delivered mail. Recognising them means that
# mistake now just falls back to console printing, which is obvious
# and harmless.
_PLACEHOLDERS = {"youraddress@gmail.com", "your16digitapppassword"}
if EMAIL_HOST_USER in _PLACEHOLDERS or EMAIL_HOST_PASSWORD in _PLACEHOLDERS:
    EMAIL_HOST_USER = ""
    EMAIL_HOST_PASSWORD = ""
    EMAIL_CREDENTIALS_ARE_PLACEHOLDERS = True
else:
    EMAIL_CREDENTIALS_ARE_PLACEHOLDERS = False

if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "smtp.gmail.com"
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    DEFAULT_FROM_EMAIL = "noreply@soori.example.com"

# Send notification emails on a background thread so the HTTP response
# doesn't wait for SMTP. Real SMTP costs roughly a second per message,
# and several actions notify multiple people -- assigning a ticket
# emails the engineer AND every service manager. Measured before this:
# a single assignment took 1.75s, nearly all of it waiting on mail.
# After: 0.146s.
#
# Test commands set this False so they can check mail.outbox
# deterministically instead of racing the thread.
EMAIL_SEND_ASYNC = True

# Required by django.contrib.staticfiles (in INSTALLED_APPS) even though
# this project barely uses static files yet -- omitting it raises
# ImproperlyConfigured as soon as you run the dev server.
STATIC_URL = "static/"

# Where uploaded ticket attachments actually live on disk, and the URL
# prefix used to serve them back. Only wired to actually serve files in
# urls.py when DEBUG=True -- a real deployment would serve these via
# nginx/S3/etc., not Django itself.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# General safety cap on non-file request bodies. NOTE: multipart file
# uploads (like ticket attachments) are streamed to disk regardless of
# this setting -- the actual per-file size cap is enforced explicitly
# in TicketAttachmentSerializer.validate_file(), not here.
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # JWT first: this is what the React frontend will actually use.
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        # Session auth kept too: this is what makes the Django admin
        # AND the DRF browsable API's "Log in" link keep working for
        # local development/debugging. DRF tries each authentication
        # class in order and uses the first one that succeeds, so
        # having both doesn't create a conflict.
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": "core.exception_handlers.exception_handler",
}

SIMPLE_JWT = {
    # Short-lived access tokens limit the damage window if one leaks
    # (e.g. via browser dev tools, a compromised frontend dependency).
    # The frontend is expected to silently call /api/token/refresh/
    # when it gets a 401, rather than making the user re-login every
    # 30 minutes.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    # Issues a brand-new refresh token on every refresh call, which
    # (combined with token blacklisting, not set up yet -- see the
    # guide) is what lets you actually revoke a compromised session
    # instead of it silently working for the full 7 days regardless.
    "ROTATE_REFRESH_TOKENS": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# CORS: the React dev server runs on a different origin (port) than
# this API, so the browser blocks the frontend's requests unless the
# API explicitly allows that origin.
#
# Env-driven for the same reason DEBUG and ALLOWED_HOSTS are: a
# deployment shouldn't have to edit source to name its own frontend,
# and a hardcoded list quietly shipping localhost origins to
# production is exactly the kind of thing nobody notices. Set:
#   DJANGO_CORS_ALLOWED_ORIGINS=https://support.example.com,https://example.com
#
# The dev fallback covers Create React App's default port (3000) and
# Vite's (5173), and applies ONLY when DEBUG is on -- with DEBUG off
# and nothing configured, no cross-origin caller is allowed, which
# fails visibly rather than half-working.
_cors = os.environ.get("DJANGO_CORS_ALLOWED_ORIGINS", "")
if _cors:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors.split(",") if o.strip()]
elif DEBUG:
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
else:
    CORS_ALLOWED_ORIGINS = []

# Origins Django will accept unsafe (POST/PUT/DELETE) requests from
# when a CSRF token is involved -- the Django admin and DRF's browsable
# API both need this once they're served over HTTPS behind a proxy.
# The JWT API path doesn't use CSRF at all (Bearer tokens aren't sent
# automatically by the browser, which is the thing CSRF protects
# against), so this is not what makes the React app work.
_csrf = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf.split(",") if o.strip()]

# NOTE: there's deliberately no FRONTEND_URL setting here anymore.
# Password resets use an emailed 6-digit CODE rather than a link, so
# nothing needs to know where the frontend lives -- which means one
# less thing to get wrong when deploying. Code lifetime and attempt
# limits live on the PasswordResetOTP model instead.


# ---------------------------------------------------------------------
# HTTPS and cookie hardening.
#
# Applied only when DEBUG is off, because every one of these assumes a
# real HTTPS certificate. Turning them on locally would redirect
# http://localhost to https://localhost, which has no certificate, and
# the site would simply stop loading.
# ---------------------------------------------------------------------
if not DEBUG:
    # Redirect any plain-HTTP request to HTTPS. If you deploy behind a
    # load balancer or reverse proxy that already terminates TLS, set
    # DJANGO_SSL_REDIRECT=false and let the proxy handle it instead --
    # otherwise the two can fight and cause a redirect loop.
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SSL_REDIRECT", "true").lower() in ("1", "true", "yes")

    # Tells the browser "only ever reach this site over HTTPS", so it
    # won't even attempt an insecure first request that could be
    # intercepted.
    #
    # Deliberately starts at 1 hour, not the usual year. HSTS is
    # effectively irreversible for its duration -- browsers cache it,
    # so if HTTPS breaks after setting a long value, visitors are
    # locked out with no way for you to undo it remotely. Verify HTTPS
    # works properly, then raise this to 31536000 (one year).
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False

    # Never send these cookies over plain HTTP, where they could be
    # read off the wire and used to hijack a session.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # Blocks JavaScript from reading the session cookie, limiting the
    # damage if a cross-site scripting bug ever slips in.
    SESSION_COOKIE_HTTPONLY = True

    # Stops browsers second-guessing declared content types, which can
    # turn an uploaded file into executable script.
    SECURE_CONTENT_TYPE_NOSNIFF = True

    # Needed when running behind a proxy/load balancer that terminates
    # TLS: without it Django sees plain HTTP internally and would
    # redirect forever. Harmless if the header isn't present.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# ---------------------------------------------------------------------
# Password hashing.
#
# Argon2 first, PBKDF2 kept behind it. This is faster AND stronger, not
# a tradeoff between the two:
#
#   - Faster: measured 0.352s vs 0.815s for PBKDF2 on this hardware.
#     Hashing happens on every account creation and every login, and
#     it was the single biggest remaining delay when creating a staff
#     member or customer -- the whole request took ~1s, almost all of
#     it here.
#   - Stronger: Argon2 won the Password Hashing Competition and is
#     OWASP's current first recommendation. Unlike PBKDF2 it's
#     deliberately memory-hard, which is what makes it resistant to
#     the GPU/ASIC cracking rigs that make PBKDF2 comparatively cheap
#     to attack at scale.
#
# The point of a slow hash is that cracking a stolen password database
# stays expensive, so this is NOT achieved by lowering the work factor
# -- Django's Argon2 defaults are used as-is.
#
# PBKDF2 stays listed second so passwords hashed BEFORE this change
# still verify. Django re-hashes each one with Argon2 automatically on
# that user's next successful login, so the migration happens on its
# own with nobody forced to reset anything.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]
