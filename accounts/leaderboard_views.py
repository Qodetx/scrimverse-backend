"""
Leaderboard API views
"""
import logging

from django.core.cache import cache
from django.db.models import F, Sum

from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.models import TeamStatistics
from accounts.serializers import TeamStatisticsSerializer

logger = logging.getLogger("accounts")


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
        game_filter = request.query_params.get("game", "ALL")  # Game-specific filter

        # Validate game_filter
        valid_games = ['BGMI', 'COD', 'Valorant', 'Freefire', 'Scarfall', 'ALL']
        if game_filter not in valid_games:
            logger.warning(f"Invalid game filter: {game_filter}, defaulting to 'ALL'")
            game_filter = 'ALL'

        logger.debug(f"Leaderboard request - Type: {leaderboard_type}, Limit: {limit}, Game: {game_filter}")

        # Try to get from cache first (include game in cache key)
        cache_key = f"leaderboard:{leaderboard_type}:{game_filter}:top{limit}"
        cached_data = cache.get(cache_key)

        if cached_data:
            logger.debug(f"Leaderboard cache HIT - Key: {cache_key}")
            return Response(cached_data)

        logger.debug(f"Leaderboard cache MISS - Key: {cache_key}, fetching from database")

        # Build base queryset: for 'ALL', exclude literal 'ALL' rows and aggregate across games
        # For specific game, filter directly
        if leaderboard_type == "scrims":
            if game_filter == 'ALL':
                # Aggregate across all game-specific rows per team
                aggregated = (
                    TeamStatistics.objects.exclude(game_name='ALL')
                    .values('team_id')
                    .annotate(
                        total_scrim_wins=Sum('scrim_wins'),
                        total_scrim_position=Sum('scrim_position_points'),
                        total_scrim_kill=Sum('scrim_kill_points'),
                    )
                    .filter(total_scrim_position__gt=0)
                    .order_by('-total_scrim_position', '-total_scrim_kill', '-total_scrim_wins')[:limit]
                )
                leaderboard_data = []
                for rank, entry in enumerate(aggregated, start=1):
                    # Get the first stats row for serialization (team name etc.)
                    sample = TeamStatistics.objects.filter(team_id=entry['team_id']).exclude(game_name='ALL').select_related('team').first()
                    if sample:
                        data = TeamStatisticsSerializer(sample).data
                        data["rank"] = rank
                        data["scrim_wins"] = entry['total_scrim_wins']
                        data["total_points"] = (entry['total_scrim_position'] or 0) + (entry['total_scrim_kill'] or 0)
                        data["total_position_points"] = entry['total_scrim_position'] or 0
                        data["total_kill_points"] = entry['total_scrim_kill'] or 0
                        leaderboard_data.append(data)
                data = {
                    "leaderboard": leaderboard_data,
                    "total_teams": len(leaderboard_data),
                }
            else:
                # For scrims leaderboard, order by scrim points
                top_teams = (
                    TeamStatistics.objects.filter(game_name=game_filter).select_related("team")
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
                    "total_teams": TeamStatistics.objects.filter(game_name=game_filter, scrim_position_points__gt=0).count(),
                }
            logger.debug(f"Scrims leaderboard generated - {len(leaderboard_data)} teams")
        else:
            if game_filter == 'ALL':
                # Aggregate across all game-specific rows per team
                aggregated = (
                    TeamStatistics.objects.exclude(game_name='ALL')
                    .values('team_id')
                    .annotate(
                        total_t_wins=Sum('tournament_wins'),
                        total_t_position=Sum('tournament_position_points'),
                        total_t_kill=Sum('tournament_kill_points'),
                    )
                    .filter(total_t_position__gt=0)
                    .order_by('-total_t_position', '-total_t_kill', '-total_t_wins')[:limit]
                )
                leaderboard_data = []
                for rank, entry in enumerate(aggregated, start=1):
                    sample = TeamStatistics.objects.filter(team_id=entry['team_id']).exclude(game_name='ALL').select_related('team').first()
                    if sample:
                        data = TeamStatisticsSerializer(sample).data
                        data["rank"] = rank
                        data["tournament_wins"] = entry['total_t_wins']
                        data["total_points"] = (entry['total_t_position'] or 0) + (entry['total_t_kill'] or 0)
                        data["total_position_points"] = entry['total_t_position'] or 0
                        data["total_kill_points"] = entry['total_t_kill'] or 0
                        leaderboard_data.append(data)
                data = {
                    "leaderboard": leaderboard_data,
                    "total_teams": len(leaderboard_data),
                }
            else:
                # For tournaments leaderboard, order by tournament points
                top_teams = (
                    TeamStatistics.objects.filter(game_name=game_filter).select_related("team")
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
                    "total_teams": TeamStatistics.objects.filter(game_name=game_filter, tournament_position_points__gt=0).count(),
                }
            logger.debug(f"Tournaments leaderboard generated - {len(leaderboard_data)} teams")

        # Cache for 5 minutes
        cache.set(cache_key, data, 300)
        logger.debug(f"Leaderboard cached - Key: {cache_key}")

        return Response(data)


class TeamRankView(generics.GenericAPIView):
    """
    Get specific team's rank and statistics
    GET /api/teams/<team_id>/rank/
    """

    permission_classes = [AllowAny]

    def get(self, request, team_id):
        logger.debug(f"Team rank request - Team ID: {team_id}")

        try:
            # Get aggregate stats (game_name='ALL')
            stats = TeamStatistics.objects.filter(game_name='ALL').select_related("team").get(team_id=team_id)
            serializer = TeamStatisticsSerializer(stats)
            logger.debug(f"Team rank found - Team ID: {team_id}, Rank: {stats.rank}")
            return Response(serializer.data)
        except TeamStatistics.DoesNotExist:
            logger.warning(f"Team statistics not found - Team ID: {team_id}")
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
