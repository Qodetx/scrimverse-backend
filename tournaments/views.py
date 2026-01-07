import logging

from django.core.cache import cache
from django.db.models import Sum
from django.utils import timezone

from rest_framework import generics, parsers, permissions
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import HostProfile, PlayerProfile, User

from .models import HostRating, RoundScore, Scrim, ScrimRegistration, Tournament, TournamentRegistration
from .serializers import (
    HostRatingSerializer,
    ScrimListSerializer,
    ScrimRegistrationSerializer,
    ScrimSerializer,
    TournamentListSerializer,
    TournamentRegistrationSerializer,
    TournamentSerializer,
)

logger = logging.getLogger(__name__)


class IsHostUser(permissions.BasePermission):
    """Permission class for Host users"""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == "host"


class IsPlayerUser(permissions.BasePermission):
    """Permission class for Player users"""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == "player"


# ============= Tournament Views =============


class TournamentListView(generics.ListAPIView):
    """
    List all tournaments with Redis cache (Guest/Player/Host can access)
    GET /api/tournaments/
    Cache: Only when no filters applied
    """

    queryset = Tournament.objects.all()
    serializer_class = TournamentListSerializer
    permission_classes = [permissions.AllowAny]

    def list(self, request, *args, **kwargs):
        now = timezone.now()

        Tournament.objects.filter(tournament_start__lte=now, tournament_end__gt=now, status="upcoming").update(
            status="ongoing"
        )

        Tournament.objects.filter(tournament_end__lte=now, status__in=["upcoming", "ongoing"]).update(
            status="completed"
        )

        status_param = request.query_params.get("status")
        game_param = request.query_params.get("game")
        category_param = request.query_params.get("category")
        event_mode_param = request.query_params.get("event_mode")

        if not status_param and not game_param and not category_param and not event_mode_param:
            cache_key = "tournaments:list:all"
            cached_data = cache.get(cache_key)

            if cached_data:
                return Response(cached_data)

            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            cache.set(cache_key, serializer.data, timeout=300)  # 5 minutes
            return Response(serializer.data)

        # Don't cache filtered results
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Tournament.objects.all()
        status_param = self.request.query_params.get("status", None)
        game = self.request.query_params.get("game", None)
        category = self.request.query_params.get("category", None)
        event_mode = self.request.query_params.get("event_mode", None)

        if status_param:
            queryset = queryset.filter(status=status_param)
        if game:
            queryset = queryset.filter(game_name__icontains=game)
        if event_mode:
            queryset = queryset.filter(event_mode=event_mode)

        # Filter by category based on plan type
        if category == "all":
            queryset = queryset.filter(plan_type="basic")
        elif category == "official":
            queryset = queryset.filter(plan_type__in=["featured", "premium"])

        return queryset


class TournamentDetailView(generics.RetrieveAPIView):
    """
    Get tournament details
    GET /api/tournaments/<id>/
    Includes user_registration_status for authenticated players
    """

    queryset = Tournament.objects.all()
    serializer_class = TournamentSerializer
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)

        # Add user registration status if user is a player
        if request.user.is_authenticated and request.user.user_type == "player":
            try:
                player_profile = PlayerProfile.objects.get(user=request.user)
                tournament_id = kwargs.get("pk")

                # Check if player has a registration
                registration = TournamentRegistration.objects.filter(
                    tournament_id=tournament_id, player=player_profile
                ).first()

                if registration:
                    response.data["user_registration_status"] = registration.status
                else:
                    response.data["user_registration_status"] = None
            except PlayerProfile.DoesNotExist:
                response.data["user_registration_status"] = None
        else:
            response.data["user_registration_status"] = None

        return response


class TournamentCreateView(generics.CreateAPIView):
    """
    Host creates a tournament
    POST /api/tournaments/create/
    Invalidates cache on creation
    """

    serializer_class = TournamentSerializer
    permission_classes = [IsHostUser]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)

    def create(self, request, *args, **kwargs):
        """Override create to handle file uploads properly"""
        # Clean empty file fields (FormData sends empty strings for missing files)
        data = request.data.copy()

        # Remove empty file fields to prevent validation errors
        for file_field in ["banner_image", "tournament_file"]:
            if file_field in data:
                value = data[file_field]
                # Remove if it's an empty string or has no size
                if value == "" or value == "null" or (isinstance(value, str) and not value):
                    data.pop(file_field)
                elif hasattr(value, "size") and value.size == 0:
                    data.pop(file_field)

        # Debug logging
        print(f"[DEBUG] Received rounds data: {data.get('rounds')}")
        print(f"[DEBUG] Received event_mode: {data.get('event_mode')}")

        serializer = self.get_serializer(data=data)
        if not serializer.is_valid():
            print(f"[DEBUG] Serializer validation errors: {serializer.errors}")
            return Response(serializer.errors, status=400)

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=201, headers=headers)

    def perform_create(self, serializer):
        host_profile = HostProfile.objects.get(user=self.request.user)
        serializer.save(host=host_profile)
        # Invalidate tournament list cache
        cache.delete("tournaments:list:all")


