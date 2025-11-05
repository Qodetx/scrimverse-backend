from django.contrib.auth.password_validation import validate_password

from rest_framework import serializers

from .models import HostProfile, PlayerProfile, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "username", "user_type", "phone_number", "profile_picture", "created_at")
        read_only_fields = ("id", "created_at")


class PlayerProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = PlayerProfile
        fields = "__all__"


class HostProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = HostProfile
        fields = "__all__"


class PlayerRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    in_game_name = serializers.CharField(required=True)
    game_id = serializers.CharField(required=True)

    class Meta:
        model = User
        fields = ("email", "username", "password", "password2", "phone_number", "in_game_name", "game_id")

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        # Remove password2 and profile fields
        validated_data.pop("password2")
        in_game_name = validated_data.pop("in_game_name")
        game_id = validated_data.pop("game_id")

        # Create user
        user = User.objects.create_user(
            email=validated_data["email"],
            username=validated_data["username"],
            password=validated_data["password"],
            user_type="player",
            phone_number=validated_data.get("phone_number", ""),
        )

        # Create player profile
        PlayerProfile.objects.create(user=user, in_game_name=in_game_name, game_id=game_id)

        return user


class HostRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    organization_name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ("email", "username", "password", "password2", "phone_number", "organization_name")

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        # Remove password2 and profile fields
        validated_data.pop("password2")
        organization_name = validated_data.pop("organization_name", "")

        # Create user
        user = User.objects.create_user(
            email=validated_data["email"],
            username=validated_data["username"],
            password=validated_data["password"],
            user_type="host",
            phone_number=validated_data.get("phone_number", ""),
        )

        # Create host profile
        HostProfile.objects.create(user=user, organization_name=organization_name)

        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    user_type = serializers.ChoiceField(choices=["player", "host"], required=True)
