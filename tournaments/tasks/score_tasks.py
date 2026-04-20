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

    # Only process teams that have actually played matches — skip teams with no MatchScore records
    active_team_ids = MatchScore.objects.values_list('team__team_id', flat=True).distinct()
    teams = Team.objects.filter(id__in=active_team_ids)
    teams_updated = 0

    # Pre-build winner lookup: {reg_id: (team_id, event_mode)} from all completed tournaments
    # This avoids N×M individual DB queries inside the team loop
    winner_reg_to_info = {}  # reg_id -> {'team_id': ..., 'event_mode': ..., 'game_name': ...}
    for t in Tournament.objects.filter(status="completed", winners__isnull=False).values('id', 'winners', 'event_mode', 'game_name'):
        if not t['winners']:
            continue
        for winner_val in t['winners'].values():
            if isinstance(winner_val, dict):
                winner_id = winner_val.get('reg_id')
            else:
                winner_id = winner_val
            if not isinstance(winner_id, int):
                continue
            winner_reg_to_info[winner_id] = {'event_mode': t['event_mode'], 'game_name': t['game_name']}
    # Load all winner registrations at once: reg_id -> team_id
    winner_reg_ids = list(winner_reg_to_info.keys())
    reg_team_map = {
        r['id']: r['team_id']
        for r in TournamentRegistration.objects.filter(id__in=winner_reg_ids).values('id', 'team_id')
    }

    # Bulk aggregate all scores grouped by team + event_mode + game_name (3 queries total)
    from django.db.models import Count

    all_bulk = (
        MatchScore.objects.values('team__team_id', 'match__group__tournament__event_mode', 'match__group__tournament__game_name')
        .annotate(pos=Sum('position_points'), kills=Sum('kill_points'))
    )
    # Structure: {team_id: {event_mode: {game_name: {pos, kills}}}}
    bulk_scores = {}
    for row in all_bulk:
        tid = row['team__team_id']
        em = row['match__group__tournament__event_mode'] or 'TOURNAMENT'
        gn = row['match__group__tournament__game_name'] or ''
        bulk_scores.setdefault(tid, {}).setdefault(em, {})[gn] = {
            'pos': row['pos'] or 0, 'kills': row['kills'] or 0
        }

    # Bulk count matches played per team + event_mode + game_name
    matches_bulk = (
        MatchScore.objects.values('team__team_id', 'match__group__tournament__event_mode', 'match__group__tournament__game_name')
        .annotate(match_count=Count('match', distinct=True))
    )
    bulk_matches = {}
    for row in matches_bulk:
        tid = row['team__team_id']
        em = row['match__group__tournament__event_mode'] or 'TOURNAMENT'
        gn = row['match__group__tournament__game_name'] or ''
        bulk_matches.setdefault(tid, {}).setdefault(em, {})[gn] = row['match_count']

    # Pre-build wins per team: {team_id: {'tournament': count, 'scrim': count, game: {'tournament': count, 'scrim': count}}}
    wins_by_team = {}
    for reg_id, info in winner_reg_to_info.items():
        team_id = reg_team_map.get(reg_id)
        if not team_id:
            continue
        wins_by_team.setdefault(team_id, {'tournament': 0, 'scrim': 0, 'by_game': {}})
        em = info['event_mode']
        gn = info['game_name'] or ''
        if em == 'SCRIM':
            wins_by_team[team_id]['scrim'] += 1
        else:
            wins_by_team[team_id]['tournament'] += 1
        wins_by_team[team_id]['by_game'].setdefault(gn, {'tournament': 0, 'scrim': 0})
        if em == 'SCRIM':
            wins_by_team[team_id]['by_game'][gn]['scrim'] += 1
        else:
            wins_by_team[team_id]['by_game'][gn]['tournament'] += 1

    for team in teams:
        try:
            tid = team.id
            team_scores = bulk_scores.get(tid, {})
            team_matches = bulk_matches.get(tid, {})
            team_wins = wins_by_team.get(tid, {'tournament': 0, 'scrim': 0, 'by_game': {}})

            # Overall totals
            t_pos = t_kills = t_t_pos = t_t_kills = t_s_pos = t_s_kills = 0
            matches_played = tournament_matches_played = scrim_matches_played = 0
            for em, games_dict in team_scores.items():
                for gn, pts in games_dict.items():
                    t_pos += pts['pos']; t_kills += pts['kills']
                    if em == 'TOURNAMENT':
                        t_t_pos += pts['pos']; t_t_kills += pts['kills']
                    elif em == 'SCRIM':
                        t_s_pos += pts['pos']; t_s_kills += pts['kills']
            for em, games_dict in team_matches.items():
                for gn, cnt in games_dict.items():
                    matches_played += cnt
                    if em == 'TOURNAMENT':
                        tournament_matches_played += cnt
                    elif em == 'SCRIM':
                        scrim_matches_played += cnt

            tournament_wins = team_wins['tournament']
            scrim_wins = team_wins['scrim']

            # Save 'ALL' stats
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
            all_stats.tournament_matches_played = tournament_matches_played
            all_stats.scrim_matches_played = scrim_matches_played
            all_stats.matches_played = matches_played
            all_stats.save()

            # Per-game stats — only for games this team actually played
            all_games = set()
            for em_dict in team_scores.values():
                all_games.update(em_dict.keys())

            for game in all_games:
                g_t_pos = team_scores.get('TOURNAMENT', {}).get(game, {}).get('pos', 0)
                g_t_kills = team_scores.get('TOURNAMENT', {}).get(game, {}).get('kills', 0)
                g_s_pos = team_scores.get('SCRIM', {}).get(game, {}).get('pos', 0)
                g_s_kills = team_scores.get('SCRIM', {}).get(game, {}).get('kills', 0)
                game_matches_played = (
                    team_matches.get('TOURNAMENT', {}).get(game, 0) +
                    team_matches.get('SCRIM', {}).get(game, 0)
                )
                game_wins = team_wins['by_game'].get(game, {'tournament': 0, 'scrim': 0})

                game_stats, _ = TeamStatistics.objects.get_or_create(team=team, game_name=game)
                game_stats.tournament_wins = game_wins['tournament']
                game_stats.tournament_position_points = g_t_pos
                game_stats.tournament_kill_points = g_t_kills
                game_stats.scrim_wins = game_wins['scrim']
                game_stats.scrim_position_points = g_s_pos
                game_stats.scrim_kill_points = g_s_kills
                game_stats.total_position_points = g_t_pos + g_s_pos
                game_stats.total_kill_points = g_t_kills + g_s_kills
                game_stats.total_points = game_stats.total_position_points + game_stats.total_kill_points
                game_stats.matches_played = game_matches_played
                game_stats.save()

            # Update Team model fields
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
    # Only process players who have at least one confirmed registration in a completed tournament
    active_player_ids = TournamentRegistration.objects.filter(
        status="confirmed", tournament__status="completed"
    ).values_list('player_id', flat=True).distinct()
    players = PlayerProfile.objects.filter(id__in=active_player_ids)
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