class TournamentUpdateView(generics.UpdateAPIView):
    """
    Host updates their tournament
    PUT/PATCH /api/tournaments/<id>/update/
    Invalidates cache on update
    """

    queryset = Tournament.objects.all()
    serializer_class = TournamentSerializer
    permission_classes = [IsHostUser]

    def get_queryset(self):
        # Host can only update their own tournaments
        host_profile = HostProfile.objects.get(user=self.request.user)
        return Tournament.objects.filter(host=host_profile)

    def perform_update(self, serializer):
        serializer.save()
        # Invalidate cache
        cache.delete("tournaments:list:all")


class TournamentDeleteView(generics.DestroyAPIView):
    """
    Host deletes their tournament
    DELETE /api/tournaments/<id>/delete/
    Invalidates cache on deletion
    """

    queryset = Tournament.objects.all()
    permission_classes = [IsHostUser]

    def get_queryset(self):
        host_profile = HostProfile.objects.get(user=self.request.user)
        return Tournament.objects.filter(host=host_profile)

    def perform_destroy(self, instance):
        instance.delete()
        # Invalidate cache
        cache.delete("tournaments:list:all")


class HostTournamentsView(generics.ListAPIView):
    """
    Get all tournaments by a specific host
    GET /api/tournaments/host/<host_id>/
    """

    serializer_class = TournamentListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        host_id = self.kwargs["host_id"]
        return Tournament.objects.filter(host_id=host_id)


# ============= Scrim Views =============


class ScrimListView(generics.ListAPIView):
    """
    List all scrims
    GET /api/tournaments/scrims/
    """

    queryset = Scrim.objects.all()
    serializer_class = ScrimListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = Scrim.objects.all()
        status_param = self.request.query_params.get("status", None)
        game = self.request.query_params.get("game", None)

        if status_param:
            queryset = queryset.filter(status=status_param)
        if game:
            queryset = queryset.filter(game_name__icontains=game)

        return queryset


class ScrimDetailView(generics.RetrieveAPIView):
    """
    Get scrim details
    GET /api/tournaments/scrims/<id>/
    """

    queryset = Scrim.objects.all()
    serializer_class = ScrimSerializer
    permission_classes = [permissions.AllowAny]


class ScrimCreateView(generics.CreateAPIView):
    """
    Host creates a scrim
    POST /api/tournaments/scrims/create/
    """

    serializer_class = ScrimSerializer
    permission_classes = [IsHostUser]

    def perform_create(self, serializer):
        host_profile = HostProfile.objects.get(user=self.request.user)
        serializer.save(host=host_profile)


class ScrimUpdateView(generics.UpdateAPIView):
    """
    Host updates their scrim
    PUT/PATCH /api/tournaments/scrims/<id>/update/
    """

    queryset = Scrim.objects.all()
    serializer_class = ScrimSerializer
    permission_classes = [IsHostUser]

    def get_queryset(self):
        host_profile = HostProfile.objects.get(user=self.request.user)
        return Scrim.objects.filter(host=host_profile)


class ScrimDeleteView(generics.DestroyAPIView):
    """
    Host deletes their scrim
    DELETE /api/tournaments/scrims/<id>/delete/
    """

    queryset = Scrim.objects.all()
    permission_classes = [IsHostUser]

    def get_queryset(self):
        host_profile = HostProfile.objects.get(user=self.request.user)
        return Scrim.objects.filter(host=host_profile)


# ============= Registration Views =============


