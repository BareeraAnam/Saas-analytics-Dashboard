from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import redirect, render
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import APIKey, Membership
from .permissions import IsOwner, IsTenantMember


class APIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        # signing_secret is not listed. It is returned once from create().
        fields = ["id", "name", "key_id", "prefix", "is_active", "created_at", "last_used_at"]
        read_only_fields = ["key_id", "prefix", "created_at", "last_used_at"]


class APIKeyViewSet(viewsets.ModelViewSet):
    queryset = APIKey.objects.all().order_by("-created_at")
    serializer_class = APIKeySerializer
    permission_classes = [IsTenantMember]

    def create(self, request, *args, **kwargs):
        obj, raw, signing_secret = APIKey.create_key(request.data.get("name", "default"))
        data = APIKeySerializer(obj).data
        # Shown once. The raw key authenticates ingest. The signing secret
        # stays on the server and is only used to check webhook signatures.
        data["key"] = raw
        data["signing_secret"] = signing_secret
        return Response(data, status=201)


class SessionLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        user = authenticate(
            request,
            username=request.data.get("username", ""),
            password=request.data.get("password", ""),
        )
        if user is None or not user.is_active or not hasattr(user, "membership"):
            return Response({"detail": "invalid credentials"}, status=401)
        login(request, user)
        return Response({"email": user.email, "role": user.membership.role})


class InviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=[Membership.MEMBER, Membership.VIEWER])


class InviteView(APIView):
    permission_classes = [IsOwner]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invite"

    def post(self, request):
        incoming = InviteSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        email = incoming.validated_data["email"]
        role = incoming.validated_data["role"]
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError({"email": "A user with this email already exists."})
        user = User.objects.create(username=email, email=email, is_active=True)
        user.set_unusable_password()
        user.save()
        Membership.objects.create(user=user, role=role)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        # Use the stored domain, not the Host header, so the link cannot be rewritten.
        from django.db import connection
        primary = connection.tenant.get_primary_domain()
        scheme = "https" if not settings.DEBUG else "http"
        port = "" if not settings.DEBUG else ":8000"
        link = f"{scheme}://{primary.domain}{port}/invite/{uid}/{token}/"
        from django.core.mail import send_mail
        send_mail(
            "You were invited",
            f"Set your password: {link}",
            None,
            [email],
        )
        return Response({"email": email, "role": role}, status=201)


def tenant_login(request):
    # Separate from /admin/login/ so a member who is not staff can open the dashboard.
    if request.user.is_authenticated:
        return redirect("/")
    error = ""
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username", ""),
            password=request.POST.get("password", ""),
        )
        if user is not None and user.is_active and hasattr(user, "membership"):
            login(request, user)
            return redirect("/")
        error = "Invalid credentials"
    return render(request, "accounts/login.html", {"error": error})


def accept_invite(request, uidb64, token):
    User = get_user_model()
    user = None
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError):
        user = None
    valid = user is not None and default_token_generator.check_token(user, token)
    error = ""
    if request.method == "POST" and valid:
        password = request.POST.get("password", "")
        if len(password) < 8:
            error = "Password must be at least 8 characters."
        else:
            user.set_password(password)
            user.save()
            return redirect("/login/")
    return render(request, "accounts/accept_invite.html", {"valid": valid, "error": error})
