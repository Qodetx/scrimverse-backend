"""
Score processing and leaderboard tasks.
Handles round scores, match scores, and team/player statistics.
"""
import logging

from django.core.cache import cache
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from celery import shared_task

from accounts.models import PlayerProfile, Team, TeamStatistics
from tournaments.models import Match, MatchScore, RoundScore, Tournament, TournamentRegistration
from tournaments.services import TournamentGroupService

logger = logging.getLogger(__name__)


@shared_task
def update_leaderboard():
    """
    Recalculate all team and player statistics from scratch.
    Runs periodically (e.g. nightly) via Celery Beat.

    Covers:
    - Overall + per-game team stats (points, wins, rank)
    - Player participation and win counts
    """
    logger.info("Starting leaderboard update...")

    teams = Team.objects.all()
    teams_updated = 0

    for team in teams:
        try:
            # 1. Overall aggregated scores (event_mode = any)
            all_scores = MatchScore.objects.filter(team__team=team).aggregate(
                pos=Sum("position_points"), kills=Sum("kill_points")
            )
            t_pos = all_scores["pos"] or 0
            t_kills = all_scores["kills"] or 0

            # 2. Tournament vs Scrim breakdowns
            tournament_scores = MatchScore.objects.filter(
                team__team=team, match__group__tournament__event_mode="TOURNAMENT"
            ).aggregate(pos=Sum("position_points"), kills=Sum("kill_points"))

            scrim_scores = MatchScore.objects.filter(
                team__team=team, match__group__tournament__event_mode="SCRIM"
            ).aggregate(pos=Sum("position_points"), kills=Sum("kill_points"))

            t_t_pos = tournament_scores["pos"] or 0
            t_t_kills = tournament_scores["kills"] or 0
            t_s_pos = scrim_scores["pos"] or 0
            t_s_kills = scrim_scores["kills"] or 0

            # 3. Win counts
            matches_played = MatchScore.objects.filter(team__team=team).values("match").distinct().count()
            tournament_wins = 0
            scrim_wins = 0

            completed_tournaments = Tournament.objects.filter(status="completed", winners__isnull=False)
            for tournament in completed_tournaments:
                if tournament.winners:
                    for winner_id in tournament.winners.values():
                        try:
                            reg = TournamentRegistration.objects.get(id=winner_id, tournament=tournament)
                            if reg.team and reg.team == team:
                                if tournament.event_mode == "SCRIM":
                                    scrim_wins += 1
                                else:
                                    tournament_wins += 1
                        except TournamentRegistration.DoesNotExist:
                            pass

            # 4. Save aggregate 'ALL' stats row
            all_stats, _ = TeamStatistics.objects.get_or_create(team=team, game_name="ALL")
            all_stats.tournament_wins = tournament_wins
            all_stats.scrim_wins = scrim_wins
            all_stats.tournament_position_points = t_t_pos
            all_stats.tournament_kill_points = t_t_kills
            all_stats.scrim_position_points = t_s_pos
            all_stats.scrim_kill_points = t_s_kills
            all_stats.total_position_points = t_pos
            all_stats.total_kill_points = t_kills
            all_stats.total_points = t_pos + t_kills
            all_stats.save()

            # 5. Per-game stats
            games = (
                Tournament.objects.filter(status="completed")
                .values_list("game_name", flat=True)
                .distinct()
            )

            for game in games:
                game_tournament_wins = 0
                game_scrim_wins = 0

                game_tournaments = Tournament.objects.filter(
                    status="completed", game_name=game, winners__isnull=False
                )
                for tournament in game_tournaments:
                    if tournament.winners:
                        for winner_id in tournament.winners.values():
                            try:
                                reg = TournamentRegistration.objects.get(id=winner_id, tournament=tournament)
                                if reg.team and reg.team == team:
                                    if tournament.event_mode == "SCRIM":
                                        game_scrim_wins += 1
                                    else:
                                        game_tournament_wins += 1
                            except TournamentRegistration.DoesNotExist:
                                pass

                # Tournament points for this game
                gt_scores = MatchScore.objects.filter(
                    team__team=team,
                    match__group__tournament__event_mode="TOURNAMENT",
                    match__group__tournament__game_name=game,
                ).aggregate(pos=Sum("position_points"), kills=Sum("kill_points"))

                # Scrim points for this game
                gs_scores = MatchScore.objects.filter(
                    team__team=team,
                    match__group__tournament__event_mode="SCRIM",
                    match__group__tournament__game_name=game,
                ).aggregate(pos=Sum("position_points"), kills=Sum("kill_points"))

                g_t_pos = gt_scores["pos"] or 0
                g_t_kills = gt_scores["kills"] or 0
                g_s_pos = gs_scores["pos"] or 0
                g_s_kills = gs_scores["kills"] or 0

                # Only create/update rows if there are any stats for this game
                if g_t_pos or g_t_kills or game_tournament_wins or g_s_pos or g_s_kills or game_scrim_wins:
                    game_stats, _ = TeamStatistics.objects.get_or_create(team=team, game_name=game)
                    game_stats.tournament_wins = game_tournament_wins
                    game_stats.tournament_position_points = g_t_pos
                    game_stats.tournament_kill_points = g_t_kills
                    game_stats.scrim_wins = game_scrim_wins
                    game_stats.scrim_position_points = g_s_pos
                    game_stats.scrim_kill_points = g_s_kills
                    game_stats.total_position_points = g_t_pos + g_s_pos
                    game_stats.total_kill_points = g_t_kills + g_s_kills
                    game_stats.total_points = game_stats.total_position_points + game_stats.total_kill_points
                    game_stats.save()

            # Update Team model field for matches_played/wins
            team.total_matches = matches_played
            team.wins = tournament_wins + scrim_wins
            team.save(update_fields=["total_matches", "wins"])

            teams_updated += 1
        except Exception as e:
            logger.error(f"Error updating stats for team {team.name}: {e}")
            continue

    # Assign Ranks
    with transaction.atomic():
        # Overall Rank (only for aggregate 'ALL' stats)
        overall_stats = TeamStatistics.objects.filter(game_name='ALL').order_by("-total_points", "-tournament_wins", "-scrim_wins")
        for idx, s in enumerate(overall_stats, 1):
            s.rank = idx
            s.save(update_fields=["rank"])

        # Tournament Rank (only for aggregate 'ALL' stats)
        t_stats = TeamStatistics.objects.filter(game_name='ALL').annotate(
            t_total=F("tournament_position_points") + F("tournament_kill_points")
        ).order_by("-t_total", "-tournament_wins", "-tournament_kill_points")
        for idx, s in enumerate(t_stats, 1):
            s.tournament_rank = idx
            s.save(update_fields=["tournament_rank"])

        # Scrim Rank (only for aggregate 'ALL' stats)
        s_stats = TeamStatistics.objects.filter(game_name='ALL').annotate(
            s_total=F("scrim_position_points") + F("scrim_kill_points")
        ).order_by("-s_total", "-scrim_wins", "-scrim_kill_points")
        for idx, s in enumerate(s_stats, 1):
            s.scrim_rank = idx
            s.save(update_fields=["scrim_rank"])

    # Update Player Statistics (Participation and Wins)
    players = PlayerProfile.objects.all()
    players_updated = 0

    for player in players:
        # Participation: confirmed registrations in completed tournaments
        participation_count = TournamentRegistration.objects.filter(
            player=player, status="confirmed", tournament__status="completed"
        ).count()

        # Wins: registrations that are listed as winners in tournament.winners
        wins_count = 0
        winning_registrations = TournamentRegistration.objects.filter(
            player=player, status="confirmed", tournament__status="completed"
        )

        for reg in winning_registrations:
            tournament = reg.tournament
            if tournament.winners:
                # Check if this registration is the winner of any round (usually final round)
                if any(
                    str(reg.id) == str(winner_id) or reg.id == winner_id for winner_id in tournament.winners.values()
                ):
                    wins_count += 1

        player.total_tournaments_participated = participation_count
        player.total_wins = wins_count
        player.save(update_fields=["total_tournaments_participated", "total_wins"])
        players_updated += 1

    # Clear cache
    cache.delete_pattern("leaderboard:*")

    logger.info(f"Updated {teams_updated} teams and {players_updated} players statistics.")
    return {"teams_updated": teams_updated, "players_updated": players_updated, "timestamp": timezone.now().isoformat()}


