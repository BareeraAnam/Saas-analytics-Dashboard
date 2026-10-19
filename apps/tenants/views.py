from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import PendingSignup
from .serializers import SIGNUP_TTL, SignupSerializer, hash_token
from .tasks import provision_tenant


class SignupView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "signup"

    def post(self, request):
        incoming = SignupSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        incoming.save()
        return Response(
            {"detail": "Check your email to finish creating the workspace."},
            status=202,
        )


class VerifySignupView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, token):
        pending = PendingSignup.objects.filter(token_hash=hash_token(token)).first()
        if pending is None or timezone.now() - pending.created_at > SIGNUP_TTL:
            return Response({"detail": "Invalid or expired link."}, status=400)
        if pending.status == PendingSignup.DONE:
            return Response({"detail": "Workspace is ready."})
        # Schema creation runs in the worker, not in this request.
        # A missing Redis used to raise a 500 after the user had already confirmed.
        try:
            provision_tenant.delay(pending.id)
        except Exception:
            return Response(
                {"detail": "Redis is not reachable. Start Redis and the Celery worker, then open this link again."},
                status=503,
            )
        return Response({"detail": "Confirmed. The workspace is being created. The Celery worker must be running."})
