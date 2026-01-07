"""
Celery tasks for tournaments app
"""
import logging

from django.core.cache import cache
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from celery import shared_task

from accounts.models import Team, TeamStatistics

from .models import MatchScore, Tournament, TournamentRegistration


@shared_task
def update_tournament_statuses():
    """
    Update tournament statuses based on current time
    Runs every minute via Celery Beat
    """
    now = timezone.now()

    # Update to ongoing
    updated_ongoing = Tournament.objects.filter(
        tournament_start__lte=now, tournament_end__gt=now, status="upcoming"
    ).update(status="ongoing")

    # Update to completed
    updated_completed = Tournament.objects.filter(tournament_end__lte=now, status__in=["upcoming", "ongoing"]).update(
        status="completed"
    )

    # Clear cache if any updates occurred
    if updated_ongoing > 0 or updated_completed > 0:
        cache.delete("tournaments:list:all")

    return {
        "updated_ongoing": updated_ongoing,
        "updated_completed": updated_completed,
        "timestamp": now.isoformat(),
    }


@shared_task
def update_leaderboard():
    """
    Update team leaderboard statistics
    Calculates:
    - Tournament wins/points/rank
    - Scrim wins/points/rank
    - Overall rank
    - Total matches played (only from completed events)
    """
    logger = logging.getLogger(__name__)
    logger.info("Starting comprehensive leaderboard update...")

    # Get all non-temporary teams
    teams = Team.objects.filter(is_temporary=False)

    completed_tournaments = Tournament.objects.filter(status="completed")

    teams_updated = 0
    for team in teams:
        try:
            stats, _ = TeamStatistics.objects.get_or_create(team=team)

            # 1. Matches Played (from completed events)
            # Individual matches played by this team in completed tournaments/scrims
            matches_played = MatchScore.objects.filter(
                team__team=team, match__group__tournament__status="completed"
            ).count()

            # 2. Wins Calculation
            tournament_wins = 0
            scrim_wins = 0

            for tournament in completed_tournaments:
                if tournament.winners:
                    # Check each round's winner (usually only final round matters for 'wins')
                    # If it's a scrim, usually only 1 winner
                    # If it's a tournament, we look for the winner of the final round
                    final_round = str(len(tournament.rounds)) if tournament.rounds else "1"
                    winner_reg_id = tournament.winners.get(final_round)

                    if winner_reg_id:
                        try:
                            winner_reg = TournamentRegistration.objects.get(id=winner_reg_id)
                            if winner_reg.team and winner_reg.team.id == team.id:
                                if tournament.event_mode == "SCRIM":
                                    scrim_wins += 1
                                else:
                                    tournament_wins += 1
                        except TournamentRegistration.DoesNotExist:
                            pass

            # 3. Points Calculation
            # Tournament Points
            t_scores = MatchScore.objects.filter(
                team__team=team, match__group__tournament__event_mode="TOURNAMENT"
            ).aggregate(pos=Sum("position_points"), kills=Sum("kill_points"))

            # Scrim Points
            s_scores = MatchScore.objects.filter(
                team__team=team, match__group__tournament__event_mode="SCRIM"
            ).aggregate(pos=Sum("position_points"), kills=Sum("kill_points"))

            # Update stats object
            stats.tournament_wins = tournament_wins
            stats.tournament_position_points = t_scores["pos"] or 0
            stats.tournament_kill_points = t_scores["kills"] or 0

            stats.scrim_wins = scrim_wins
            stats.scrim_position_points = s_scores["pos"] or 0
            stats.scrim_kill_points = s_scores["kills"] or 0

            # Aggregate for overall
            stats.total_position_points = stats.tournament_position_points + stats.scrim_position_points
            stats.total_kill_points = stats.tournament_kill_points + stats.scrim_kill_points
            stats.total_points = stats.total_position_points + stats.total_kill_points
            stats.save()

            # Update Team model field for matches_played/wins
            team.total_matches = matches_played
            team.wins = tournament_wins + scrim_wins
            team.save(update_fields=["total_matches", "wins"])

            teams_updated += 1
        except Exception as e:
            logger.error(f"Error updating stats for team {team.name}: {e}")
            continue

    # 4. Assign Ranks
    with transaction.atomic():
        # Overall Rank
        overall_stats = TeamStatistics.objects.all().order_by("-total_points", "-tournament_wins", "-scrim_wins")
        for idx, s in enumerate(overall_stats, 1):
            s.rank = idx
            s.save(update_fields=["rank"])

        # Tournament Rank
        t_stats = TeamStatistics.objects.annotate(
            t_total=F("tournament_position_points") + F("tournament_kill_points")
        ).order_by("-t_total", "-tournament_wins", "-tournament_kill_points")
        for idx, s in enumerate(t_stats, 1):
            s.tournament_rank = idx
            s.save(update_fields=["tournament_rank"])

        # Scrim Rank
        s_stats = TeamStatistics.objects.annotate(s_total=F("scrim_position_points") + F("scrim_kill_points")).order_by(
            "-s_total", "-scrim_wins", "-scrim_kill_points"
        )
        for idx, s in enumerate(s_stats, 1):
            s.scrim_rank = idx
            s.save(update_fields=["scrim_rank"])

    # Clear cache
    cache.delete_pattern("leaderboard:*")

    logger.info(f"Updated {teams_updated} teams statistics and ranks.")
    return {"teams_updated": teams_updated, "timestamp": timezone.now().isoformat()}