class TournamentRegistrationCreateView(generics.CreateAPIView):
    """
    Player registers for a tournament as a team
    POST /api/tournaments/<tournament_id>/register/
    Body: {
        "team_name": "Team Name",
        "player_usernames": ["player1", "player2", "player3", "player4"],
        "in_game_details": {"ign": "", "uid": "", "rank": ""}
    }
    Invalidates cache when participant count changes
    """

    serializer_class = TournamentRegistrationSerializer
    permission_classes = [IsPlayerUser]

    def get_serializer_context(self):
        """Add tournament_id to serializer context"""
        context = super().get_serializer_context()
        context["tournament_id"] = self.kwargs["tournament_id"]
        return context

    def perform_create(self, serializer):
        player_profile = PlayerProfile.objects.get(user=self.request.user)
        tournament_id = self.kwargs["tournament_id"]
        tournament = Tournament.objects.get(id=tournament_id)

        # Check registration window
        now = timezone.now()
        if now < tournament.registration_start:
            raise ValidationError({"error": "Registration has not started yet"})
        if now > tournament.registration_end:
            raise ValidationError({"error": "Registration has ended"})

        # Check if player has a rejected registration
        rejected_registration = TournamentRegistration.objects.filter(
            tournament=tournament, player=player_profile, status="rejected"
        ).first()

        if rejected_registration:
            raise ValidationError(
                {
                    "error": "You cannot re-register for this tournament. Your previous registration was rejected by the host."  # noqa
                }
            )

        # Check if tournament is full
        if tournament.current_participants >= tournament.max_participants:
            raise ValidationError({"error": "Tournament is full"})

        # Get player_usernames from validated data
        player_usernames = serializer.validated_data.get("player_usernames", [])
        team_id = serializer.validated_data.get("team_id")

        # Validate that the current user is in the team (only when not using existing team_id)
        if not team_id:
            current_username = self.request.user.username
            if current_username not in player_usernames:
                raise ValidationError({"player_usernames": "You must include your own username in the team"})

        # Check if any team member is already registered (check by player profile IDs)
        # Get all player profiles for the team
        team_users = User.objects.filter(username__in=player_usernames, user_type="player").select_related(
            "player_profile"
        )
        team_player_ids = {user.player_profile.id for user in team_users if hasattr(user, "player_profile")}

        # Check existing registrations
        existing_registrations = TournamentRegistration.objects.filter(tournament=tournament)
        for registration in existing_registrations:
            if registration.team_members:
                registered_player_ids = {member.get("id") for member in registration.team_members if member.get("id")}
                # Check if any overlap
                overlapping_ids = team_player_ids & registered_player_ids
                if overlapping_ids:
                    # Find usernames of overlapping players
                    registered_usernames = [
                        member.get("username")
                        for member in registration.team_members
                        if member.get("id") in overlapping_ids
                    ]
                    raise ValidationError(
                        {
                            "player_usernames": f"One or more players are already registered for this tournament: "
                            f"{', '.join(registered_usernames)}"
                        }
                    )

        # Save registration (serializer will handle team_members creation)
        serializer.save(player_id=player_profile.id, tournament_id=tournament_id)

        # Update participant count (count teams, not individual players)
        tournament.current_participants += 1
        tournament.save()

        # Invalidate cache since participant count changed
        cache.delete("tournaments:list:all")


class ScrimRegistrationCreateView(generics.CreateAPIView):
    """
    Player registers for a scrim
    POST /api/tournaments/scrims/<scrim_id>/register/
    """

    serializer_class = ScrimRegistrationSerializer
    permission_classes = [IsPlayerUser]

    def perform_create(self, serializer):
        player_profile = PlayerProfile.objects.get(user=self.request.user)
        scrim_id = self.kwargs["scrim_id"]
        scrim = Scrim.objects.get(id=scrim_id)

        # Check if already registered
        if ScrimRegistration.objects.filter(scrim=scrim, player=player_profile).exists():
            raise ValidationError({"error": "Already registered for this scrim"})

        serializer.save(player=player_profile, scrim=scrim)

        # Update participant count
        scrim.current_participants += 1
        scrim.save()


class PlayerTournamentRegistrationsView(generics.ListAPIView):
    """
    Get all tournament registrations of a player
    GET /api/tournaments/my-registrations/
    """

    serializer_class = TournamentRegistrationSerializer
    permission_classes = [IsPlayerUser]

    def get_queryset(self):
        player_profile = PlayerProfile.objects.get(user=self.request.user)
        return TournamentRegistration.objects.filter(player=player_profile)


class PlayerScrimRegistrationsView(generics.ListAPIView):
    """
    Get all scrim registrations of a player
    GET /api/tournaments/scrims/my-registrations/
    """

    serializer_class = ScrimRegistrationSerializer
    permission_classes = [IsPlayerUser]

    def get_queryset(self):
        player_profile = PlayerProfile.objects.get(user=self.request.user)
        return ScrimRegistration.objects.filter(player=player_profile)


# ============= Host Rating Views =============


class HostRatingCreateView(generics.CreateAPIView):
    """
    Player rates a host
    POST /api/tournaments/host/<host_id>/rate/
    """

    serializer_class = HostRatingSerializer
    permission_classes = [IsPlayerUser]

    def perform_create(self, serializer):
        player_profile = PlayerProfile.objects.get(user=self.request.user)
        host_id = self.kwargs["host_id"]
        host_profile = HostProfile.objects.get(id=host_id)

        serializer.save(player=player_profile, host=host_profile)


class HostRatingsListView(generics.ListAPIView):
    """
    Get all ratings for a host
    GET /api/tournaments/host/<host_id>/ratings/
    """

    serializer_class = HostRatingSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        host_id = self.kwargs["host_id"]
        return HostRating.objects.filter(host_id=host_id)


# ============= Tournament Management Views =============


class ManageTournamentView(generics.RetrieveAPIView):
    """
    Get tournament management data (host only)
    GET /api/tournaments/<pk>/manage/
    Returns tournament with all registrations
    """

    serializer_class = TournamentSerializer
    permission_classes = [IsHostUser]

    def get_queryset(self):
        host_profile = HostProfile.objects.get(user=self.request.user)
        return Tournament.objects.filter(host=host_profile)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)

        # Get all registrations for this tournament
        registrations = TournamentRegistration.objects.filter(tournament=instance)
        registration_serializer = TournamentRegistrationSerializer(registrations, many=True)

        return Response(
            {
                "tournament": serializer.data,
                "registrations": registration_serializer.data,
            }
        )


