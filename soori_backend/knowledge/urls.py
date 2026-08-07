from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AccessCodeLoginView, AccessCodeViewSet, KnowledgeBaseViewSet

router = DefaultRouter()
router.register("access-codes", AccessCodeViewSet, basename="access-code")
router.register("knowledge-base", KnowledgeBaseViewSet, basename="knowledge-base")

urlpatterns = router.urls + [
    path("access/login/", AccessCodeLoginView.as_view(), name="access-code-login"),
]
