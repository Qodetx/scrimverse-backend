from rest_framework import serializers

from accounts.serializers import HostProfileSerializer, PlayerProfileSerializer

from .models import HostRating, Scrim, ScrimRegistration, Tournament, TournamentRegistration


class TournamentSerializer(serializers.ModelSerializer):
    host = HostProfileSerializer(read_only=True)
    host_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = Tournament
        fields = "__all__"
        read_only_fields = ("current_participants", "created_at", "updated_at")


class TournamentListSerializer(serializers.ModelSerializer):
    """Simplified serializer for list views"""

    host_name = serializers.CharField(source="host.organization_name", read_only=True)

    class Meta:
        model = Tournament
        fields = (
            "id",
            "title",
            "game_name",
            "game_mode",
            "host_name",
            "max_participants",
            "current_participants",
            "entry_fee",
            "prize_pool",
            "tournament_start",
            "status",
            "banner_image",
            "is_featured",
        )


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