class TournamentRegistrationsView(generics.ListAPIView):
    """
    Get all registrations for a tournament (host only)
    GET /api/tournaments/<tournament_id>/registrations/
    """

    serializer_class = TournamentRegistrationSerializer
    permission_classes = [IsHostUser]

    def get_queryset(self):
        tournament_id = self.kwargs["tournament_id"]
        host_profile = HostProfile.objects.get(user=self.request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)
        return TournamentRegistration.objects.filter(tournament=tournament)


class StartRoundView(generics.GenericAPIView):
    """
    Start a specific round
    POST /api/tournaments/<tournament_id>/start-round/<round_number>/
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id, round_number):
        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        # Validate round number
        if round_number < 1 or round_number > len(tournament.rounds):
            return Response(
                {"error": f"Invalid round number. Tournament has {len(tournament.rounds)} rounds."}, status=400
            )

        # Check if previous round is completed (if not first round)
        if round_number > 1:
            prev_round_status = tournament.round_status.get(str(round_number - 1))
            if prev_round_status != "completed":
                return Response(
                    {"error": f"Round {round_number - 1} must be completed before starting round {round_number}"},
                    status=400,
                )

        # Initialize round_status if needed
        if not tournament.round_status:
            tournament.round_status = {}

        # Set current round and status
        tournament.current_round = round_number
        tournament.round_status[str(round_number)] = "ongoing"

        # Initialize selected_teams for this round if not exists
        if not tournament.selected_teams:
            tournament.selected_teams = {}
        if str(round_number) not in tournament.selected_teams:
            tournament.selected_teams[str(round_number)] = []

        tournament.save(update_fields=["current_round", "round_status", "selected_teams"])
        cache.delete("tournaments:list:all")

        return Response(
            {
                "message": f"Round {round_number} started",
                "current_round": tournament.current_round,
                "round_status": tournament.round_status,
            }
        )


class SubmitRoundScoresView(generics.GenericAPIView):
    """
    Host submits scores for teams in a round.
    POST /api/tournaments/<tournament_id>/submit-scores/
    Body: [
      {"team_id": 12, "position_points": 10, "kill_points": 8},
      {"team_id": 13, "position_points": 5, "kill_points": 12}
    ]
    Automatically selects top qualifying teams.
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id):
        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)
        round_num = tournament.current_round

        if round_num == 0:
            return Response({"error": "No active round"}, status=400)

        scores_data = request.data
        if not isinstance(scores_data, list):
            return Response({"error": "Invalid data format"}, status=400)

        # Save scores
        for entry in scores_data:
            team_id = entry.get("team_id")
            position_points = int(entry.get("position_points", 0))
            kill_points = int(entry.get("kill_points", 0))
            team = TournamentRegistration.objects.get(id=team_id, tournament=tournament)
            RoundScore.objects.update_or_create(
                tournament=tournament,
                round_number=round_num,
                team=team,
                defaults={"position_points": position_points, "kill_points": kill_points},
            )

        # Auto select top N teams
        round_config = next((r for r in tournament.rounds if r["round"] == round_num), None)
        qualifying_teams = int(round_config.get("qualifying_teams") or 0)
        all_scores = RoundScore.objects.filter(tournament=tournament, round_number=round_num).order_by("-total_points")

        selected_team_ids = list(all_scores.values_list("team_id", flat=True)[:qualifying_teams])
        if not tournament.selected_teams:
            tournament.selected_teams = {}
        tournament.selected_teams[str(round_num)] = selected_team_ids
        tournament.save(update_fields=["selected_teams"])

        return Response(
            {
                "message": f"Scores submitted successfully. Top {qualifying_teams} teams auto-selected.",
                "selected_teams": selected_team_ids,
            }
        )


