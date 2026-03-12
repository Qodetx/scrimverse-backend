"""
Tournament registration and host rating serializers.
"""
from django.db import models as django_models
from django.utils import timezone

from rest_framework import serializers

from accounts.models import PlayerProfile, Team, TeamJoinRequest, TeamMember, User
from accounts.serializers import PlayerProfileSerializer
from tournaments.models import HostRating, Match, MatchScore, Tournament, TournamentRegistration
from tournaments.serializers.tournament import TournamentListSerializer


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
        required=False,
        allow_empty=True,
        help_text="List of teammate email addresses. For 5v5 games (Valorant/COD): 4 emails required. For Squad BGMI: 3 emails required."
    )

    def validate_team_name(self, value):
        """Validate team name is not empty and meets minimum length."""
        if not value or len(value.strip()) < 3:
            raise serializers.ValidationError("Team name must be at least 3 characters long.")
        return value.strip()

    def validate_teammate_emails(self, value):
        """Validate teammate emails - allow optional (0 to 5 teammates)."""
        # Allow empty list - users can register as captain only
        if not value:
            return []

        # Validate that we don't have more than 5 teammates (6 total including captain)
        if len(value) > 5:
            raise serializers.ValidationError(
                f"Maximum 5 teammates allowed. You provided {len(value)}."
            )

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
        now = timezone.now()
        if now < tournament.registration_start:
            raise serializers.ValidationError({"error": "Registration has not started yet."})
        if now > tournament.registration_end:
            raise serializers.ValidationError({"error": "Registration has ended."})

        # Check if tournament is full
        if tournament.current_participants >= tournament.max_participants:
            raise serializers.ValidationError({"error": "Tournament is full."})

        # Check if captain (current user) is already registered
        player_profile = request.user.player_profile
        existing = TournamentRegistration.objects.filter(
            tournament=tournament,
            player=player_profile
        ).exclude(status="rejected").first()

        if existing:
            raise serializers.ValidationError(
                {"error": "You are already registered for this tournament."}
            )

        # Also check if user is already a member of any team in this tournament
        # (they may have accepted an invite for a team in this tournament)
        already_in_team = TournamentRegistration.objects.filter(
            tournament=tournament
        ).filter(
            django_models.Q(team__members__user=request.user)
        ).exclude(status="rejected").exists()

        if already_in_team:
            raise serializers.ValidationError(
                {"error": "You are already registered for this tournament via an accepted team invite. You cannot register separately."}
            )

        # Verify that captain's email is not in the teammate emails
        captain_email = request.user.email.lower()
        teammate_emails = attrs['teammate_emails']
        if captain_email in teammate_emails:
            raise serializers.ValidationError(
                {"teammate_emails": "Captain's email cannot be in the teammate list."}
            )

        # VALIDATE MANDATORY TEAMMATE EMAILS BASED ON GAME MODE
        # For 5v5 games (Valorant, COD) - Need exactly 4 teammates (5 total including captain)
        # For Squad mode games (BGMI) - Need exactly 3 teammates (4 total including captain)
        game_name = tournament.game_name.lower()
        game_mode = tournament.game_mode

        required_teammates = 0
        if game_mode == "5v5" or (game_name in ["valorant", "cod", "call of duty"]):
            required_teammates = 4  # 5v5 needs 4 teammates + captain
        elif game_mode == "Squad" and game_name in ["bgmi", "pubg"]:
            required_teammates = 3  # Squad BGMI needs 3 teammates + captain (4 total)

        if required_teammates > 0 and len(teammate_emails) < required_teammates:
            raise serializers.ValidationError(
                {
                    "teammate_emails": f"This tournament requires {required_teammates} teammate email(s) for {game_mode} mode in {tournament.game_name}. You provided {len(teammate_emails)}."
                }
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
