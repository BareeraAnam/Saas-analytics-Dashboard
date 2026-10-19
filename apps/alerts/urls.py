from rest_framework.routers import DefaultRouter
from .views import AlertLogViewSet, AlertRuleViewSet

router = DefaultRouter()
router.register("alerts/rules", AlertRuleViewSet, basename="alertrule")
router.register("alerts/logs", AlertLogViewSet, basename="alertlog")
urlpatterns = router.urls
