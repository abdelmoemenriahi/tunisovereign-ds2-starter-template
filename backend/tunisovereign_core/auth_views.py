from rest_framework import generics, permissions
from rest_framework_simplejwt.views import TokenObtainPairView

from .auth_serializers import RegisterSerializer, TuniTokenObtainPairSerializer
from .models import StakeholderUser


class RegisterView(generics.CreateAPIView):
    queryset = StakeholderUser.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(TokenObtainPairView):
    serializer_class = TuniTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]