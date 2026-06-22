import logging

from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone

from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import HostProfile, PlayerProfile
from payments.models import Payment
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

                # Check if player has a confirmed direct registration (captain)
                # Exclude cancelled/rejected so a stale cancelled reg doesn't shadow a confirmed team membership
                registration = TournamentRegistration.objects.filter(
                    tournament_id=tournament_id, player=player_profile, status="confirmed"
                ).first()

                if registration:
                    response.data["user_registration_status"] = registration.status
                else:
                    # Check if user is a team member of any team registered in this tournament
                    team_reg = TournamentRegistration.objects.filter(
                        tournament_id=tournament_id,
                        team__members__user=request.user
                    ).exclude(status='rejected').first()

                    if team_reg:
                        response.data["user_registration_status"] = team_reg.status
                    else:
                        response.data["user_registration_status"] = None
            except PlayerProfile.DoesNotExist:
                response.data["user_registration_status"] = None
        else:
            response.data["user_registration_status"] = None

        # Resolve 1st place winner name for completed tournaments
        tournament = self.get_object()
        if tournament.status == "completed" and tournament.winners:
            try:
                final_round = str(tournament.get_total_rounds())
                winner_reg_id = tournament.winners.get(final_round)
                if winner_reg_id:
                    winner_reg = TournamentRegistration.objects.get(id=winner_reg_id)
                    response.data["winner_name"] = winner_reg.team_name or winner_reg.player.user.username
                else:
                    response.data["winner_name"] = None
            except Exception:
                response.data["winner_name"] = None
        else:
            response.data["winner_name"] = None

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