class SelectTeamsView(generics.GenericAPIView):
    """
    Select/eliminate teams for current round
    POST /api/tournaments/<tournament_id>/select-teams/
    Body: {"team_ids": [1, 2, 3], "action": "select"} or {"action": "eliminate"}
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id):
        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        if tournament.current_round == 0:
            return Response({"error": "No round is currently active"}, status=400)

        action = request.data.get("action")  # "select" or "eliminate"
        team_ids = request.data.get("team_ids", [])

        if action not in ["select", "eliminate"]:
            return Response({"error": "Action must be 'select' or 'eliminate'"}, status=400)

        round_num = str(tournament.current_round)
        round_config = next((r for r in tournament.rounds if r["round"] == tournament.current_round), None)

        if not round_config:
            return Response({"error": "Round configuration not found"}, status=400)

        # Get current selected teams for this round
        if not tournament.selected_teams:
            tournament.selected_teams = {}
        if round_num not in tournament.selected_teams:
            tournament.selected_teams[round_num] = []

        current_selected = tournament.selected_teams[round_num]

        if action == "select":
            # Get selection limit: use qualifying_teams if set, otherwise max_teams
            qualifying_teams = round_config.get("qualifying_teams")
            max_teams = round_config.get("max_teams")

            # Determine selection limit
            if qualifying_teams and int(qualifying_teams) > 0:
                selection_limit = int(qualifying_teams)
            elif max_teams:
                selection_limit = int(max_teams)
            else:
                return Response({"error": "Team selection limit not set for this round"}, status=400)

            # Validate team IDs exist (allow pending and confirmed)
            registrations = TournamentRegistration.objects.filter(
                id__in=team_ids, tournament=tournament, status__in=["pending", "confirmed"]
            )
            valid_ids = list(registrations.values_list("id", flat=True))

            # Frontend sends the complete selection, so we replace the current selection
            # Check if the total number of teams doesn't exceed the limit
            if len(valid_ids) > selection_limit:
                return Response(
                    {"error": f"Cannot select more than {selection_limit} teams. " f"You selected: {len(valid_ids)}"},
                    status=400,
                )

            # Save the complete selection (replace existing)
            tournament.selected_teams[round_num] = valid_ids

        elif action == "eliminate":
            # Remove teams
            tournament.selected_teams[round_num] = [tid for tid in current_selected if tid not in team_ids]

        tournament.save(update_fields=["selected_teams"])
        cache.delete("tournaments:list:all")

        return Response(
            {
                "message": f"Teams {action}ed successfully",
                "selected_teams": tournament.selected_teams[round_num],
                "selected_count": len(tournament.selected_teams[round_num]),
            }
        )


class EndRoundView(generics.GenericAPIView):
    """
    End current round and move to next
    POST /api/tournaments/<tournament_id>/end-round/
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id):
        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        if tournament.current_round == 0:
            return Response({"error": "No round is currently active"}, status=400)

        round_num = tournament.current_round
        round_config = next((r for r in tournament.rounds if r["round"] == round_num), None)

        if not round_config:
            return Response({"error": "Round configuration not found"}, status=400)

        # For ending round: check if it's final round (no qualifying_teams) or regular round
        qualifying_teams = round_config.get("qualifying_teams")
        max_teams = int(round_config.get("max_teams") or 0)
        is_final_round = not qualifying_teams or int(qualifying_teams) == 0

        selected_count = len(tournament.selected_teams.get(str(round_num), []))

        # Final round: must have winner selected, not just teams
        if is_final_round:
            round_key = str(round_num)
            winner = tournament.winners.get(round_key) if tournament.winners else None
            if not winner:
                return Response({"error": "Final round requires a winner to be selected before ending"}, status=400)
        else:
            # Regular round: must select exactly qualifying_teams (not max_teams)
            required_teams = int(qualifying_teams) if qualifying_teams else max_teams
            if selected_count != required_teams:
                return Response(
                    {"error": f"Must select exactly {required_teams} teams. " f"Currently selected: {selected_count}"},
                    status=400,
                )

        # Mark current round as completed
        if not tournament.round_status:
            tournament.round_status = {}
        tournament.round_status[str(round_num)] = "completed"

        # Find next round - handle both int and string round numbers
        next_round = None
        next_round_num = round_num + 1

        logger.info(f"Ending round {round_num}, looking for next round {next_round_num}")
        logger.info(f"Available rounds: {[r.get('round') for r in tournament.rounds]}")

        for round_config in tournament.rounds:
            # Handle both int and string round numbers
            config_round = round_config.get("round")
            if config_round is None:
                continue
            # Convert to int for comparison
            config_round_int = int(config_round) if isinstance(config_round, (int, str)) else config_round

            logger.info(f"Checking round config: {config_round} (as int: {config_round_int}) vs next: {next_round_num}")

            if config_round_int == next_round_num:
                next_round = config_round_int
                logger.info(f"Found next round: {next_round}")
                break

        if next_round is None:
            logger.warning(f"No next round found. Current round: {round_num}, Total rounds: {len(tournament.rounds)}")

        # Move to next round or reset if all rounds completed
        if next_round:
            # Automatically start next round
            tournament.current_round = next_round
            tournament.round_status[str(next_round)] = "ongoing"

            # Initialize selected_teams for next round if not exists
            if not tournament.selected_teams:
                tournament.selected_teams = {}
            if str(next_round) not in tournament.selected_teams:
                tournament.selected_teams[str(next_round)] = []

            message = f"Round {round_num} completed. Round {next_round} started automatically."
        else:
            # All rounds completed
            tournament.current_round = 0
            message = f"Round {round_num} completed. All rounds are now complete."

        tournament.save(update_fields=["current_round", "round_status", "selected_teams"])
        cache.delete("tournaments:list:all")

        return Response(
            {
                "message": message,
                "current_round": tournament.current_round,
                "round_status": tournament.round_status,
                "all_rounds_completed": next_round is None,
                "next_round_started": next_round is not None,
            }
        )


