import json

from django.conf import settings

from rest_framework import serializers

from accounts.models import PlayerProfile, Team, TeamMember, TeamJoinRequest, User
from accounts.serializers import HostProfileSerializer, PlayerProfileSerializer
from tournaments.models import HostRating, Match, MatchScore, Tournament, TournamentRegistration


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
    placement_points = serializers.JSONField(required=False)
    prize_distribution = serializers.JSONField(required=False)
    
    # 5v5-specific fields
    is_5v5 = serializers.SerializerMethodField()
    requires_password = serializers.SerializerMethodField()

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
        """Validate banner image size (max 5MB) and premium plan requirement"""
        if value and value.size > 5 * 1024 * 1024:  # 5MB
            raise serializers.ValidationError("Banner image size should not exceed 5MB")

        # Check if banner upload is allowed (premium plan only)
        if value:
            plan_type = self.initial_data.get("plan_type", "basic")
            if plan_type != "premium":
                raise serializers.ValidationError(
                    "Custom banner upload is only available for Premium plan. Upgrade to Premium to upload custom banners."  # noqa E501
                )
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

    def validate_placement_points(self, value):
        """Ensure placement_points is a valid JSON/dict"""
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid JSON format for placement_points")

        if not isinstance(value, dict):
            raise serializers.ValidationError("placement_points must be an object/dictionary")

        return value

    def validate_prize_distribution(self, value):
        """Ensure prize_distribution is a valid JSON/dict"""
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid JSON format for prize_distribution")

        if not isinstance(value, dict):
            raise serializers.ValidationError("prize_distribution must be an object/dictionary")

        return value
    
    def get_is_5v5(self, obj):
        """Check if tournament is a 5v5 game format (Valorant/COD)"""
        return obj.is_5v5_game()
    
    def get_requires_password(self, obj):
        """Check if tournament requires match passwords"""
        return obj.requires_password()

    def validate(self, attrs):
        """Root level validation for Tournament"""
        event_mode = attrs.get("event_mode", "TOURNAMENT")

        if event_mode == "SCRIM":
            # Additional Scrim validations
            max_matches = attrs.get("max_matches", 4)
            if max_matches > 4:
                raise serializers.ValidationError({"max_matches": "Scrims support a maximum of 4 matches."})

        return attrs

    def to_representation(self, instance):
        """Custom representation to ensure default banner fallback and proper tournament_file handling"""
        data = super().to_representation(instance)

        # Check if banner_image is null in the model instance
        if not instance.banner_image:
            default_banner_path = instance.get_default_banner_path()
            if settings.USE_S3:
                data["banner_image"] = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/media/{default_banner_path}"
            else:
                request = self.context.get("request")
                if request:
                    data["banner_image"] = request.build_absolute_uri(f"{settings.MEDIA_URL}{default_banner_path}")
                else:
                    data["banner_image"] = f"{settings.MEDIA_URL}{default_banner_path}"

        # Ensure tournament_file is null when not uploaded (no default fallback)
        if not instance.tournament_file:
            data["tournament_file"] = None

        return data


