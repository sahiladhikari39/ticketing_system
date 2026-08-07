from rest_framework.routers import DefaultRouter

from .views import ClientViewSet, StaffRoleViewSet, SubClientViewSet, SupportStaffViewSet

router = DefaultRouter()
router.register("clients", ClientViewSet, basename="client")
router.register("support-staff", SupportStaffViewSet, basename="support-staff")
router.register("sub-clients", SubClientViewSet, basename="sub-client")
router.register("staff-roles", StaffRoleViewSet, basename="staff-role")

urlpatterns = router.urls
