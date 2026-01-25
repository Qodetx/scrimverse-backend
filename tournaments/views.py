import logging

from django.core.cache import cache
from django.db.models import Q, Sum
from django.utils import timezone

from rest_framework import generics, parsers, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import HostProfile, PlayerProfile, TeamMember, User
from accounts.tasks import update_host_rating_cache
from tournaments.models import HostRating, RoundScore, Tournament, TournamentRegistration
from tournaments.serializers import (
    HostRatingSerializer,
    TournamentListSerializer,
    TournamentRegistrationSerializer,
    TournamentSerializer,
)
from tournaments.tasks import update_host_dashboard_stats, update_leaderboard, update_platform_statistics

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
        entry_fee = self.request.query_params.get("entry_fee", None)

        if status_param:
            queryset = queryset.filter(status=status_param)
        if game:
            queryset = queryset.filter(game_name__icontains=game)
        if event_mode:
            queryset = queryset.filter(event_mode=event_mode)
        if entry_fee is not None:
            queryset = queryset.filter(entry_fee=entry_fee)

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
    Host creates a tournament - initiates payment flow
    POST /api/tournaments/create/
    Returns payment redirect URL instead of creating tournament immediately
    """

    serializer_class = TournamentSerializer
    permission_classes = [IsHostUser]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)

    def create(self, request, *args, **kwargs):
        """Validate tournament data and initiate payment"""
        from uuid import uuid4

        from decouple import config

        from payments.models import Payment
        from payments.services import phonepe_service

        logger.debug(
            f"Tournament creation request - Host: {request.user.id}, Event mode: {request.data.get('event_mode')}"
        )

        # Clean empty file fields (FormData sends empty strings for missing files)
        data = request.data.copy()

        # Remove empty file fields to prevent validation errors
        for file_field in ["banner_image", "tournament_file"]:
            if file_field in data:
                value = data[file_field]
                if value == "" or value == "null" or (isinstance(value, str) and not value):
                    data.pop(file_field)
                elif hasattr(value, "size") and value.size == 0:
                    data.pop(file_field)

        # Validate the data using serializer
        serializer = self.get_serializer(data=data)
        if not serializer.is_valid():
            logger.error(f"[DEBUG] Serializer validation errors: {serializer.errors}")
            return Response(serializer.errors, status=400)

        # Get validated data but DON'T create tournament yet
        validated_data = serializer.validated_data
        plan_type = validated_data.get("plan_type", "basic")
        event_mode = validated_data.get("event_mode", "TOURNAMENT")

        # Get dynamic price from database (or fallback to defaults)
        from payments.models import PlanPricing

        amount = PlanPricing.get_price(event_mode, plan_type)

        # ✅ CHECK IF FREE PLAN (amount <= 0)
        if amount <= 0:
            # Skip payment, create tournament directly
            logger.info(f"Free plan detected ({plan_type}), creating tournament directly")

            # Create tournament immediately
            tournament = serializer.save(
                host=request.user.host_profile, plan_payment_status=True, plan_payment_id="FREE_PLAN"
            )

            logger.info(f"Tournament created (free plan): {tournament.id} - {tournament.title}")

            # Invalidate caches
            cache.delete("tournaments:list:all")
            cache.delete(f"host:dashboard:{request.user.host_profile.id}")

            return Response(
                {
                    "success": True,
                    "message": "Tournament created successfully (Free Plan)",
                    "tournament_id": tournament.id,
                    "payment_required": False,  # Signal to frontend to skip payment
                    "plan_type": plan_type,
                    "amount": 0,
                },
                status=200,
            )

        # PAID PLAN - Continue with payment flow
        # Generate unique merchant order ID
        merchant_order_id = f"ORD_{uuid4().hex[:16].upper()}"

        # Convert amount to paisa
        amount_paisa = int(amount * 100)

        # Prepare redirect URL
        frontend_url = config("CORS_ALLOWED_ORIGINS", default="http://localhost:3000").split(",")[0]
        redirect_url = f"{frontend_url}/host/dashboard?payment_status=check&order_id={merchant_order_id}"

        # Store tournament data as JSON (serialize files as paths if they exist)
        from datetime import date, datetime, time
        from decimal import Decimal

        pending_tournament_data = {}
        # Fields to exclude (we set these explicitly when creating the tournament)
        excluded_fields = {"plan_payment_status", "plan_payment_id"}

        for key, value in validated_data.items():
            if key in excluded_fields:
                continue  # Skip fields we'll set explicitly
            if hasattr(value, "name"):  # File field
                pending_tournament_data[key] = value.name
            elif hasattr(value, "id"):  # Foreign key
                pending_tournament_data[key] = value.id
            elif isinstance(value, Decimal):
                pending_tournament_data[key] = float(value)
            elif isinstance(value, (datetime, date)):
                pending_tournament_data[key] = value.isoformat()
            elif isinstance(value, time):
                pending_tournament_data[key] = value.isoformat()
            else:
                pending_tournament_data[key] = value

        # Add host ID
        pending_tournament_data["host_id"] = request.user.host_profile.id

        # Prepare metadata - udf3 has 256 char limit, so store tournament data separately
        payment_type = "scrim_plan" if event_mode == "SCRIM" else "tournament_plan"
        meta_info = {
            "udf1": str(request.user.id),
            "udf2": payment_type,
            "udf3": payment_type,  # Just store payment type (within 256 char limit)
            "udf4": plan_type,
            "udf5": merchant_order_id,
            "tournament_data": pending_tournament_data,  # Store actual data here (not sent to PhonePe)
        }

        # Create payment record
        try:
            payment = Payment.objects.create(
                merchant_order_id=merchant_order_id,
                payment_type=payment_type,
                amount=amount,
                amount_paisa=amount_paisa,
                user=request.user,
                host_profile=request.user.host_profile,
                status="pending",
                meta_info=meta_info,
            )

            # Initiate payment with PhonePe
            phonepe_response = phonepe_service.initiate_payment(
                amount=amount_paisa,
                redirect_url=redirect_url,
                merchant_order_id=merchant_order_id,
                meta_info_dict=meta_info,
                message=f"Payment for {validated_data.get('title', 'Tournament')} - {plan_type.title()} Plan",
                expire_after=43200,  # 12 hours
                disable_payment_retry=False,
            )

            if not phonepe_response.get("success"):
                payment.status = "failed"
                payment.error_code = phonepe_response.get("error_code", "")
                payment.save()

                return Response(
                    {"error": "Failed to initiate payment", "details": phonepe_response.get("error")},
                    status=500,
                )

            # Update payment with PhonePe response
            payment.phonepe_order_id = phonepe_response.get("order_id")
            payment.redirect_url = phonepe_response.get("redirect_url")
            payment.save()

            logger.info(f"Payment initiated for tournament creation: {merchant_order_id}")

            return Response(
                {
                    "success": True,
                    "message": "Please complete payment to create tournament",
                    "merchant_order_id": merchant_order_id,
                    "phonepe_order_id": phonepe_response.get("order_id"),
                    "redirect_url": phonepe_response.get("redirect_url"),
                    "amount": float(amount),
                    "plan_type": plan_type,
                    "payment_required": True,  # Signal to frontend to open iframe
                },
                status=200,
            )

        except Exception as e:
            logger.error(f"Error initiating tournament payment: {str(e)}")
            return Response({"error": "Internal server error"}, status=500)


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

    def create(self, request, *args, **kwargs):
        """Override create to handle payment-required response status"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            self.perform_create(serializer)
        except ValidationError as e:
            # If it's a payment_required "error", return it as a 200 response
            if isinstance(e.detail, dict) and e.detail.get("payment_required"):
                return Response(e.detail, status=status.HTTP_200_OK)
            # Re-raise other validation errors
            raise

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        from uuid import uuid4

        from decouple import config

        from payments.models import Payment
        from payments.services import phonepe_service

        logger.debug(
            f"Tournament registration request - Player: {self.request.user.id}, Tournament: {self.kwargs['tournament_id']}"  # noqa E501
        )

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
        confirmed_count = TournamentRegistration.objects.filter(tournament=tournament).count()

        if confirmed_count >= tournament.max_participants:
            raise ValidationError({"error": "Tournament is full"})

        # Get player_usernames from validated data
        player_usernames = serializer.validated_data.get("player_usernames", [])
        team_id = serializer.validated_data.get("team_id")

        # Validate that the current user is in the team (only when not using existing team_id)
        if not team_id:
            current_username = self.request.user.username
            if current_username not in player_usernames:
                raise ValidationError({"player_usernames": "You must include your own username in the team"})

            # ✅ VALIDATE: All player_usernames must be registered players
            if player_usernames:
                invalid_usernames = []
                for username in player_usernames:
                    if username:
                        user_exists = User.objects.filter(username=username, user_type="player").exists()
                        if not user_exists:
                            invalid_usernames.append(username)

                if invalid_usernames:
                    raise ValidationError(
                        {
                            "player_usernames": f"The following players were not found: {', '.join(invalid_usernames)}. Only registered ScrimVerse players can join tournaments."  # noqa: E501
                        }
                    )

        # Check if any team member is already registered (check by player profile IDs)
        team_users = User.objects.filter(username__in=player_usernames, user_type="player").select_related(
            "player_profile"
        )
        team_player_ids = {user.player_profile.id for user in team_users if hasattr(user, "player_profile")}

        # Check existing registrations
        existing_registrations = TournamentRegistration.objects.filter(tournament=tournament)
        for registration in existing_registrations:
            if registration.team_members:
                registered_player_ids = {member.get("id") for member in registration.team_members if member.get("id")}
                overlapping_ids = team_player_ids & registered_player_ids
                if overlapping_ids:
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

        # Check if entry fee is required
        if tournament.entry_fee > 0:
            # PAYMENT FLOW - Don't create registration yet

            # Prepare registration data to store in meta_info
            pending_reg_data = {
                "tournament_id": tournament_id,
                "player_id": player_profile.id,
                "team_id": team_id,
                "player_usernames": player_usernames,
                "team_name": serializer.validated_data.get("team_name", ""),
                "save_as_team": serializer.validated_data.get("save_as_team", False),
            }

            # Add any other validated data
            for key, value in serializer.validated_data.items():
                if key not in [
                    "player_usernames",
                    "team_name",
                    "team_id",
                    "save_as_team",
                    "tournament_id",
                    "player_id",
                ]:
                    if hasattr(value, "id"):
                        pending_reg_data[key] = value.id
                    else:
                        pending_reg_data[key] = value

            # Generate unique merchant order ID
            merchant_order_id = f"ORD_{uuid4().hex[:16].upper()}"
            amount = tournament.entry_fee
            amount_paisa = int(amount * 100)

            # Prepare redirect URL
            frontend_url = config("CORS_ALLOWED_ORIGINS", default="http://localhost:3000").split(",")[0]
            redirect_url = f"{frontend_url}/player/dashboard?payment_status=check&order_id={merchant_order_id}"

            # Prepare metadata - udf3 has 256 char limit, so store registration data separately
            meta_info = {
                "udf1": str(self.request.user.id),
                "udf2": "entry_fee",
                "udf3": "entry_fee",  # Just store payment type (within 256 char limit)
                "udf4": str(tournament_id),
                "udf5": merchant_order_id,
                "registration_data": pending_reg_data,  # Store actual data here (not sent to PhonePe)
            }

            try:
                # Create payment record
                payment = Payment.objects.create(
                    merchant_order_id=merchant_order_id,
                    payment_type="entry_fee",
                    amount=amount,
                    amount_paisa=amount_paisa,
                    user=self.request.user,
                    player_profile=player_profile,
                    status="pending",
                    meta_info=meta_info,
                )

                # Initiate payment with PhonePe
                phonepe_response = phonepe_service.initiate_payment(
                    amount=amount_paisa,
                    redirect_url=redirect_url,
                    merchant_order_id=merchant_order_id,
                    meta_info_dict=meta_info,
                    message=f"Entry fee for {tournament.title}",
                    expire_after=43200,  # 12 hours
                    disable_payment_retry=False,
                )

                if not phonepe_response.get("success"):
                    payment.status = "failed"
                    payment.error_code = phonepe_response.get("error_code", "")
                    payment.save()

                    raise ValidationError(
                        {"error": "Failed to initiate payment", "details": phonepe_response.get("error")}
                    )

                # Update payment with PhonePe response
                payment.phonepe_order_id = phonepe_response.get("order_id")
                payment.redirect_url = phonepe_response.get("redirect_url")
                payment.save()

                logger.info(f"Payment initiated for registration: {merchant_order_id}")

                # Return payment info instead of registration
                # This will be caught by the view and returned as response
                raise ValidationError(
                    {
                        "payment_required": True,
                        "merchant_order_id": merchant_order_id,
                        "redirect_url": phonepe_response.get("redirect_url"),
                        "amount": float(amount),
                        "message": "Please complete payment to register",
                    }
                )

            except ValidationError:
                raise
            except Exception as e:
                logger.error(f"Error initiating registration payment: {str(e)}")
                raise ValidationError({"error": "Internal server error"})

        else:
            # NO PAYMENT REQUIRED - Create registration directly
            registration = serializer.save(player_id=player_profile.id, tournament_id=tournament_id)

            logger.info(
                f"Registration created - ID: {registration.id}, Player: {player_profile.user.username}, Tournament: {tournament.title}, Team: {registration.team_name}"  # noqa E501
            )

            # Update participant count
            tournament.current_participants += 1
            tournament.save()

            # Invalidate caches
            cache.delete("tournaments:list:all")
            cache.delete(f"host:dashboard:{tournament.host.id}")

            update_host_dashboard_stats.delay(tournament.host.id)


