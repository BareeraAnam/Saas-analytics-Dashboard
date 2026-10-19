from rest_framework.routers import DefaultRouter
from .views import ReportScheduleViewSet

router = DefaultRouter()
router.register("reports", ReportScheduleViewSet, basename="report")
urlpatterns = router.urls