class SelectWinnerView(generics.GenericAPIView):
    """
    Select winner for final round (when 2 teams, 1 winner)
    POST /api/tournaments/<tournament_id>/select-winner/
    Body: {"winner_id": 123}
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id):
        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        if tournament.current_round == 0:
            return Response({"error": "No round is currently active"}, status=400)

        round_num = tournament.current_round
        round_config = next((r for r in tournament.rounds if r["round"] == round_num), None)

        if not round_config:
            return Response({"error": "Round configuration not found"}, status=400)

        winner_id = request.data.get("winner_id")
        if not winner_id:
            return Response({"error": "winner_id is required"}, status=400)

        # Get participating teams for current round
        if round_num == 1:
            # For round 1, all confirmed teams are participating
            participating_teams = TournamentRegistration.objects.filter(
                tournament=tournament, status="confirmed"
            ).values_list("id", flat=True)
            valid_team_ids = list(participating_teams)
        else:
            # For other rounds, teams selected in previous round are participating
            prev_round_key = str(round_num - 1)
            valid_team_ids = tournament.selected_teams.get(prev_round_key, [])

        # Validate winner is in participating teams
        winner_id_int = int(winner_id)
        if winner_id_int not in valid_team_ids:
            return Response({"error": "Winner must be one of the participating teams for this round"}, status=400)

        # Check if this is a final round (no qualifying_teams or qualifying_teams = 0)
        qualifying_teams = round_config.get("qualifying_teams")
        is_final_round = not qualifying_teams or int(qualifying_teams) == 0

        # Check if it's the last round
        is_last_round = round_num == len(tournament.rounds)

        if not (is_final_round and is_last_round):
            return Response({"error": "Winner selection is only available for final rounds"}, status=400)

        if len(valid_team_ids) < 2:
            return Response({"error": "Final round requires at least 2 teams to select a winner"}, status=400)

        # Save winner
        if not tournament.winners:
            tournament.winners = {}
        round_key = str(round_num)
        tournament.winners[round_key] = winner_id_int

        tournament.save(update_fields=["winners"])
        cache.delete("tournaments:list:all")

        # Get winner registration details
        winner_registration = TournamentRegistration.objects.get(id=winner_id_int, tournament=tournament)

        return Response(
            {
                "message": "Winner selected successfully!",
                "winner": {
                    "id": winner_registration.id,
                    "team_name": winner_registration.team_name or winner_registration.player.user.username,
                    "player_name": winner_registration.player.user.username,
                },
                "round": round_num,
            }
        )


class TournamentStatsView(generics.GenericAPIView):
    """
    Get full tournament leaderboard (accessible by all)
    GET /api/tournaments/<tournament_id>/stats/
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, tournament_id):
        try:
            tournament = Tournament.objects.get(id=tournament_id)
        except Tournament.DoesNotExist:
            return Response({"error": "Tournament not found"}, status=404)

        # Aggregate scores for all teams across all rounds
        team_scores = (
            RoundScore.objects.filter(tournament=tournament)
            .values("team__id", "team__team_name", "team__player__in_game_name")
            .annotate(
                total_position_points=Sum("position_points"),
                total_kill_points=Sum("kill_points"),
                total_points=Sum("total_points"),
            )
            .order_by("-total_points", "-total_kill_points")
        )

        # Add rank
        leaderboard = []
        for idx, entry in enumerate(team_scores, start=1):
            leaderboard.append(
                {
                    "rank": idx,
                    "team_id": entry["team__id"],
                    "team_name": entry["team__team_name"] or entry["team__player__in_game_name"],
                    "player_name": entry["team__player__in_game_name"],
                    "total_position_points": entry["total_position_points"],
                    "total_kill_points": entry["total_kill_points"],
                    "total_points": entry["total_points"],
                }
            )

        return Response(
            {
                "tournament": tournament.title,
                "game": tournament.game_name,
                "status": tournament.status,
                "leaderboard": leaderboard,
            }
        )