class PlayerTournamentRegistrationsView(generics.ListAPIView):
    """
    Get all tournament registrations of a player
    GET /api/tournaments/my-registrations/
    """

    serializer_class = TournamentRegistrationSerializer
    permission_classes = [IsPlayerUser]

    def get_queryset(self):
        try:
            player_profile = PlayerProfile.objects.get(user=self.request.user)
            team_ids = TeamMember.objects.filter(user=self.request.user).values_list("team_id", flat=True)
            return (
                TournamentRegistration.objects.filter(Q(player=player_profile) | Q(team_id__in=team_ids))
                .distinct()
                .order_by("-registered_at")
            )
        except PlayerProfile.DoesNotExist:
            return TournamentRegistration.objects.none()


class PlayerPublicRegistrationsView(generics.ListAPIView):
    """
    Get all tournament registrations for any player publicly
    GET /api/tournaments/player/<player_id>/registrations/
    """

    serializer_class = TournamentRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        player_id = self.kwargs["player_id"]

        try:
            player = PlayerProfile.objects.get(id=player_id)
            user = player.user
            team_ids = TeamMember.objects.filter(user=user).values_list("team_id", flat=True)

            queryset = TournamentRegistration.objects.filter(
                Q(player_id=player_id) | Q(team_id__in=team_ids)
            ).distinct()
        except PlayerProfile.DoesNotExist:
            return TournamentRegistration.objects.none()

        if self.request.query_params.get("confirmed") == "true":
            queryset = queryset.filter(status="confirmed")
        return queryset.order_by("-registered_at")


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
        update_host_rating_cache.delay(host_profile.id)


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
        logger.debug(
            f"Start round request - Tournament: {tournament_id}, Round: {round_number}, Host: {request.user.id}"
        )

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

        logger.info(f"Round started - Tournament: {tournament.id}, Round: {round_number}, Status: ongoing")

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
        logger.debug(f"Submit round scores request - Tournament: {tournament_id}, Host: {request.user.id}")

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

        logger.info(
            f"Round scores submitted - Tournament: {tournament.id}, Round: {round_num}, Teams scored: {len(scores_data)}, Top teams: {len(selected_team_ids)}"  # noqa E501
        )

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
        logger.debug(
            f"Select teams request - Tournament: {tournament_id}, Action: {request.data.get('action')}, Host: {request.user.id}"  # noqa E501
        )

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

        logger.info(
            f"Teams {action}ed - Tournament: {tournament.id}, Round: {round_num}, Count: {len(tournament.selected_teams[round_num])}"  # noqa E501
        )

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
        logger.debug(
            f"Select winner request - Tournament: {tournament_id}, Winner ID: {request.data.get('winner_id')}, Host: {request.user.id}"  # noqa E501
        )

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

        logger.info(f"Winner selected - Tournament: {tournament.id}, Round: {round_num}, Winner ID: {winner_id_int}")

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
            .values("team__id", "team__team_name", "team__player__user__username")
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
                    "team_name": entry["team__team_name"] or entry["team__player__user__username"],
                    "player_name": entry["team__player__user__username"],
                    "total_position_points": entry["total_position_points"],
                    "total_kill_points": entry["total_kill_points"],
                    "total_points": entry["total_points"],
                }
            )

        return Response(
            {
                "tournament": tournament.title,
                "game": tournament.game_name,
                "event_mode": tournament.event_mode,
                "status": tournament.status,
                "leaderboard": leaderboard,
            }
        )


