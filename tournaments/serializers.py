import json

from rest_framework import serializers

from accounts.models import PlayerProfile, User
from accounts.serializers import HostProfileSerializer, PlayerProfileSerializer

from .models import HostRating, Match, MatchScore, Scrim, ScrimRegistration, Tournament, TournamentRegistration


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
        read_only_fields = (
            "current_participants",
            "created_at",
            "updated_at",
            "host",
            "plan_price",
            "is_featured",
        )

    def validate_banner_image(self, value):
        """Validate banner image size (max 5MB)"""
        if value and value.size > 5 * 1024 * 1024:  # 5MB
            raise serializers.ValidationError("Banner image size should not exceed 5MB")
        return value

    def validate_max_participants(self, value):
        """Validate max participants based on plan type and event mode"""
        data = self.initial_data
        event_mode = data.get("event_mode", "TOURNAMENT")

        if event_mode == "SCRIM" and value > 25:
            raise serializers.ValidationError("Scrims allow maximum 25 teams.")

        plan_type = data.get("plan_type", "basic")
        if plan_type == "basic" and value > 100:
            raise serializers.ValidationError(
                "Basic plan allows maximum 100 teams. Upgrade to Featured or Premium plan for unlimited teams."
            )
        return value

    def validate_rounds(self, value):
        """Validate rounds structure"""
        event_mode = self.initial_data.get("event_mode", "TOURNAMENT")

        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid JSON format for rounds")

        if event_mode == "SCRIM":
            # For Scrims, we force 1 round
            max_teams = self.initial_data.get("max_participants")
            if not max_teams and self.instance:
                max_teams = self.instance.max_participants

            return [{"round": 1, "max_teams": int(max_teams) if max_teams else 25, "qualifying_teams": 0}]

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

    def validate(self, attrs):
        """Root level validation for Tournament"""
        event_mode = attrs.get("event_mode", "TOURNAMENT")

        if event_mode == "SCRIM":
            # Additional Scrim validations
            max_matches = attrs.get("max_matches", 4)
            if max_matches > 4:
                raise serializers.ValidationError({"max_matches": "Scrims support a maximum of 4 matches."})

            # Scrims must have entry_fee >= 0 and basic plan
            attrs["plan_type"] = "basic"

        return attrs


class TournamentListSerializer(serializers.ModelSerializer):
    """Simplified serializer for list views"""

    host_name = serializers.CharField(source="host.user.username", read_only=True)
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
            "plan_type",
            "homepage_banner",
            "event_mode",
        )

    def get_host(self, obj):
        return {"id": obj.host.id, "username": obj.host.user.username}


class ScrimSerializer(serializers.ModelSerializer):
    host = HostProfileSerializer(read_only=True)
    host_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = Scrim
        fields = "__all__"
        read_only_fields = ("current_participants", "created_at", "updated_at")


