import json
import logging

from django.conf import settings

logger = logging.getLogger("soori.errors")


class FrameAncestorsMiddleware:
    """
    Allows a specific external site to embed Soori in an iframe.

    Django's XFrameOptionsMiddleware sends `X-Frame-Options: DENY` by
    default, which blocks ALL framing -- correct while nothing embeds
    us, and exactly what stops the GNG site's /support page from
    rendering anything but a browser error.

    `X-Frame-Options` can't express "allow this one other origin": its
    only values are DENY and SAMEORIGIN, and support.<domain> framed by
    <domain> is a different ORIGIN even though it's the same site. The
    CSP `frame-ancestors` directive is the modern replacement that can,
    so this middleware REPLACES XFrameOptionsMiddleware (see the
    MIDDLEWARE list in settings.py) rather than sitting alongside it --
    two headers disagreeing about framing is how you get behaviour that
    differs per browser.

    Driven by DJANGO_FRAME_ANCESTORS (comma-separated origins). When
    that's unset, settings.py keeps Django's XFrameOptionsMiddleware
    instead and nothing can frame us -- the safe default is preserved
    by not opting in, never by configuring this loosely.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        origins = getattr(settings, "FRAME_ANCESTORS", []) or []
        # 'self' keeps our own pages able to frame each other; without
        # it, listing any ancestor implicitly excludes ourselves.
        self.header_value = "frame-ancestors 'self' " + " ".join(origins)

    def __call__(self, request):
        response = self.get_response(request)
        # Don't clobber a policy a view set deliberately.
        response.setdefault("Content-Security-Policy", self.header_value)
        return response


class LogBadRequestBodyMiddleware:
    """
    Django's default request logging shows only a status code and a
    byte count for a rejected request:

        Bad Request: /api/support-staff/
        "POST /api/support-staff/ HTTP/1.1" 400 43

    ...which tells you something was rejected but not WHAT, so you end
    up guessing. This prints the actual validation error body right in
    the terminal instead:

        [400] POST /api/support-staff/
              {"email": ["That email is already in use."]}

    Only active when DEBUG is True (see settings.py) -- a real
    deployment shouldn't be dumping request/response details to logs.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if response.status_code == 400 and request.path.startswith("/api/"):
            body = None
            try:
                # DRF responses expose .data before rendering; fall back
                # to the rendered content if that isn't available.
                if hasattr(response, "data"):
                    body = json.dumps(response.data, indent=2, default=str)
                elif hasattr(response, "content"):
                    body = response.content.decode("utf-8", errors="replace")
            except Exception:
                body = "<could not read response body>"

            print(f"\n[400 Bad Request] {request.method} {request.path}\n{body}\n")
            logger.warning("400 on %s %s: %s", request.method, request.path, body)

        return response
