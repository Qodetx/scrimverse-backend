import logging

from django.core.cache import cache
from django.db.models import Q, Sum
from django.utils import timezone

from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import HostProfile, PlayerProfile
from tournaments.models import HostRating, Tournament, TournamentRegistration
from tournaments.serializers import (
    HostRatingSerializer,
    TournamentListSerializer,
    TournamentRegistrationSerializer,
    TournamentSerializer,
)
from tournaments.tasks import update_host_dashboard_stats, update_platform_statistics
from tournaments.views.permissions import IsHostUser

logger = logging.getLogger(__name__)


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
            # Only use cache for unauthenticated users — authenticated users
            # need per-user data (is_registered) so bypass cache for them.
            if not request.user or not request.user.is_authenticated:
                cached_data = cache.get(cache_key)
                if cached_data:
                    return Response(cached_data)

            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)

            # Only cache for unauthenticated requests
            if not request.user or not request.user.is_authenticated:
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

        search = self.request.query_params.get("search", None)
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(game_name__icontains=search))

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
        from tournaments.models import RoundScore
        team_scores = (
            RoundScore.objects.filter(tournament=tournament)
            .values("team__id", "team__team_name", "team__player__user__username")
            .annotate(
                total_position_points=Sum("position_points"),
                total_kill_points=Sum("kill_points"),
                total_points=Sum("total_points"),
            )
            .order_by("-total_points", "-total_position_points")
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
