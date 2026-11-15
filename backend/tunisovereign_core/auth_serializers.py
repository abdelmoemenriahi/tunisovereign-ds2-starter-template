from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import StakeholderUser


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = StakeholderUser
        fields = ("username", "email", "password", "institution",
                  "governorate", "wallet_address", "preferred_dialect")

    def create(self, validated_data):
        # Public signup is always a STUDENT: nobody can self-assign an admin role.
        return StakeholderUser.objects.create_user(
            role=StakeholderUser.Role.STUDENT, **validated_data
        )


class TuniTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["institution"] = user.institution
        token["governorate"] = user.governorate
        token["wallet_address"] = user.wallet_address or ""
        return token