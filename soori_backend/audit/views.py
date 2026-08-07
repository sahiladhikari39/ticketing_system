from rest_framework import permissions, viewsets

from core.permissions import CanViewAuditLog, IsClientSubscriptionActive, TenantScopedQuerySetMixin

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(TenantScopedQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    """
    Read-only on purpose: audit entries are written by application code
    at the point an action happens, not by any client-facing API call.

    Client Admin reads their own org's log -- NOT Soori Admin. An audit
    entry records a Client's own internal actions (who reassigned a
    ticket, etc.), which is exactly the kind of operational data the
    platform owner shouldn't have visibility into. See
    TenantScopedQuerySetMixin's docstring for the full reasoning.
    """

    queryset = AuditLog.objects.select_related("client", "actor")
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, CanViewAuditLog, IsClientSubscriptionActive]
