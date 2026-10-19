from django.urls import path
from .views import dashboard_page

from apps.accounts.views import accept_invite, tenant_login

urlpatterns = [
    path("login/", tenant_login, name="login"),
    path("invite/<str:uidb64>/<str:token>/", accept_invite, name="accept-invite"),
    path("", dashboard_page, name="dashboard"),
]
