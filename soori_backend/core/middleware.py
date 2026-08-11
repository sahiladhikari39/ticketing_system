import json
import logging

logger = logging.getLogger("soori.errors")


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
