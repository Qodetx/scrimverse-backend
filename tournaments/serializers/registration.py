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
            team_instance = Team.objects.create(
                name=team_name,
                captain=registering_player.user,
                is_temporary=True,
                linked_tournament=tournament,
            )

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
            # Always include the registering captain first
            cap_user = registering_player.user
            cap_pp_id = registering_player.id
            team_members_data.append(
                {
                    "username": cap_user.username,
                    "is_registered": True,
                    "player_id": cap_pp_id,
                }
            )
            # Then add any explicitly provided player_usernames (excluding captain to avoid duplicate)
            for username in player_usernames:
                if username == cap_user.username:
                    continue
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
    invite_mode = serializers.ChoiceField(
        choices=['email', 'username', 'phone'],
        required=False,
        default='email',
    )
    teammate_emails = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
        allow_empty=True,
        help_text="List of teammate email addresses."
    )
    teammate_usernames = serializers.ListField(
        child=serializers.CharField(max_length=150),
        required=False,
        allow_empty=True,
        help_text="List of teammate usernames."
    )
    teammate_phones = serializers.ListField(
        child=serializers.CharField(max_length=20),
        required=False,
        allow_empty=True,
        help_text="List of teammate phone numbers."
    )

    def validate_team_name(self, value):
        """Validate team name is not empty and meets minimum length."""
        if not value or len(value.strip()) < 3:
            raise serializers.ValidationError("Team name must be at least 3 characters long.")
        return value.strip()

    def validate_teammate_emails(self, value):
        """Validate teammate emails - allow optional (0 to 5 teammates)."""
        if not value:
            return []
        if len(value) > 5:
            raise serializers.ValidationError(
                f"Maximum 5 teammates allowed. You provided {len(value)}."
            )
        normalized_emails = [email.lower() for email in value]
        if len(normalized_emails) != len(set(normalized_emails)):
            raise serializers.ValidationError("Duplicate emails are not allowed in the invite list.")
        return normalized_emails

    def validate(self, attrs):
        """
        Root-level validation. Each invite mode is kept fully independent:
        - email mode: validates attrs['teammate_emails'], stores email strings
        - phone mode: validates attrs['teammate_phones'], stores phone strings
        - username mode: looks up User objects, stores them in attrs['teammate_users']
        No cross-mode resolution happens here.
        """
        request = self.context.get('request')
        tournament_id = self.context.get('tournament_id')

        if not request or not tournament_id:
            raise serializers.ValidationError("Missing request context or tournament_id.")

        invite_mode = attrs.get('invite_mode', 'email')

        # ----- EMAIL MODE -----
        if invite_mode == 'email':
            emails = attrs.get('teammate_emails', [])
            teammate_count = len(emails)

            if len(emails) > 5:
                raise serializers.ValidationError(
                    {"teammate_emails": f"Maximum 5 teammates allowed. You provided {len(emails)}."}
                )
            if len(emails) != len(set(emails)):
                raise serializers.ValidationError(
                    {"teammate_emails": "Duplicate emails are not allowed."}
                )

            captain_email = request.user.email.lower()
            if captain_email in emails:
                raise serializers.ValidationError(
                    {"teammate_emails": "You cannot add yourself as a teammate."}
                )

            attrs['teammate_emails'] = emails

        # ----- PHONE MODE -----
        elif invite_mode == 'phone':
            phones = attrs.get('teammate_phones', [])
            # Normalise: strip whitespace, allow +91 prefix and reduce to 10 digits
            normalised_phones = []
            for p in phones:
                clean = p.strip().replace(' ', '').lstrip('+')
                if clean.startswith('91') and len(clean) > 10:
                    clean = clean[2:]
                if not clean.isdigit() or len(clean) != 10:
                    raise serializers.ValidationError(
                        {"teammate_phones": f"'{p}' is not a valid 10-digit phone number."}
                    )
                normalised_phones.append(clean)

            teammate_count = len(normalised_phones)

            if teammate_count > 5:
                raise serializers.ValidationError(
                    {"teammate_phones": f"Maximum 5 teammates allowed. You provided {teammate_count}."}
                )
            if len(normalised_phones) != len(set(normalised_phones)):
                raise serializers.ValidationError(
                    {"teammate_phones": "Duplicate phone numbers are not allowed."}
                )

            # Check captain is not inviting themselves
            captain_phone_raw = getattr(request.user, 'phone_number', '') or ''
            captain_phone = captain_phone_raw.strip().lstrip('+')
            if captain_phone.startswith('91') and len(captain_phone) > 10:
                captain_phone = captain_phone[2:]
            if captain_phone and captain_phone in normalised_phones:
                raise serializers.ValidationError(
                    {"teammate_phones": "You cannot add yourself as a teammate."}
                )

            attrs['teammate_phones'] = normalised_phones

        # ----- USERNAME MODE -----
        elif invite_mode == 'username':
            usernames = attrs.get('teammate_usernames', [])

            if len(usernames) > 5:
                raise serializers.ValidationError(
                    {"teammate_usernames": f"Maximum 5 teammates allowed. You provided {len(usernames)}."}
                )

            normalised = [u.strip() for u in usernames]
            if len(normalised) != len(set(u.lower() for u in normalised)):
                raise serializers.ValidationError(
                    {"teammate_usernames": "Duplicate usernames are not allowed."}
                )

            captain_username = request.user.username.lower()
            user_objects = []
            for uname in normalised:
                if uname.lower() == captain_username:
                    raise serializers.ValidationError(
                        {"teammate_usernames": "You cannot add yourself as a teammate."}
                    )
                try:
                    u = User.objects.filter(username__iexact=uname, user_type='player').first()
                    if not u:
                        raise User.DoesNotExist
                    user_objects.append(u)
                except User.DoesNotExist:
                    raise serializers.ValidationError(
                        {"teammate_usernames": f"Player '{uname}' not found."}
                    )

            teammate_count = len(user_objects)
            attrs['teammate_users'] = user_objects

        else:
            teammate_count = 0

        # ----- TOURNAMENT CHECKS (shared) -----
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
        already_in_team = TournamentRegistration.objects.filter(
            tournament=tournament
        ).filter(
            django_models.Q(team__members__user=request.user)
        ).exclude(status="rejected").exists()

        if already_in_team:
            raise serializers.ValidationError(
                {"error": "You are already registered for this tournament via an accepted team invite. You cannot register separately."}
            )

        # VALIDATE MANDATORY TEAMMATES BASED ON GAME MODE
        game_name = tournament.game_name.lower()
        game_mode = tournament.game_mode

        required_teammates = 0
        if game_mode == "5v5" or (game_name in ["valorant", "cod", "call of duty"]):
            required_teammates = 4
        elif game_mode == "Squad" and game_name in ["bgmi", "pubg"]:
            required_teammates = 3

        if required_teammates > 0 and teammate_count < required_teammates:
            if invite_mode == 'phone':
                error_field = "teammate_phones"
            elif invite_mode == 'username':
                error_field = "teammate_usernames"
            else:
                error_field = "teammate_emails"
            raise serializers.ValidationError(
                {
                    error_field: f"This tournament requires {required_teammates} teammate(s) for {game_mode} mode in {tournament.game_name}. You provided {teammate_count}."
                }
            )

        # Check that each email is not already invited (email mode only)
        if invite_mode == 'email':
            for email in attrs.get('teammate_emails', []):
                existing_invite = TeamJoinRequest.objects.filter(
                    invited_email=email.lower(),
                    tournament_registration__tournament=tournament,
                    status__in=['pending', 'accepted']
                ).exists()
                if existing_invite:
                    raise serializers.ValidationError(
                        {"teammate_emails": f"A player with email '{email}' is already invited to this tournament."}
                    )

        # Check that each username invite is not already pending (username mode only)
        if invite_mode == 'username':
            for user_obj in attrs.get('teammate_users', []):
                existing_invite = TeamJoinRequest.objects.filter(
                    player=user_obj,
                    invite_type='username',
                    tournament_registration__tournament=tournament,
                    status__in=['pending', 'accepted']
                ).exists()
                if existing_invite:
                    raise serializers.ValidationError(
                        {"teammate_usernames": f"Player '{user_obj.username}' is already invited to this tournament."}
                    )

        return attrs
