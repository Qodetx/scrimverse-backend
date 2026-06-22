"""
Leaderboard API views
"""
import logging

from django.core.cache import cache
from django.db.models import F, Q, Sum

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
                # Use the pre-aggregated 'ALL' rows directly
                top_teams = (
                    TeamStatistics.objects.filter(game_name='ALL').select_related('team')
                    .filter(Q(scrim_position_points__gt=0) | Q(scrim_kill_points__gt=0) | Q(scrim_wins__gt=0))
                    .annotate(scrim_total=F('scrim_position_points') + F('scrim_kill_points'))
                    .order_by('-scrim_total', '-scrim_wins', '-scrim_kill_points')[:limit]
                )
                leaderboard_data = []
                for rank, stats in enumerate(top_teams, start=1):
                    data = TeamStatisticsSerializer(stats).data
                    data["rank"] = rank
                    data["scrim_wins"] = stats.scrim_wins
                    data["total_points"] = stats.scrim_position_points + stats.scrim_kill_points
                    data["total_position_points"] = stats.scrim_position_points
                    data["total_kill_points"] = stats.scrim_kill_points
                    data["matches_played"] = stats.matches_played
                    data["tournament_matches_played"] = stats.tournament_matches_played
                    data["scrim_matches_played"] = stats.scrim_matches_played
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
                    data["matches_played"] = stats.matches_played
                    leaderboard_data.append(data)

                data = {
                    "leaderboard": leaderboard_data,
                    "total_teams": TeamStatistics.objects.filter(game_name=game_filter, scrim_position_points__gt=0).count(),
                }
            logger.debug(f"Scrims leaderboard generated - {len(leaderboard_data)} teams")
        else:
            if game_filter == 'ALL':
                # Use the pre-aggregated 'ALL' rows directly (these are already aggregated by update_leaderboard task)
                top_teams = (
                    TeamStatistics.objects.filter(game_name='ALL').select_related('team')
                    .filter(Q(tournament_position_points__gt=0) | Q(tournament_kill_points__gt=0) | Q(tournament_wins__gt=0))
                    .annotate(tournament_total=F('tournament_position_points') + F('tournament_kill_points'))
                    .order_by('-tournament_total', '-tournament_wins', '-tournament_kill_points')[:limit]
                )
                leaderboard_data = []
                for rank, stats in enumerate(top_teams, start=1):
                    data = TeamStatisticsSerializer(stats).data
                    data["rank"] = rank
                    data["tournament_wins"] = stats.tournament_wins
                    data["total_points"] = stats.tournament_position_points + stats.tournament_kill_points
                    data["total_position_points"] = stats.tournament_position_points
                    data["total_kill_points"] = stats.tournament_kill_points
                    data["matches_played"] = stats.matches_played
                    data["tournament_matches_played"] = stats.tournament_matches_played
                    data["scrim_matches_played"] = stats.scrim_matches_played
                    leaderboard_data.append(data)
                data = {
                    "leaderboard": leaderboard_data,
                    "total_teams": len(leaderboard_data),
                }
            else:
                # For tournaments leaderboard, order by wins first for 5v5 games (Valorant/COD),
                # otherwise order by points
                WINS_ONLY_GAMES = ['Valorant', 'COD']
                if game_filter in WINS_ONLY_GAMES:
                    top_teams = (
                        TeamStatistics.objects.filter(game_name=game_filter).select_related("team")
                        .filter(tournament_wins__gt=0)
                        .order_by("-tournament_wins")[:limit]
                    )
                else:
                    top_teams = (
                        TeamStatistics.objects.filter(game_name=game_filter).select_related("team")
                        .annotate(tournament_total=F("tournament_position_points") + F("tournament_kill_points"))
                        .filter(Q(tournament_total__gt=0) | Q(tournament_wins__gt=0))
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
                    data["matches_played"] = stats.matches_played
                    leaderboard_data.append(data)

                if game_filter in WINS_ONLY_GAMES:
                    total_teams_count = TeamStatistics.objects.filter(
                        game_name=game_filter, tournament_wins__gt=0
                    ).count()
                else:
                    total_teams_count = TeamStatistics.objects.filter(
                        game_name=game_filter
                    ).annotate(t_total=F("tournament_position_points") + F("tournament_kill_points")).filter(
                        Q(t_total__gt=0) | Q(tournament_wins__gt=0)
                    ).count()

                data = {
                    "leaderboard": leaderboard_data,
                    "total_teams": total_teams_count,
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
