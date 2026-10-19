from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import APIKeyViewSet, InviteView, SessionLoginView

router = DefaultRouter()
router.register("keys", APIKeyViewSet, basename="apikey")
urlpatterns = [
    path("login/", SessionLoginView.as_view()),
    path("users/invite/", InviteView.as_view()),
] + router.urls