class UpdateTournamentFieldsView(generics.UpdateAPIView):
    """
    Update specific tournament fields (restricted - host only)
    PUT/PATCH /api/tournaments/<pk>/update-fields/
    Only allows updating: title, description, rules, banner_image
    """

    queryset = Tournament.objects.all()
    serializer_class = TournamentSerializer
    permission_classes = [IsHostUser]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)

    def get_queryset(self):
        host_profile = HostProfile.objects.get(user=self.request.user)
        return Tournament.objects.filter(host=host_profile)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        # Only allow updating specific fields
        allowed_fields = ["title", "description", "rules", "banner_image"]
        data = request.data.copy()

        # Filter to only allowed fields
        filtered_data = {k: v for k, v in data.items() if k in allowed_fields}

        # Handle file uploads
        if "banner_image" in request.FILES:
            filtered_data["banner_image"] = request.FILES["banner_image"]
        elif "banner_image" in data and (data["banner_image"] == "" or data["banner_image"] == "null"):
            # Remove empty banner_image to keep existing one
            filtered_data.pop("banner_image", None)

        serializer = self.get_serializer(instance, data=filtered_data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        cache.delete("tournaments:list:all")
        return Response(serializer.data)


class EndTournamentView(generics.GenericAPIView):
    """
    End tournament (mark as completed)
    POST /api/tournaments/<tournament_id>/end/
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id):
        from .tasks import update_leaderboard

        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        # Check if all rounds are completed (warning only, not blocking)
        all_rounds_completed = True
        if tournament.round_status and len(tournament.round_status) > 0:
            all_rounds_completed = all(status == "completed" for round_num, status in tournament.round_status.items())

        # End tournament regardless of round status (host decision)
        tournament.status = "completed"
        tournament.current_round = 0
        tournament.save(update_fields=["status", "current_round"])
        cache.delete("tournaments:list:all")

        # Trigger leaderboard update asynchronously
        update_leaderboard.delay()

        message = "Tournament ended successfully"
        if not all_rounds_completed:
            message += " (Note: Not all rounds were completed)"

        return Response(
            {
                "message": message,
                "status": tournament.status,
                "all_rounds_completed": all_rounds_completed,
            }
        )


class PlatformStatsView(generics.GenericAPIView):
    """
    Get platform-wide statistics
    GET /api/tournaments/stats/platform/
    Returns aggregated stats for the entire platform
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        # Total tournaments
        total_tournaments = Tournament.objects.count()

        # Total players (unique player profiles)
        total_players = PlayerProfile.objects.count()

        # Total prize money distributed (sum of prize pools from completed tournaments)
        total_prize_money = (
            Tournament.objects.filter(status="completed").aggregate(total=Sum("prize_pool"))["total"] or 0
        )

        # Total registrations
        total_registrations = TournamentRegistration.objects.count()

        return Response(
            {
                "total_tournaments": total_tournaments,
                "total_players": total_players,
                "total_prize_money": str(total_prize_money),
                "total_registrations": total_registrations,
            }
        )


class UpdateTeamStatusView(generics.GenericAPIView):
    """
    Host updates team registration status (confirm/reject)
    PATCH /api/tournaments/<tournament_id>/registrations/<registration_id>/status/
    Body: {"status": "confirmed"} or {"status": "rejected"}

    Manages participant count:
    - Confirming a pending team: no change (already counted)
    - Confirming a rejected team: increase count
    - Rejecting a pending/confirmed team: decrease count
    """

    permission_classes = [IsHostUser]

    def patch(self, request, tournament_id, registration_id):
        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        try:
            registration = TournamentRegistration.objects.get(id=registration_id, tournament=tournament)
        except TournamentRegistration.DoesNotExist:
            return Response({"error": "Registration not found"}, status=404)

        new_status = request.data.get("status")
        if new_status not in ["confirmed", "rejected", "pending"]:
            return Response({"error": "Invalid status. Must be 'confirmed', 'rejected', or 'pending'"}, status=400)

        old_status = registration.status

        # Update participant count based on status change
        if old_status != new_status:
            # Rejecting a team that was pending or confirmed -> decrease count
            if new_status == "rejected" and old_status in ["pending", "confirmed"]:
                if tournament.current_participants > 0:
                    tournament.current_participants -= 1
                    tournament.save(update_fields=["current_participants"])

            # Confirming a team that was rejected -> increase count
            elif new_status == "confirmed" and old_status == "rejected":
                if tournament.current_participants < tournament.max_participants:
                    tournament.current_participants += 1
                    tournament.save(update_fields=["current_participants"])
                else:
                    return Response({"error": "Tournament is full. Cannot confirm more teams."}, status=400)

        registration.status = new_status
        registration.save()

        return Response(
            {
                "message": f"Team status updated to {new_status}",
                "registration_id": registration.id,
                "status": registration.status,
                "current_participants": tournament.current_participants,
                "max_participants": tournament.max_participants,
            }
        )


class StartTournamentView(generics.GenericAPIView):
    """
    Host explicitly starts the tournament
    POST /api/tournaments/<tournament_id>/start/

    Validates:
    - Pending teams will be automatically confirmed upon starting
    - Tournament status is 'upcoming'

    Actions:
    - Changes status to 'ongoing'
    - Sets current_round to 1
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id):
        try:
            host_profile = HostProfile.objects.get(user=request.user)
            tournament = Tournament.objects.get(id=tournament_id, host=host_profile)
        except Tournament.DoesNotExist:
            return Response({"error": "Tournament not found"}, status=404)

        # Validate tournament status
        if tournament.status != "upcoming":
            return Response({"error": f"Cannot start tournament. Current status: {tournament.status}"}, status=400)

        # Auto-confirm any pending teams before starting
        TournamentRegistration.objects.filter(tournament=tournament, status="pending").update(status="confirmed")

        # Check if starting early
        from django.utils import timezone

        now = timezone.now()
        is_early = now < tournament.tournament_start

        # Update tournament
        tournament.status = "ongoing"
        tournament.current_round = 1

        # Set Round 1 status to ongoing
        if not tournament.round_status:
            tournament.round_status = {}
        tournament.round_status["1"] = "ongoing"

        tournament.save(update_fields=["status", "current_round", "round_status"])

        return Response(
            {
                "message": "Tournament started successfully",
                "status": tournament.status,
                "current_round": tournament.current_round,
                "is_early_start": is_early,
                "scheduled_start": tournament.tournament_start.isoformat() if tournament.tournament_start else None,
            }
        )


class HostDashboardStatsView(APIView):
    """
    Get statistics and data for the host dashboard
    GET /api/tournaments/stats/host/
    """

    permission_classes = [IsHostUser]

    def get(self, request):
        host_profile = HostProfile.objects.get(user=request.user)
        now = timezone.now()
        one_week_ago = now - timezone.timedelta(days=7)
        one_month_ago = now - timezone.timedelta(days=30)

        # Basic Stats
        active_tournaments = Tournament.objects.filter(host=host_profile, status__in=["upcoming", "ongoing"]).count()
        live_now_count = Tournament.objects.filter(host=host_profile, status="ongoing").count()

        total_tournaments = Tournament.objects.filter(host=host_profile).count()

        # Total participants (confirmed teams)
        total_participants = TournamentRegistration.objects.filter(
            tournament__host=host_profile, status="confirmed"
        ).count()

        # Growth this week
        participants_this_week = TournamentRegistration.objects.filter(
            tournament__host=host_profile, status="confirmed", registered_at__gte=one_week_ago
        ).count()

        # Revenue (Sum of entry fees for confirmed registrations)
        revenue_tournaments = (
            TournamentRegistration.objects.filter(tournament__host=host_profile, status="confirmed").aggregate(
                total=Sum("tournament__entry_fee")
            )["total"]
            or 0
        )
        revenue_scrims = (
            ScrimRegistration.objects.filter(scrim__host=host_profile, status="confirmed").aggregate(
                total=Sum("scrim__entry_fee")
            )["total"]
            or 0
        )
        total_revenue = revenue_tournaments + revenue_scrims

        # Monthly growth (Revenue in last 30 days)
        rev_tournaments_month = (
            TournamentRegistration.objects.filter(
                tournament__host=host_profile, status="confirmed", registered_at__gte=one_month_ago
            ).aggregate(total=Sum("tournament__entry_fee"))["total"]
            or 0
        )
        rev_scrims_month = (
            ScrimRegistration.objects.filter(
                scrim__host=host_profile, status="confirmed", registered_at__gte=one_month_ago
            ).aggregate(total=Sum("scrim__entry_fee"))["total"]
            or 0
        )
        growth_this_month = rev_tournaments_month + rev_scrims_month

        # Avg Participation
        avg_participation = (total_participants / total_tournaments) if total_tournaments > 0 else 0

        # Live Tournaments
        live_tournaments = Tournament.objects.filter(host=host_profile, status="ongoing")
        live_serializer = TournamentListSerializer(live_tournaments, many=True)

        # Upcoming Tournaments
        upcoming_tournaments = Tournament.objects.filter(host=host_profile, status="upcoming")[:5]
        upcoming_serializer = TournamentListSerializer(upcoming_tournaments, many=True)

        # Recent Activity (Mocked or aggregated from registrations)
        recent_registrations = TournamentRegistration.objects.filter(tournament__host=host_profile).order_by(
            "-registered_at"
        )[:5]

        recent_activity = []
        for reg in recent_registrations:
            recent_activity.append(
                {
                    "type": "registration",
                    "message": f"New team registered for {reg.tournament.title}",
                    "team_name": reg.team_name or reg.player.in_game_name,
                    "timestamp": reg.registered_at,
                }
            )

        # Add some mock activities if not enough real ones
        if len(recent_activity) < 3:
            recent_activity.append(
                {
                    "type": "info",
                    "message": "Welcome to your new dashboard!",
                    "timestamp": timezone.now(),
                }
            )

        return Response(
            {
                "stats": {
                    "active_tournaments": active_tournaments,
                    "live_now_count": live_now_count,
                    "total_participants": total_participants,
                    "participants_weekly_growth": participants_this_week,
                    "total_revenue": total_revenue,
                    "revenue_monthly_growth": growth_this_month,
                    "avg_participation": round(avg_participation, 1),
                    "growth_percentage": 12.5,  # Mock growth percentage
                },
                "live_tournaments": live_serializer.data,
                "upcoming_tournaments": upcoming_serializer.data,
                "recent_activity": recent_activity,
            }
        )
