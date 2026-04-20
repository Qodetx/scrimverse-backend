"""
User authentication and registration serializers.
"""
from django.contrib.auth.password_validation import validate_password

from rest_framework import serializers

from accounts.models import HostProfile, PlayerProfile, User


class UserSerializer(serializers.ModelSerializer):
    phone_verified = serializers.BooleanField(source='is_phone_verified', read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "user_type",
            "phone_number",
            "phone_verified",
            "profile_picture",
            "username_change_count",
            "last_username_change",
            "is_email_verified",
            "created_at",
        )
        read_only_fields = ("id", "username_change_count", "last_username_change", "is_email_verified", "phone_verified", "created_at")


class PlayerRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    phone_number = serializers.CharField(max_length=15, required=True)

    class Meta:
        model = User
        fields = ("email", "username", "password", "password2", "phone_number")

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        # Remove password2 and profile fields
        validated_data.pop("password2")

        # Create user
        user = User.objects.create_user(
            email=validated_data["email"],
            username=validated_data["username"],
            password=validated_data["password"],
            user_type="player",
            phone_number=validated_data.get("phone_number", ""),
        )

        # Create player profile
        PlayerProfile.objects.create(user=user)

        return user


class HostRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    phone_number = serializers.CharField(max_length=15, required=True)
    instagram = serializers.CharField(required=False, allow_blank=True, default='')
    youtube = serializers.CharField(required=False, allow_blank=True, default='')
    linkedin = serializers.CharField(required=False, allow_blank=True, default='')
    website = serializers.URLField(required=False, allow_blank=True, default='')

    class Meta:
        model = User
        fields = ("email", "username", "password", "password2", "phone_number", "instagram", "youtube", "linkedin", "website")

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def validate_phone_number(self, value):
        # Accept +CC format (e.g. +919876543210) or plain 10-digit number
        digits = value.lstrip('+')
        if not digits.isdigit():
            raise serializers.ValidationError("Phone number must contain only digits (with optional + prefix).")
        if len(digits) < 10 or len(digits) > 15:
            raise serializers.ValidationError("Phone number must be 10–15 digits.")
        return value

    def create(self, validated_data):
        validated_data.pop("password2")
        instagram = validated_data.pop("instagram", "")
        youtube = validated_data.pop("youtube", "")
        linkedin = validated_data.pop("linkedin", "")
        website = validated_data.pop("website", "")

        user = User.objects.create_user(
            email=validated_data["email"],
            username=validated_data["username"],
            password=validated_data["password"],
            user_type="host",
            phone_number=validated_data.get("phone_number"),
        )

        social_links = {}
        if instagram: social_links["instagram"] = instagram
        if youtube: social_links["youtube"] = youtube
        if linkedin: social_links["linkedin"] = linkedin

        HostProfile.objects.create(user=user, social_links=social_links, website=website)

        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    user_type = serializers.ChoiceField(choices=["player", "host"], required=True)
