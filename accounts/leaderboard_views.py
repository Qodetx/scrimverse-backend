"""
Leaderboard API views
"""
from django.core.cache import cache
from django.db.models import F

from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.models import TeamStatistics
from accounts.serializers import TeamStatisticsSerializer


class LeaderboardView(generics.GenericAPIView):
    """
    Get top teams leaderboard
    GET /api/leaderboard/?limit=50&type=tournaments
    GET /api/leaderboard/?limit=50&type=scrims
    """

    permission_classes = [AllowAny]

    def get(self, request):
        limit = int(request.query_params.get("limit", 50))
        leaderboard_type = request.query_params.get("type", "tournaments")  # 'tournaments' or 'scrims'

        # Try to get from cache first
        cache_key = f"leaderboard:{leaderboard_type}:top{limit}"
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(cached_data)

        # Get top teams based on type
        if leaderboard_type == "scrims":
            # For scrims leaderboard, order by scrim points
            top_teams = (
                TeamStatistics.objects.select_related("team")
                .annotate(scrim_total=F("scrim_position_points") + F("scrim_kill_points"))
                .filter(scrim_total__gt=0)
                .order_by("-scrim_total", "-scrim_wins", "-scrim_kill_points")[:limit]
            )

            # Manually add rank for scrims
            leaderboard_data = []
            for rank, stats in enumerate(top_teams, start=1):
                data = TeamStatisticsSerializer(stats).data
                data["rank"] = rank
                data["total_points"] = stats.scrim_position_points + stats.scrim_kill_points
                data["total_position_points"] = stats.scrim_position_points
                data["total_kill_points"] = stats.scrim_kill_points
                leaderboard_data.append(data)

            data = {
                "leaderboard": leaderboard_data,
                "total_teams": TeamStatistics.objects.filter(scrim_position_points__gt=0).count(),
            }
        else:
            # For tournaments leaderboard, order by tournament points
            top_teams = (
                TeamStatistics.objects.select_related("team")
                .annotate(tournament_total=F("tournament_position_points") + F("tournament_kill_points"))
                .filter(tournament_total__gt=0)
                .order_by("-tournament_total", "-tournament_wins", "-tournament_kill_points")[:limit]
            )

            # Manually add rank for tournaments
            leaderboard_data = []
            for rank, stats in enumerate(top_teams, start=1):
                data = TeamStatisticsSerializer(stats).data
                data["rank"] = rank
                data["total_points"] = stats.tournament_position_points + stats.tournament_kill_points
                data["total_position_points"] = stats.tournament_position_points
                data["total_kill_points"] = stats.tournament_kill_points
                leaderboard_data.append(data)

            data = {
                "leaderboard": leaderboard_data,
                "total_teams": TeamStatistics.objects.filter(tournament_position_points__gt=0).count(),
            }

        # Cache for 5 minutes
        cache.set(cache_key, data, 300)

        return Response(data)


class TeamRankView(generics.GenericAPIView):
    """
    Get specific team's rank and statistics
    GET /api/teams/<team_id>/rank/
    """

    permission_classes = [AllowAny]

    def get(self, request, team_id):
        try:
            stats = TeamStatistics.objects.select_related("team").get(team_id=team_id)
            serializer = TeamStatisticsSerializer(stats)
            return Response(serializer.data)
        except TeamStatistics.DoesNotExist:
            return Response(
                {
                    "rank": 0,
                    "tournament_wins": 0,
                    "scrim_wins": 0,
                    "total_position_points": 0,
                    "total_kill_points": 0,
                    "total_points": 0,
                    "message": "No statistics available for this team",
                }
            )
