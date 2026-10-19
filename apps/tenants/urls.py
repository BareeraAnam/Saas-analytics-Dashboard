from django.urls import path

from .views import SignupView, VerifySignupView

urlpatterns = [
    path("signup/", SignupView.as_view()),
    path("signup/verify/<str:token>/", VerifySignupView.as_view()),
]