class ScrimListSerializer(serializers.ModelSerializer):
    """Simplified serializer for list views"""

    host_name = serializers.CharField(source="host.user.username", read_only=True)

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
    team_name = serializers.CharField(required=False, max_length=100)
    player_usernames = serializers.ListField(
        child=serializers.CharField(max_length=150),
        write_only=True,
        required=False,
        help_text="List of player usernames for the team",
    )
    team_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    save_as_team = serializers.BooleanField(write_only=True, default=False)

    class Meta:
        model = TournamentRegistration
        fields = "__all__"
        read_only_fields = ("player", "tournament", "registered_at", "updated_at", "team_members")

    def validate_player_usernames(self, value):
        # Check for duplicates
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate usernames are not allowed")

        # We will check if they are users later or just store as strings
        # to allow unregistered players as well if needed.
        return value

    def validate(self, attrs):
        """Validate team size matches tournament game mode"""
        tournament_id = attrs.get("tournament_id") or self.context.get("tournament_id")
        player_usernames = attrs.get("player_usernames", [])
        team_id = attrs.get("team_id")

        # Skip validation if using existing team
        if team_id:
            return attrs

        # Validate player_usernames only when creating new team
        if tournament_id and player_usernames:
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
        """Create registration with team logic"""
        from accounts.models import Team, TeamMember

        player_usernames = validated_data.pop("player_usernames", [])
        team_name = validated_data.pop("team_name", None)
        tournament_id = validated_data.pop("tournament_id")
        player_id = validated_data.pop("player_id", None)
        team_id = validated_data.pop("team_id", None)
        save_as_team = validated_data.pop("save_as_team", False)

        tournament = Tournament.objects.get(id=tournament_id)

        # Get registering player
        if player_id:
            registering_player = PlayerProfile.objects.get(id=player_id)
        else:
            # Fallback for API calls if player_id is not provided
            registering_player = self.context["request"].user.player_profile

        # Check for duplicate registration
        if TournamentRegistration.objects.filter(tournament=tournament, player=registering_player).exists():
            raise serializers.ValidationError({"detail": "You have already registered for this tournament."})

        # Get team instance if using an existing one
        team_instance = None
        if team_id:
            try:
                team_instance = Team.objects.get(id=team_id)
                # Get team name from existing team if not provided
                if not team_name:
                    team_name = team_instance.name
            except Team.DoesNotExist:
                raise serializers.ValidationError({"team_id": "Team not found"})

        # If they want to save as a team and it's not already an existing team
        if save_as_team and not team_instance:
            # Validate that none of the players are already in a permanent team
            for username in player_usernames:
                user_obj = User.objects.filter(username=username, user_type="player").first()
                if user_obj:
                    existing_permanent_membership = TeamMember.objects.filter(
                        user=user_obj, team__is_temporary=False
                    ).exists()
                    if existing_permanent_membership:
                        raise serializers.ValidationError(
                            {
                                "player_usernames": f"Player {username} is already in a permanent team. "
                                "All players must be available to create a permanent team."
                            }
                        )

            # Create permanent team
            team_instance = Team.objects.create(name=team_name, captain=registering_player.user)
            for username in player_usernames:
                user_obj = User.objects.filter(username=username, user_type="player").first()
                is_cap = username == registering_player.user.username
                TeamMember.objects.create(team=team_instance, username=username, user=user_obj, is_captain=is_cap)

        # If it's a one-time team (not saved), we create a temporary team entry
        # for organizational purposes, or just rely on the strings in registration.
        # Flow says: "if not : it should exist only for that tournament... should be treated as temporary"
        if not team_instance:
            team_instance = Team.objects.create(name=team_name, captain=registering_player.user, is_temporary=True)

        # Prepare team members data for registration record (snapshot)
        team_members_data = []

        # If using existing team, get members from the team
        if team_id:
            for member in team_instance.members.all():
                team_members_data.append(
                    {
                        "username": member.username,
                        "is_registered": member.user is not None,
                        "player_id": member.user.player_profile.id
                        if member.user and hasattr(member.user, "player_profile")
                        else None,
                    }
                )
        else:
            # Otherwise, use player_usernames
            for username in player_usernames:
                user_obj = User.objects.filter(username=username, user_type="player").first()
                team_members_data.append(
                    {
                        "username": username,
                        "is_registered": user_obj is not None,
                        "player_id": user_obj.player_profile.id
                        if user_obj and hasattr(user_obj, "player_profile")
                        else None,
                    }
                )

        # Create registration
        registration = TournamentRegistration.objects.create(
            tournament=tournament,
            player=registering_player,
            team=team_instance,
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
    team_name = serializers.CharField(required=True, max_length=100)
    player_usernames = serializers.ListField(
        child=serializers.CharField(max_length=150), write_only=True, required=True
    )
    team_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    save_as_team = serializers.BooleanField(write_only=True, default=False)

    class Meta:
        model = ScrimRegistration
        fields = "__all__"
        read_only_fields = ("player", "scrim", "registered_at", "updated_at", "team_members")

    def create(self, validated_data):
        from accounts.models import Team, TeamMember

        player_usernames = validated_data.pop("player_usernames")
        team_name = validated_data.pop("team_name")
        save_as_team = validated_data.pop("save_as_team", False)
        team_id = validated_data.pop("team_id", None)

        # Extract scrim and player from validated_data (may be IDs or objects)
        scrim = validated_data.pop("scrim", None)
        scrim_id = validated_data.pop("scrim_id", None)
        if not scrim and scrim_id:
            scrim = Scrim.objects.get(id=scrim_id)

        player = validated_data.pop("player", None)
        player_id = validated_data.pop("player_id", None)
        if not player:
            if player_id:
                player = PlayerProfile.objects.get(id=player_id)
            else:
                player = self.context["request"].user.player_profile

        team_instance = None
        if team_id:
            try:
                team_instance = Team.objects.get(id=team_id)
            except Team.DoesNotExist:
                raise serializers.ValidationError({"team_id": "Team not found"})

        if save_as_team and not team_instance:
            team_instance = Team.objects.create(name=team_name, captain=player.user)
            for username in player_usernames:
                user_obj = User.objects.filter(username=username, user_type="player").first()
                TeamMember.objects.create(
                    team=team_instance, username=username, user=user_obj, is_captain=(username == player.user.username)
                )

        if not team_instance:
            team_instance = Team.objects.create(name=team_name, captain=player.user, is_temporary=True)

        team_members_data = []
        for username in player_usernames:
            user_obj = User.objects.filter(username=username, user_type="player").first()
            team_members_data.append(
                {
                    "username": username,
                    "is_registered": user_obj is not None,
                    "player_id": user_obj.player_profile.id
                    if user_obj and hasattr(user_obj, "player_profile")
                    else None,
                }
            )

        registration = ScrimRegistration.objects.create(
            scrim=scrim,
            player=player,
            team=team_instance,
            team_name=team_name,
            team_members=team_members_data,
            **validated_data,
        )

        return registration


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


class MatchScoreSerializer(serializers.ModelSerializer):
    """Serializer for match scores"""

    team_name = serializers.CharField(source="team.team_name", read_only=True)
    team_id = serializers.IntegerField(source="team.id", read_only=True)

    class Meta:
        model = MatchScore
        fields = ["id", "team_id", "team_name", "wins", "position_points", "kill_points", "total_points"]
        read_only_fields = ["id", "total_points"]


class MatchSerializer(serializers.ModelSerializer):
    """Serializer for match details"""

    scores = MatchScoreSerializer(many=True, read_only=True)
    can_edit_room = serializers.SerializerMethodField()
    can_edit_scores = serializers.SerializerMethodField()
    can_start = serializers.SerializerMethodField()
    can_end = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = [
            "id",
            "match_number",
            "match_id",
            "match_password",
            "status",
            "started_at",
            "ended_at",
            "created_at",
            "scores",
            "can_edit_room",
            "can_edit_scores",
            "can_start",
            "can_end",
            "can_cancel",
        ]
        read_only_fields = ["id", "status", "started_at", "ended_at", "created_at"]

    def get_can_edit_room(self, obj):
        return obj.can_edit_room_details()

    def get_can_edit_scores(self, obj):
        return obj.can_edit_scores()

    def get_can_start(self, obj):
        can_start, _ = obj.can_start_match()
        return can_start

    def get_can_end(self, obj):
        can_end, _ = obj.can_end_match()
        return can_end

    def get_can_cancel(self, obj):
        can_cancel, _ = obj.can_cancel_match()
        return can_cancel