class HostAnalyticsView(APIView):
    """
    Detailed analytics for the authenticated host.
    GET /api/tournaments/stats/host/analytics/
    Returns KPIs, trend data, engagement breakdown, game distribution,
    and per-tournament analytics.
    """

    permission_classes = [IsHostUser]

    def get(self, request):
        host_profile = HostProfile.objects.get(user=request.user)
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        six_months_ago = now - timedelta(days=180)

        # ------------------------------------------------------------------
        # KPIs
        # ------------------------------------------------------------------

        # Total revenue: completed entry_fee payments for host's tournaments
        total_revenue = float(
            Payment.objects.filter(
                tournament__host=host_profile,
                payment_type="entry_fee",
                status="completed",
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )

        # Total confirmed registrations
        total_registrations = TournamentRegistration.objects.filter(
            tournament__host=host_profile, status="confirmed"
        ).count()

        # Average fill rate across host's tournaments (only those with capacity > 0)
        host_tournaments = Tournament.objects.filter(host=host_profile)
        fill_rates = []
        for t in host_tournaments:
            capacity = (t.max_participants or 0) if (t.max_participants or 0) > 0 else (t.max_teams or 0)
            if capacity > 0:
                reg_count = TournamentRegistration.objects.filter(tournament=t, status="confirmed").count()
                fill_rates.append(reg_count / capacity * 100)
        avg_fill_rate = round(sum(fill_rates) / len(fill_rates), 1) if fill_rates else 0.0

        # Returning players percentage
        # A player is "returning" if they appear in ≥ 2 confirmed registrations for this host
        player_reg_counts: dict = {}
        all_regs = TournamentRegistration.objects.filter(
            tournament__host=host_profile, status="confirmed"
        ).values_list("player_id", flat=True)
        for pid in all_regs:
            if pid is not None:
                player_reg_counts[pid] = player_reg_counts.get(pid, 0) + 1
        total_unique_players = len(player_reg_counts)
        returning_count = sum(1 for cnt in player_reg_counts.values() if cnt >= 2)
        returning_players_pct = (
            round(returning_count / total_unique_players * 100, 1) if total_unique_players > 0 else 0.0
        )

        tournaments_hosted = host_tournaments.count()

        kpis = {
            "total_revenue": total_revenue,
            "total_registrations": total_registrations,
            "avg_fill_rate": avg_fill_rate,
            "returning_players_pct": returning_players_pct,
            "avg_dropoff": 0.0,
            "tournaments_hosted": tournaments_hosted,
        }

        # ------------------------------------------------------------------
        # Global registration trend (last 6 months — frontend does range slicing)
        # ------------------------------------------------------------------
        raw_reg_trend = (
            TournamentRegistration.objects.filter(
                tournament__host=host_profile,
                status="confirmed",
                registered_at__gte=six_months_ago,
            )
            .annotate(day=TruncDate("registered_at"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        cumulative = 0
        registration_trend = []
        for r in raw_reg_trend:
            cumulative += r["count"]
            registration_trend.append(
                {
                    "date": r["day"].strftime("%Y-%m-%d"),
                    "registrations": r["count"],
                    "cumulative": cumulative,
                }
            )

        # ------------------------------------------------------------------
        # Global revenue trend (last 6 months)
        # ------------------------------------------------------------------
        raw_revenue = (
            Payment.objects.filter(
                tournament__host=host_profile,
                payment_type="entry_fee",
                status="completed",
                completed_at__gte=six_months_ago,
            )
            .annotate(month=TruncMonth("completed_at"))
            .values("month")
            .annotate(total=Sum("amount"))
            .order_by("month")
        )
        revenue_trend = [
            {"month": p["month"].strftime("%b %Y"), "revenue": float(p["total"])} for p in raw_revenue
        ]

        # ------------------------------------------------------------------
        # Engagement (last 6 months) — returning vs new per month
        # A player is "returning" in a given month if they also registered in
        # ANY OTHER tournament by this host (outside of this month's tournaments).
        # This is tournament-based rather than time-based, so it works correctly
        # even when all tournaments were created within the same calendar month.
        # ------------------------------------------------------------------
        engagement = []
        for i in range(5, -1, -1):
            # Compute month_start as the 1st of the month (i months ago)
            month_start = (now - timedelta(days=i * 30)).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            month_end = (month_start + timedelta(days=32)).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            # Tournaments that had registrations this month
            month_tournament_ids = list(
                TournamentRegistration.objects.filter(
                    tournament__host=host_profile,
                    status="confirmed",
                    registered_at__gte=month_start,
                    registered_at__lt=month_end,
                ).values_list("tournament_id", flat=True).distinct()
            )
            month_player_ids = list(
                TournamentRegistration.objects.filter(
                    tournament__host=host_profile,
                    status="confirmed",
                    registered_at__gte=month_start,
                    registered_at__lt=month_end,
                ).values_list("player_id", flat=True)
            )
            # Players who also registered in any OTHER tournament of this host
            # (i.e. a tournament not in this month's batch)
            other_player_ids = set(
                TournamentRegistration.objects.filter(
                    tournament__host=host_profile,
                    status="confirmed",
                ).exclude(
                    tournament_id__in=month_tournament_ids,
                ).values_list("player_id", flat=True)
            )
            returning_m = 0
            new_players_m = 0
            for player_id in month_player_ids:
                if player_id is None:
                    new_players_m += 1
                    continue
                if player_id in other_player_ids:
                    returning_m += 1
                else:
                    new_players_m += 1
            engagement.append(
                {
                    "month": month_start.strftime("%b %Y"),
                    "returning": returning_m,
                    "new": new_players_m,
                }
            )

        # ------------------------------------------------------------------
        # Game distribution — by registration count per game
        # ------------------------------------------------------------------
        reg_by_game = (
            TournamentRegistration.objects.filter(
                tournament__host=host_profile, status="confirmed"
            )
            .values("tournament__game_name")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        total_regs_for_dist = sum(g["count"] for g in reg_by_game)
        game_distribution = []
        for g in reg_by_game:
            game_name = g["tournament__game_name"]
            if game_name:
                pct = round(g["count"] / total_regs_for_dist * 100, 1) if total_regs_for_dist > 0 else 0.0
                game_distribution.append({"name": game_name, "value": pct})

        # ------------------------------------------------------------------
        # Per-tournament analytics
        # ------------------------------------------------------------------
        # Pre-build set of all player IDs registered to host's tournaments
        # (used for cross-tournament returning player checks)
        all_host_player_ids = set(
            TournamentRegistration.objects.filter(
                tournament__host=host_profile, status="confirmed"
            ).values_list("player_id", flat=True)
        )

        tournaments_data = []
        for t in host_tournaments.order_by("-created_at"):
            t_capacity = (t.max_participants or 0) if (t.max_participants or 0) > 0 else (t.max_teams or 0)
            t_regs = TournamentRegistration.objects.filter(tournament=t, status="confirmed").count()
            t_fill_rate = round(t_regs / t_capacity * 100, 1) if t_capacity > 0 else 0.0
            t_revenue = float(
                Payment.objects.filter(
                    tournament=t, payment_type="entry_fee", status="completed"
                ).aggregate(total=Sum("amount"))["total"]
                or 0
            )

            # Per-tournament registration trend (last 6 months)
            raw_t_reg_trend = (
                TournamentRegistration.objects.filter(
                    tournament=t,
                    status="confirmed",
                    registered_at__gte=six_months_ago,
                )
                .annotate(day=TruncDate("registered_at"))
                .values("day")
                .annotate(count=Count("id"))
                .order_by("day")
            )
            t_cum = 0
            t_reg_trend = []
            for r in raw_t_reg_trend:
                t_cum += r["count"]
                t_reg_trend.append(
                    {
                        "date": r["day"].strftime("%Y-%m-%d"),
                        "registrations": r["count"],
                        "cumulative": t_cum,
                    }
                )

            # Per-tournament revenue trend (last 6 months, grouped by month)
            raw_t_rev = (
                Payment.objects.filter(
                    tournament=t,
                    payment_type="entry_fee",
                    status="completed",
                    completed_at__gte=six_months_ago,
                )
                .annotate(month=TruncMonth("completed_at"))
                .values("month")
                .annotate(total=Sum("amount"))
                .order_by("month")
            )
            t_rev_trend = [
                {"month": p["month"].strftime("%b %Y"), "revenue": float(p["total"])} for p in raw_t_rev
            ]

            # Per-tournament engagement: check how many players also played in other
            # tournaments by this host (cross-tournament returning)
            t_player_ids = list(
                TournamentRegistration.objects.filter(tournament=t, status="confirmed").values_list(
                    "player_id", flat=True
                )
            )
            # Players registered to other host tournaments (excluding this one)
            other_player_ids = set(
                TournamentRegistration.objects.filter(
                    tournament__host=host_profile, status="confirmed"
                )
                .exclude(tournament=t)
                .values_list("player_id", flat=True)
            )
            t_returning = sum(1 for p in t_player_ids if p is not None and p in other_player_ids)
            t_new = len(t_player_ids) - t_returning

            # Per-tournament registered teams (for team list in analytics detail view)
            t_team_regs = (
                TournamentRegistration.objects.filter(tournament=t, status="confirmed")
                .select_related("team", "player__user")
                .order_by("registered_at")
            )
            t_teams = []
            for reg in t_team_regs:
                team_obj = reg.team
                member_count = team_obj.members.count() if team_obj else 1
                t_teams.append(
                    {
                        "id": team_obj.id if team_obj else None,
                        "name": reg.team_name or (team_obj.name if team_obj else "Unknown"),
                        "players": member_count,
                        "registered_at": reg.registered_at.strftime("%b %d") if reg.registered_at else "",
                    }
                )

            tournaments_data.append(
                {
                    "id": t.id,
                    "name": t.title,
                    "game": t.game_name,
                    "registrations": t_regs,
                    "capacity": t_capacity,
                    "fill_rate": t_fill_rate,
                    "revenue": t_revenue,
                    "status": t.status,
                    "registration_trend": t_reg_trend,
                    "revenue_trend": t_rev_trend,
                    "engagement": {"returning": t_returning, "new": t_new},
                    "teams": t_teams,
                }
            )

        return Response(
            {
                "kpis": kpis,
                "registration_trend": registration_trend,
                "revenue_trend": revenue_trend,
                "engagement": engagement,
                "game_distribution": game_distribution,
                "tournaments": tournaments_data,
            }
        )
