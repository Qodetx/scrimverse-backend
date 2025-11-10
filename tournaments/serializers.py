import json

from rest_framework import serializers

from accounts.serializers import HostProfileSerializer, PlayerProfileSerializer

from .models import HostRating, Scrim, ScrimRegistration, Tournament, TournamentRegistration


class TournamentSerializer(serializers.ModelSerializer):
    host = HostProfileSerializer(read_only=True)
    host_id = serializers.IntegerField(write_only=True, required=False)
    banner_image = serializers.ImageField(
        max_length=None, use_url=True, required=False, allow_null=True, allow_empty_file=True
    )
    tournament_file = serializers.FileField(
        max_length=None, use_url=True, required=False, allow_null=True, allow_empty_file=True
    )
    rounds = serializers.JSONField(required=False)

    class Meta:
        model = Tournament
        fields = "__all__"
        read_only_fields = ("current_participants", "created_at", "updated_at", "host")

    def validate_banner_image(self, value):
        """Validate banner image size (max 5MB)"""
        if value and value.size > 5 * 1024 * 1024:  # 5MB
            raise serializers.ValidationError("Banner image size should not exceed 5MB")
        return value

    def validate_rounds(self, value):
        """Validate rounds structure"""
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid JSON format for rounds")

        if not value or len(value) == 0:
            raise serializers.ValidationError("At least one round is required")

        for i, round_data in enumerate(value):
            if "round" not in round_data:
                raise serializers.ValidationError(f"Round {i+1} must have 'round' field")
            if i == 0:
                if "max_teams" not in round_data:
                    raise serializers.ValidationError("First round must have 'max_teams' field")
            else:
                if "qualifying_teams" not in round_data:
                    raise serializers.ValidationError(f"Round {i+1} must have 'qualifying_teams' field")

        return value


class TournamentListSerializer(serializers.ModelSerializer):
    """Simplified serializer for list views"""

    host_name = serializers.CharField(source="host.organization_name", read_only=True)
    host = serializers.SerializerMethodField()

    class Meta:
        model = Tournament
        fields = (
            "id",
            "title",
            "game_name",
            "game_mode",
            "host_name",
            "host",
            "max_participants",
            "current_participants",
            "entry_fee",
            "prize_pool",
            "tournament_start",
            "status",
            "banner_image",
            "is_featured",
        )

    def get_host(self, obj):
        return {"id": obj.host.id, "organization_name": obj.host.organization_name}


class ScrimSerializer(serializers.ModelSerializer):
    host = HostProfileSerializer(read_only=True)
    host_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = Scrim
        fields = "__all__"
        read_only_fields = ("current_participants", "created_at", "updated_at")


class ScrimListSerializer(serializers.ModelSerializer):
    """Simplified serializer for list views"""

    host_name = serializers.CharField(source="host.organization_name", read_only=True)

    class Meta:
        model = Scrim
        fields = (
            "id",
            "title",
            "game_name",
            "game_mode",
            "host_name",
            "max_participants",
            "current_participants",
            "entry_fee",
            "scrim_start",
            "status",
            "banner_image",
            "is_featured",
        )


class TournamentRegistrationSerializer(serializers.ModelSerializer):
    player = PlayerProfileSerializer(read_only=True)
    player_id = serializers.IntegerField(write_only=True, required=False)
    tournament = TournamentListSerializer(read_only=True)
    tournament_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = TournamentRegistration
        fields = "__all__"
        read_only_fields = ("player", "tournament", "registered_at", "updated_at")


class ScrimRegistrationSerializer(serializers.ModelSerializer):
    player = PlayerProfileSerializer(read_only=True)
    player_id = serializers.IntegerField(write_only=True, required=False)
    scrim = ScrimListSerializer(read_only=True)
    scrim_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = ScrimRegistration
        fields = "__all__"
        read_only_fields = ("player", "scrim", "registered_at", "updated_at")


class HostRatingSerializer(serializers.ModelSerializer):
    player = PlayerProfileSerializer(read_only=True)
    player_id = serializers.IntegerField(write_only=True, required=False)
    host_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = HostRating
        fields = "__all__"
        read_only_fields = (
            "player",
            "host",
            "created_at",
        )

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5")
        return value
