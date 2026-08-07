from rest_framework.routers import DefaultRouter

from .history_requests import HistoryAccessRequestViewSet
from .views import ServiceReportViewSet, TicketCommentViewSet, TicketViewSet

router = DefaultRouter()
router.register("tickets", TicketViewSet, basename="ticket")
router.register("ticket-comments", TicketCommentViewSet, basename="ticket-comment")
router.register("service-reports", ServiceReportViewSet, basename="service-report")
router.register("history-access-requests", HistoryAccessRequestViewSet, basename="history-access-request")

urlpatterns = router.urls
