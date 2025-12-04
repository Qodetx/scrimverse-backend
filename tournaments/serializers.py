import json

from rest_framework import serializers

from accounts.models import PlayerProfile, User
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
    team_name = serializers.CharField(required=True, max_length=100)
    player_usernames = serializers.ListField(
        child=serializers.CharField(max_length=150),
        write_only=True,
        required=True,
        help_text="List of player usernames for the team (e.g., ['player1', 'player2',...] for Squad)",
    )

    class Meta:
        model = TournamentRegistration
        fields = "__all__"
        read_only_fields = ("player", "tournament", "registered_at", "updated_at", "team_members")

    def validate_player_usernames(self, value):
        """Validate that all usernames exist and are unique"""
        if not value:
            raise serializers.ValidationError("At least one player username is required")

        # Check for duplicates
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate usernames are not allowed")

        # Check that all usernames exist
        usernames_set = set(value)
        existing_users = User.objects.filter(username__in=usernames_set, user_type="player")
        existing_usernames = set(existing_users.values_list("username", flat=True))

        missing_usernames = usernames_set - existing_usernames
        if missing_usernames:
            raise serializers.ValidationError(f"Players not found: {', '.join(missing_usernames)}")

        return value

    def validate(self, attrs):
        """Validate team size matches tournament game mode"""
        tournament_id = attrs.get("tournament_id") or self.context.get("tournament_id")
        player_usernames = attrs.get("player_usernames", [])

        if tournament_id:
            try:
                tournament = Tournament.objects.get(id=tournament_id)
            except Tournament.DoesNotExist:
                raise serializers.ValidationError({"tournament_id": "Tournament not found"})

            # Determine required team size based on game_mode
            game_mode = tournament.game_mode
            required_players = {"Squad": 4, "Duo": 2, "Solo": 1}.get(game_mode, 1)

            if len(player_usernames) != required_players:
                raise serializers.ValidationError(
                    {
                        "player_usernames": f"{game_mode} tournament requires exactly {required_players} player(s). "
                        f"You provided {len(player_usernames)}."
                    }
                )

        return attrs

    def create(self, validated_data):
        """Create registration with team members"""
        player_usernames = validated_data.pop("player_usernames")
        team_name = validated_data.pop("team_name")
        tournament_id = validated_data.pop("tournament_id")
        player_id = validated_data.pop("player_id", None)

        # Get tournament
        tournament = Tournament.objects.get(id=tournament_id)

        # Get registering player (the one making the registration)
        if player_id:
            registering_player = PlayerProfile.objects.get(id=player_id)
        else:
            # Fallback: use first player in the list
            registering_user = User.objects.get(username=player_usernames[0], user_type="player")
            registering_player = registering_user.player_profile

        # Validate that registering player is in the team
        registering_username = registering_player.user.username
        if registering_username not in player_usernames:
            raise serializers.ValidationError(
                {"player_usernames": "The registering player must be included in the team"}
            )

        # Get all player profiles for team members
        team_members_data = []
        for username in player_usernames:
            user = User.objects.get(username=username, user_type="player")
            player_profile = user.player_profile
            team_members_data.append(
                {
                    "id": player_profile.id,
                    "username": username,
                    "in_game_name": player_profile.in_game_name,
                    "email": user.email,
                }
            )

        # Create registration
        registration = TournamentRegistration.objects.create(
            tournament=tournament,
            player=registering_player,
            team_name=team_name,
            team_members=team_members_data,
            **validated_data,
        )

        return registration


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