class TournamentListSerializer(serializers.ModelSerializer):
    """Simplified serializer for list views"""

    host_name = serializers.CharField(source="host.user.username", read_only=True)
    host = serializers.SerializerMethodField()
    banner_image = serializers.SerializerMethodField()

    is_featured = serializers.BooleanField(read_only=True)
    is_registered = serializers.SerializerMethodField()

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
            "registration_start",
            "registration_end",
            "tournament_start",
            "status",
            "banner_image",
            "is_featured",
            "is_registered",
            "plan_type",
            "homepage_banner",
            "event_mode",
            "updated_at",
        )

    def get_is_registered(self, obj):
        """Check if current user is registered for this tournament"""
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return False

        if not hasattr(request.user, "player_profile"):
            return False

        # Avoid local import if possible, but TournamentRegistration is needed
        from tournaments.models import TournamentRegistration

        return TournamentRegistration.objects.filter(tournament=obj, player=request.user.player_profile).exists()

    def get_host(self, obj):
        return {"id": obj.host.id, "username": obj.host.user.username}

    def get_banner_image(self, obj):
        """Return custom banner for premium, default banner for basic/featured/premium fallback"""
        # If custom banner exists, return it
        if obj.banner_image:
            if settings.USE_S3:
                # S3 URL
                return obj.banner_image.url
            else:
                # Local URL
                request = self.context.get("request")
                if request:
                    return request.build_absolute_uri(obj.banner_image.url)
                return obj.banner_image.url

        # Fallback to default banner for all plans
        default_banner_path = obj.get_default_banner_path()
        if settings.USE_S3:
            # Construct S3 URL for default banner
            return f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/media/{default_banner_path}"
        else:
            # Local URL for default banner
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(f"{settings.MEDIA_URL}{default_banner_path}")
            return f"{settings.MEDIA_URL}{default_banner_path}"


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
    performance = serializers.SerializerMethodField()

    class Meta:
        model = TournamentRegistration
        fields = "__all__"
        read_only_fields = ("player", "tournament", "registered_at", "updated_at", "team_members", "performance")

    def get_performance(self, obj):
        # Aggregate scores for this registration
        scores = MatchScore.objects.filter(team=obj)
        total_kills = sum(s.kill_points for s in scores)
        total_points = sum(s.total_points for s in scores)

        # Try to find placement
        # If the tournament is completed, we might have final placement in winners JSON
        placement = "N/A"
        tournament = obj.tournament
        if tournament.status == "completed" and tournament.winners:
            # Check each round for winners
            for round_num, winner_id in tournament.winners.items():
                if winner_id == obj.id:
                    placement = f"#{1}"  # Winner of that round (if it's the final round)
                    break

        return {"kills": total_kills, "points": total_points, "placement": placement}

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

            # Determine required team size based on tournament type
            if tournament.is_5v5_game():
                required_players = 5
                mode_name = "5v5"
            else:
                game_mode = tournament.game_mode
                required_players = {"Squad": 4, "Duo": 2, "Solo": 1}.get(game_mode, 1)
                mode_name = game_mode

            if len(player_usernames) != required_players:
                raise serializers.ValidationError(
                    {
                        "player_usernames": f"{mode_name} tournament requires exactly {required_players} player(s). "
                        f"You provided {len(player_usernames)}."
                    }
                )

        return attrs

    def create(self, validated_data):
        """Create registration with team logic"""

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
        # This is only called for free tournaments (no payment required)
        # Paid tournaments are created via webhook after payment success
        registration = TournamentRegistration.objects.create(
            tournament=tournament,
            player=registering_player,
            team=team_instance,
            team_name=team_name,
            team_members=team_members_data,
            payment_status=True,  # Free tournament, mark as paid
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
    profile_picture = serializers.SerializerMethodField()

    def get_profile_picture(self, obj):
        """Get team profile picture URL"""
        try:
            # obj.team is a TournamentRegistration instance
            # obj.team.team is the Team instance
            if obj.team and hasattr(obj.team, "team") and obj.team.team:
                if obj.team.team.profile_picture:
                    return obj.team.team.profile_picture.url
        except Exception:
            # Silently handle errors to avoid breaking serialization
            pass
        return None

    class Meta:
        model = MatchScore
        fields = [
            "id",
            "team_id",
            "team_name",
            "profile_picture",
            "wins",
            "position_points",
            "kill_points",
            "total_points",
        ]
        read_only_fields = ["id", "total_points"]


class MatchSerializer(serializers.ModelSerializer):
    """Serializer for match details"""

    scores = MatchScoreSerializer(many=True, read_only=True)
    can_edit_room = serializers.SerializerMethodField()
    can_edit_scores = serializers.SerializerMethodField()
    can_start = serializers.SerializerMethodField()
    can_end = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    
    # 5v5-specific fields
    winner = serializers.SerializerMethodField()
    team_a = serializers.SerializerMethodField()
    team_b = serializers.SerializerMethodField()
    is_5v5_match = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = [
            "id",
            "match_number",
            "match_id",
            "match_password",
            "status",
            "scheduled_date",
            "scheduled_time",
            "map_name",
            "started_at",
            "ended_at",
            "created_at",
            "scores",
            "can_edit_room",
            "can_edit_scores",
            "can_start",
            "can_end",
            "can_cancel",
            "winner",
            "team_a",
            "team_b",
            "is_5v5_match",
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
    
    def get_winner(self, obj):
        """Return winner team info if match is completed and has a winner"""
        if obj.winner:
            return {
                "id": obj.winner.id,
                "team_name": obj.winner.team_name,
            }
        return None
    
    def get_team_a(self, obj):
        """Get first team in the group (for 5v5 head-to-head matches)"""
        teams = list(obj.group.teams.all()[:1])
        if teams:
            return {
                "id": teams[0].id,
                "team_name": teams[0].team_name,
            }
        return None
    
    def get_team_b(self, obj):
        """Get second team in the group (for 5v5 head-to-head matches)"""
        teams = list(obj.group.teams.all()[1:2])
        if teams:
            return {
                "id": teams[0].id,
                "team_name": teams[0].team_name,
            }
        return None
    
    def get_is_5v5_match(self, obj):
        """Check if this match belongs to a 5v5 tournament (Valorant/COD)"""
        return obj.group.tournament.is_5v5_game()


class TournamentRegistrationInitSerializer(serializers.Serializer):
    """
    Serializer for initiating tournament registration with email invites.
    This is the first step before payment is completed.
    
    POST /api/tournaments/<tournament_id>/register-init/
    
    Expected data:
    {
        "team_name": "Alpha Squad",
        "teammate_emails": ["player2@example.com", "player3@example.com", "player4@example.com"]
    }
    """
    team_name = serializers.CharField(max_length=255, required=True)
    teammate_emails = serializers.ListField(
        child=serializers.EmailField(),
        required=True,
        help_text="List of teammate email addresses (count depends on game mode: 4 for 5v5, 3 for Squad, 1 for Duo)"
    )
    
    def validate_team_name(self, value):
        """Validate team name is not empty and meets minimum length."""
        if not value or len(value.strip()) < 3:
            raise serializers.ValidationError("Team name must be at least 3 characters long.")
        return value.strip()
    
    def validate_teammate_emails(self, value):
        """Validate correct number of teammate emails based on tournament type."""
        # Get tournament from context to determine required team size
        tournament_id = self.context.get('tournament_id')
        
        if tournament_id:
            from tournaments.models import Tournament
            try:
                tournament = Tournament.objects.get(id=tournament_id)
                # Determine required teammates based on game type
                if tournament.is_5v5_game():
                    required_teammates = 4  # Captain + 4 = 5 total
                    mode_name = "5v5"
                else:
                    # For other games (Squad/Duo/Solo)
                    game_mode = tournament.game_mode
                    required_teammates = {"Squad": 3, "Duo": 1, "Solo": 0}.get(game_mode, 3)
                    mode_name = game_mode
                
                if len(value) != required_teammates:
                    raise serializers.ValidationError(
                        f"{mode_name} tournament requires exactly {required_teammates} teammate(s). "
                        f"You provided {len(value)}."
                    )
            except Tournament.DoesNotExist:
                pass  # Will be caught in root validate()
        
        # Normalize emails to lowercase
        normalized_emails = [email.lower() for email in value]
        
        # Check for duplicates
        if len(normalized_emails) != len(set(normalized_emails)):
            raise serializers.ValidationError("Duplicate emails are not allowed in the invite list.")
        
        return normalized_emails
    
    def validate(self, attrs):
        """Root level validation."""
        request = self.context.get('request')
        tournament_id = self.context.get('tournament_id')
        
        if not request or not tournament_id:
            raise serializers.ValidationError("Missing request context or tournament_id.")
        
        # Verify tournament exists
        from tournaments.models import Tournament
        try:
            tournament = Tournament.objects.get(id=tournament_id)
        except Tournament.DoesNotExist:
            raise serializers.ValidationError({"error": "Tournament not found."})
        
        # Check if registration window is open
        from django.utils import timezone
        now = timezone.now()
        if now < tournament.registration_start:
            raise serializers.ValidationError({"error": "Registration has not started yet."})
        if now > tournament.registration_end:
            raise serializers.ValidationError({"error": "Registration has ended."})
        
        # Check if tournament is full
        if tournament.current_participants >= tournament.max_participants:
            raise serializers.ValidationError({"error": "Tournament is full."})
        
        # Check if captain (current user) is already registered
        from accounts.models import PlayerProfile
        player_profile = request.user.player_profile
        existing = TournamentRegistration.objects.filter(
            tournament=tournament,
            player=player_profile
        ).exclude(status="rejected").first()
        
        if existing:
            raise serializers.ValidationError(
                {"error": "You are already registered for this tournament."}
            )
        
        # Verify that captain's email is not in the teammate emails
        captain_email = request.user.email.lower()
        teammate_emails = attrs['teammate_emails']
        if captain_email in teammate_emails:
            raise serializers.ValidationError(
                {"teammate_emails": "Captain's email cannot be in the teammate list."}
            )
        
        # Check that each teammate email is not already invited to this tournament
        for email in teammate_emails:
            existing_invite = TeamJoinRequest.objects.filter(
                invited_email=email.lower(),
                tournament_registration__tournament=tournament,
                status__in=['pending', 'accepted']
            ).exists()
            
            if existing_invite:
                raise serializers.ValidationError(
                    {"teammate_emails": f"{email} is already invited to this tournament."}
                )
        
        return attrs