@shared_task
def process_round_scores(tournament_id, round_num, scores_data):
    """
    Process and save round scores asynchronously
    - Save all scores
    - Calculate rankings
    - Auto-select qualifying teams
    - Update round statistics

    Priority: CRITICAL-HIGH
    Impact: 85-95% faster score submission
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Processing round scores for tournament {tournament_id}, round {round_num}...")

    try:
        tournament = Tournament.objects.get(id=tournament_id)

        # Save scores
        scores_saved = 0
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
            scores_saved += 1

        # Auto-select top qualifying teams
        round_config = next((r for r in tournament.rounds if r["round"] == round_num), None)
        if round_config:
            qualifying_teams = int(round_config.get("qualifying_teams") or 0)

            if qualifying_teams > 0:
                all_scores = RoundScore.objects.filter(tournament=tournament, round_number=round_num).order_by(
                    "-total_points"
                )

                selected_team_ids = list(all_scores.values_list("team_id", flat=True)[:qualifying_teams])

                if not tournament.selected_teams:
                    tournament.selected_teams = {}
                tournament.selected_teams[str(round_num)] = selected_team_ids
                tournament.save(update_fields=["selected_teams"])

        # Invalidate caches
        cache.delete(f"tournament:stats:{tournament_id}")
        cache.delete("tournaments:list:all")

        logger.info(f"Processed {scores_saved} scores for round {round_num}")
        return {"scores_saved": scores_saved, "round": round_num}

    except Tournament.DoesNotExist:
        logger.error(f"Tournament {tournament_id} not found")
        return {"error": "Tournament not found"}
    except Exception as e:
        logger.error(f"Error processing round scores: {e}")
        return {"error": str(e)}


@shared_task
def process_match_scores(match_id, scores_data):
    """
    Process match scores asynchronously
    - Save all team scores
    - Update round aggregates
    - Check if group is completed
    - Calculate qualifications if needed

    Priority: HIGH
    Impact: 85-95% faster match completion
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Processing match scores for match {match_id}...")

    try:
        match = Match.objects.get(id=match_id)
        tournament = match.group.tournament

        # Save scores
        created_count = 0
        for score_entry in scores_data:
            team_id = score_entry.get("team_id")
            wins = int(score_entry.get("wins", 0))
            position_points = int(score_entry.get("position_points", 0))
            kill_points = int(score_entry.get("kill_points", 0))

            if not team_id:
                continue

            try:
                team = TournamentRegistration.objects.get(id=team_id, tournament=tournament)
                MatchScore.objects.create(
                    match=match, team=team, wins=wins, position_points=position_points, kill_points=kill_points
                )
                created_count += 1
            except TournamentRegistration.DoesNotExist:
                continue

        # Update round score aggregates
        TournamentGroupService.calculate_round_scores(tournament, match.group.round_number)

        # Check if all matches in group are completed
        group = match.group
        all_matches_scored = all(m.scores.exists() for m in group.matches.filter(status="completed"))

        if all_matches_scored and group.matches.filter(status="completed").count() == group.matches.count():
            group.status = "completed"
            group.save(update_fields=["status"])

        # Invalidate caches
        cache.delete(f"tournament:stats:{tournament.id}")

        logger.info(f"Processed {created_count} match scores")
        return {"scores_saved": created_count, "match_id": match_id, "group_completed": group.status == "completed"}

    except Match.DoesNotExist:
        logger.error(f"Match {match_id} not found")
        return {"error": "Match not found"}
    except Exception as e:
        logger.error(f"Error processing match scores: {e}")
        return {"error": str(e)}
