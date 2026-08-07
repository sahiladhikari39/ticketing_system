from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),
    path("api/", include("clients.urls")),
    path("api/", include("tickets.urls")),
    path("api/", include("audit.urls")),
    path("api/", include("knowledge.urls")),
    # Powers the "Log in" / "Log out" links in DRF's browsable API.
    # Without this, the browsable API has nowhere to send you when you
    # click Log in, so it silently omits the link entirely.
    path("api-auth/", include("rest_framework.urls")),
]

if settings.DEBUG:
    # Only for local dev -- a real deployment serves uploaded files via
    # nginx, S3, or similar, never through Django itself.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
