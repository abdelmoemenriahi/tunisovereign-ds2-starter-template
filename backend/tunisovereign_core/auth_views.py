from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .auth_serializers import RegisterSerializer, TuniTokenObtainPairSerializer
from .models import StakeholderUser
from .permissions import IsNationalAdmin


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ - public signup, always creates a STUDENT."""

    queryset = StakeholderUser.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(TokenObtainPairView):
    """POST /api/auth/login/ - returns access + refresh tokens with role claims."""

    serializer_class = TuniTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]


class MeView(APIView):
    """GET /api/auth/me/ - any logged-in user: who am I?"""

    def get(self, request):
        u = request.user
        return Response(
            {
                "username": u.username,
                "role": u.role,
                "institution": u.institution,
                "governorate": u.governorate,
                "wallet_address": u.wallet_address or "",
            }
        )


class AdminOnlyView(APIView):
    """GET /api/auth/admin-only/ - 403 unless role == NATIONAL_ADMIN (RBAC demo)."""

    permission_classes = [IsNationalAdmin]

    def get(self, request):
        return Response({"detail": "Welcome, national admin."})