class UpdateTournamentFieldsView(generics.UpdateAPIView):
    """
    Update specific tournament fields (restricted - host only)
    PUT/PATCH /api/tournaments/<pk>/update-fields/
    Only allows updating: title, description, rules, rounds, round_names
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
        allowed_fields = ["title", "description", "rules", "round_names", "rounds"]
        data = request.data.copy()

        # Filter to only allowed fields
        filtered_data = {k: v for k, v in data.items() if k in allowed_fields}

        # Handle JSON fields
        if "round_names" in filtered_data:
            import json

            try:
                if isinstance(filtered_data["round_names"], str):
                    filtered_data["round_names"] = json.loads(filtered_data["round_names"])
            except (json.JSONDecodeError, TypeError):
                pass  # Let serializer validation handle invalid JSON

        if "rounds" in filtered_data:
            import json

            try:
                if isinstance(filtered_data["rounds"], str):
                    filtered_data["rounds"] = json.loads(filtered_data["rounds"])
            except (json.JSONDecodeError, TypeError):
                pass  # Let serializer validation handle invalid JSON

        logger.info(f"Updating tournament {instance.id} with fields: {list(filtered_data.keys())}")
        if "rounds" in filtered_data:
            logger.info(f"New rounds data: {filtered_data['rounds']}")
        if "round_names" in filtered_data:
            logger.info(f"New round_names data: {filtered_data['round_names']}")

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

        logger.info(
            f"Tournament ended - ID: {tournament.id}, Title: {tournament.title}, All rounds completed: {all_rounds_completed}"  # noqa E501
        )

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
        # Try cache first (populated by Celery task every hour)
        stats = cache.get("platform:statistics")

        if not stats:
            update_platform_statistics.delay()

            # Return basic stats as fallback while calculating
            stats = {
                "total_tournaments": Tournament.objects.count(),
                "total_players": PlayerProfile.objects.count(),
                "total_prize_money": str(
                    Tournament.objects.filter(status="completed").aggregate(total=Sum("prize_pool"))["total"] or 0
                ),
                "total_registrations": TournamentRegistration.objects.count(),
                "message": "Full statistics are being calculated in the background...",
            }

        return Response(stats)


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
        logger.debug(
            f"Update team status request - Tournament: {tournament_id}, Registration: {registration_id}, New status: {request.data.get('status')}"  # noqa E501
        )

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

        logger.info(
            f"Team status updated - Registration: {registration.id}, Old: {old_status}, New: {new_status}, Tournament: {tournament.id}"  # noqa E501
        )

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
        logger.debug(f"Start tournament request - Tournament: {tournament_id}, Host: {request.user.id}")

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

        logger.info(f"Tournament started - ID: {tournament.id}, Title: {tournament.title}, Early start: {is_early}")

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

        # Try cache first (populated by Celery task every 10 minutes)
        stats = cache.get(f"host:dashboard:{host_profile.id}")

        if not stats:
            # Cache miss - trigger async calculation
            update_host_dashboard_stats.delay(host_profile.id)

            # Return basic stats as fallback while calculating
            stats = {
                "matches_hosted": Tournament.objects.filter(host=host_profile).count(),
                "total_participants": TournamentRegistration.objects.filter(
                    tournament__host=host_profile, status="confirmed"
                ).count(),
                "total_prize_pool": float(
                    Tournament.objects.filter(host=host_profile).aggregate(total=Sum("prize_pool"))["total"] or 0
                ),
                "host_rating": float(host_profile.rating),
                "message": "Full statistics are being calculated in the background...",
            }

        # Always fetch live tournaments and recent activity (these change frequently)
        live_tournaments = Tournament.objects.filter(host=host_profile, status="ongoing")
        live_serializer = TournamentListSerializer(live_tournaments, many=True)

        upcoming_tournaments = Tournament.objects.filter(host=host_profile, status="upcoming").order_by(
            "tournament_start"
        )[:10]
        upcoming_serializer = TournamentListSerializer(upcoming_tournaments, many=True)

        past_tournaments = Tournament.objects.filter(host=host_profile, status="completed").order_by("-updated_at")[:10]
        past_serializer = TournamentListSerializer(past_tournaments, many=True)

        # Recent Activity - Multiple types
        recent_activity = []

        # 1. Recent Registrations
        recent_registrations = TournamentRegistration.objects.filter(tournament__host=host_profile).order_by(
            "-registered_at"
        )[:3]

        for reg in recent_registrations:
            recent_activity.append(
                {
                    "type": "registration",
                    "message": f"New team registered for {reg.tournament.title}",
                    "detail": reg.team_name or reg.player.user.username,
                    "timestamp": reg.registered_at,
                }
            )

        # 2. Tournament Status Changes (Started/Completed)
        recent_started = Tournament.objects.filter(host=host_profile, status="ongoing").order_by("-updated_at")[:2]

        for tournament in recent_started:
            recent_activity.append(
                {
                    "type": "tournament_started",
                    "message": f"{tournament.title} has started",
                    "detail": f"Round {tournament.current_round} is now live",
                    "timestamp": tournament.updated_at,
                }
            )

        recent_completed = Tournament.objects.filter(host=host_profile, status="completed").order_by("-updated_at")[:2]

        for tournament in recent_completed:
            recent_activity.append(
                {
                    "type": "tournament_completed",
                    "message": f"{tournament.title} has been completed",
                    "detail": "All rounds finished",
                    "timestamp": tournament.updated_at,
                }
            )

        # 3. Recent Host Ratings
        recent_ratings = HostRating.objects.filter(host=host_profile).order_by("-created_at")[:2]

        for rating in recent_ratings:
            recent_activity.append(
                {
                    "type": "rating_received",
                    "message": f"New rating received: {rating.rating}/5",
                    "detail": rating.review[:50] + "..."
                    if rating.review and len(rating.review) > 50
                    else rating.review or "No comment",
                    "timestamp": rating.created_at,
                }
            )

        # Sort all activities by timestamp (newest first) and limit to 10
        recent_activity.sort(key=lambda x: x["timestamp"], reverse=True)
        recent_activity = recent_activity[:10]

        return Response(
            {
                "stats": stats,
                "live_tournaments": live_serializer.data,
                "upcoming_tournaments": upcoming_serializer.data,
                "past_tournaments": past_serializer.data,
                "recent_activity": recent_activity,
            }
        )

        logger.debug(f"Host dashboard stats - Host ID: {host_profile.id}, Stats: {stats}")
        logger.debug(f"Host dashboard stats - Host ID: {host_profile.id}, Recent activity: {recent_activity}")
