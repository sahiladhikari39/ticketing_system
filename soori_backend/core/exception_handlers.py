from rest_framework.views import exception_handler as drf_default_exception_handler


def exception_handler(exc, context):
    """
    DRF's default exception handling only ever returns {"detail": "..."}
    for a permission denial -- there's no way for a frontend to tell
    "you're not allowed" apart from "your subscription lapsed" without
    fragile string-matching on the message text itself.

    This wraps the default handler and adds a `code` field whenever the
    permission class that raised the denial set one (see
    IsClientSubscriptionActive in core/permissions.py, which sets
    self.code = "subscription_inactive"). Any future permission class
    can opt into the same pattern just by setting `self.code` before
    returning False from has_permission().
    """
    response = drf_default_exception_handler(exc, context)
    if response is not None:
        code = getattr(exc, "get_codes", lambda: None)()
        if isinstance(code, str) and code != "permission_denied":
            response.data["code"] = code
    return response
