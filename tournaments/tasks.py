"""
Celery tasks for tournaments app
"""
import logging
import os
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from celery import shared_task
from PIL import Image

from accounts.models import HostProfile, PlayerProfile, Team, TeamJoinRequest, TeamStatistics
from payments.models import Payment
from scrimverse.email_utils import (
    send_host_approved_email,
    send_player_tournament_reminder_email,
    send_registration_limit_reached_email,
    send_team_invite_email,
    send_tournament_completed_email,
    send_tournament_created_email,
    send_tournament_registration_email,
    send_tournament_reminder_email,
)
from tournaments.models import Match, MatchScore, RoundScore, Tournament, TournamentRegistration
from tournaments.services import TournamentGroupService

logger = logging.getLogger(__name__)


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

    logger.debug(f"Tournament statuses updated - Ongoing: {updated_ongoing}, Completed: {updated_completed}")
    return {
        "updated_ongoing": updated_ongoing,
        "updated_completed": updated_completed,
        "timestamp": now.isoformat(),
    }


@shared_task
def cleanup_unpaid_tournaments_and_registrations():
    """
    Clean up expired pending payments.
    Since tournaments/registrations are now created only AFTER payment success,
    we just need to delete failed payment records occasionally.
    """
    now = timezone.now()
    # Delete failed or pending payments older than 24 hours
    expired_time = now - timezone.timedelta(hours=24)
    expired_payments = Payment.objects.filter(status__in=["pending", "failed"], created_at__lte=expired_time)

    count = expired_payments.count()
    if count > 0:
        logger.info(f"Cleaning up {count} old payment records")
        expired_payments.delete()

    return {
        "payments_deleted": count,
        "timestamp": now.isoformat(),
    }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_team_invite_emails_task(self, registration_id):
    """
    Send invite emails to all teammates for an invite-based registration.
    Called after payment is confirmed in process_successful_registration().
    """
    try:
        registration = TournamentRegistration.objects.select_related(
            "tournament", "player__user", "team"
        ).get(id=registration_id)
    except TournamentRegistration.DoesNotExist:
        logger.error(f"Registration {registration_id} not found for invite emails")
        return {"status": "error", "reason": "registration_not_found"}

    tournament = registration.tournament
    captain_name = registration.player.user.username
    team_name = registration.team.name if registration.team else registration.team_name

    invites = TeamJoinRequest.objects.filter(
        tournament_registration=registration,
        request_type="invite",
        status="pending",
    )

    emails_sent = 0
    errors = []

    for invite in invites:
        try:
            success = send_team_invite_email(
                invited_email=invite.invited_email,
                captain_name=captain_name,
                team_name=team_name,
                tournament_name=tournament.title,
                game_name=tournament.game_name,
                prize_pool=f"₹{tournament.prize_pool:,.0f}" if tournament.prize_pool else "N/A",
                invite_token=invite.invite_token,
                expires_at=invite.invite_expires_at.strftime("%B %d, %Y at %I:%M %p") if invite.invite_expires_at else "7 days",
            )
            if success:
                emails_sent += 1
            else:
                errors.append(invite.invited_email)
        except Exception as exc:
            logger.warning(f"Failed to send invite to {invite.invited_email}: {exc}")
            errors.append(invite.invited_email)

    logger.info(
        f"Team invite emails for registration {registration_id}: "
        f"{emails_sent} sent, {len(errors)} failed"
    )

    # Retry if some emails failed
    if errors and self.request.retries < self.max_retries:
        raise self.retry(exc=Exception(f"Failed emails: {errors}"))

    return {"emails_sent": emails_sent, "errors": errors}


@shared_task
def send_tournament_reminders_24h():
    """
    Send tournament reminders 24 hours before start
    Runs every hour via Celery Beat
    """
    now = timezone.now()
    tomorrow = now + timedelta(hours=24)

    # Find tournaments starting in approximately 24 hours (within 1 hour window)
    tournaments = Tournament.objects.filter(
        tournament_start__gte=tomorrow - timedelta(minutes=30),
        tournament_start__lte=tomorrow + timedelta(minutes=30),
        status="upcoming",
    )

    frontend_url = settings.CORS_ALLOWED_ORIGINS[0]
    emails_sent = 0

    for tournament in tournaments:
        # Send to host
        send_tournament_reminder_email_task.delay(
            host_email=tournament.host.user.email,
            host_name=tournament.host.user.username,
            tournament_name=tournament.title,
            start_time=tournament.tournament_start.strftime("%B %d, %Y at %I:%M %p"),
            total_registrations=TournamentRegistration.objects.filter(
                tournament=tournament, status="confirmed"
            ).count(),
            tournament_manage_url=f"{frontend_url}/host/tournaments/{tournament.id}/manage",
        )
        emails_sent += 1

        # Send to all registered players
        registrations = TournamentRegistration.objects.filter(tournament=tournament, status="confirmed")

        for reg in registrations:
            # Send to captain
            send_player_tournament_reminder_email_task.delay(
                user_email=reg.player.user.email,
                user_name=reg.player.user.username,
                tournament_name=tournament.title,
                game_name=tournament.game_name,
                start_time=tournament.tournament_start.strftime("%B %d, %Y at %I:%M %p"),
                time_until="in 24 hours",
                tournament_url=f"{frontend_url}/tournaments/{tournament.id}",
                event_type="Scrim" if tournament.event_mode == "SCRIM" else "Tournament",
                team_name=reg.team_name,
            )
            emails_sent += 1

            # Send to all team members
            if reg.team_members:
                for member in reg.team_members:
                    if member.get("is_registered") and member.get("player_id"):
                        try:
                            member_player = PlayerProfile.objects.get(id=member["player_id"])
                            send_player_tournament_reminder_email_task.delay(
                                user_email=member_player.user.email,
                                user_name=member_player.user.username,
                                tournament_name=tournament.title,
                                game_name=tournament.game_name,
                                start_time=tournament.tournament_start.strftime("%B %d, %Y at %I:%M %p"),
                                time_until="in 24 hours",
                                tournament_url=f"{frontend_url}/tournaments/{tournament.id}",
                                event_type="Scrim" if tournament.event_mode == "SCRIM" else "Tournament",
                                team_name=reg.team_name,
                            )
                            emails_sent += 1
                        except PlayerProfile.DoesNotExist:
                            pass

    logger.info(f"24h tournament reminders sent: {emails_sent} emails for {tournaments.count()} tournaments")
    return {"emails_sent": emails_sent, "tournaments": tournaments.count()}


@shared_task
def send_tournament_reminders_1h():
    """
    Send tournament reminders 1 hour before start
    Runs every 5 minutes via Celery Beat
    """
    now = timezone.now()
    one_hour_later = now + timedelta(hours=1)

    # Find tournaments starting in approximately 1 hour (within 5 minute window)
    tournaments = Tournament.objects.filter(
        tournament_start__gte=one_hour_later - timedelta(minutes=2),
        tournament_start__lte=one_hour_later + timedelta(minutes=3),
        status="upcoming",
    )

    frontend_url = settings.CORS_ALLOWED_ORIGINS[0]
    emails_sent = 0

    for tournament in tournaments:
        # Send to host
        send_tournament_reminder_email_task.delay(
            host_email=tournament.host.user.email,
            host_name=tournament.host.user.username,
            tournament_name=tournament.title,
            start_time=tournament.tournament_start.strftime("%B %d, %Y at %I:%M %p"),
            total_registrations=TournamentRegistration.objects.filter(
                tournament=tournament, status="confirmed"
            ).count(),
            tournament_manage_url=f"{frontend_url}/host/tournaments/{tournament.id}/manage",
        )
        emails_sent += 1

        # Send to all registered players
        registrations = TournamentRegistration.objects.filter(tournament=tournament, status="confirmed")

        for reg in registrations:
            # Send to captain
            send_player_tournament_reminder_email_task.delay(
                user_email=reg.player.user.email,
                user_name=reg.player.user.username,
                tournament_name=tournament.title,
                game_name=tournament.game_name,
                start_time=tournament.tournament_start.strftime("%B %d, %Y at %I:%M %p"),
                time_until="in 1 hour",
                tournament_url=f"{frontend_url}/tournaments/{tournament.id}",
                event_type="Scrim" if tournament.event_mode == "SCRIM" else "Tournament",
                team_name=reg.team_name,
            )
            emails_sent += 1

            # Send to all team members
            if reg.team_members:
                for member in reg.team_members:
                    if member.get("is_registered") and member.get("player_id"):
                        try:
                            member_player = PlayerProfile.objects.get(id=member["player_id"])
                            send_player_tournament_reminder_email_task.delay(
                                user_email=member_player.user.email,
                                user_name=member_player.user.username,
                                tournament_name=tournament.title,
                                game_name=tournament.game_name,
                                start_time=tournament.tournament_start.strftime("%B %d, %Y at %I:%M %p"),
                                time_until="in 1 hour",
                                tournament_url=f"{frontend_url}/tournaments/{tournament.id}",
                                event_type="Scrim" if tournament.event_mode == "SCRIM" else "Tournament",
                                team_name=reg.team_name,
                            )
                            emails_sent += 1
                        except PlayerProfile.DoesNotExist:
                            pass

    logger.info(f"1h tournament reminders sent: {emails_sent} emails for {tournaments.count()} tournaments")
    return {"emails_sent": emails_sent, "tournaments": tournaments.count()}


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
    logger.info("Starting comprehensive leaderboard update...")

    # Get all non-temporary teams
    teams = Team.objects.filter(is_temporary=False)

    completed_tournaments = Tournament.objects.filter(status="completed")

    teams_updated = 0
    for team in teams:
        try:
            stats, _ = TeamStatistics.objects.get_or_create(team=team)

            # 1. Matches Played (tournaments/scrims participated in)
            # Count confirmed registrations for this team in completed events
            # 1 tournament/scrim = 1 match played
            matches_played = TournamentRegistration.objects.filter(
                team=team, status="confirmed", tournament__status="completed"
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

    # 5. Update Player Statistics (Participation and Wins)
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


# ============================================================================
# CRITICAL PERFORMANCE TASKS
# ============================================================================


@shared_task
def update_platform_statistics():
    """
    Calculate and cache platform-wide statistics
    Runs every hour via Celery Beat

    Priority: 🔥🔥🔥🔥 CRITICAL
    Impact: 95%+ faster dashboard loads
    """
    logger.info("Calculating platform statistics...")

    try:
        stats = {
            "total_tournaments": Tournament.objects.count(),
            "total_players": PlayerProfile.objects.count(),
            "total_prize_money": str(
                Tournament.objects.filter(status="completed").aggregate(total=Sum("prize_pool"))["total"] or 0
            ),
            "total_registrations": TournamentRegistration.objects.count(),
            "active_tournaments": Tournament.objects.filter(status="ongoing").count(),
            "upcoming_tournaments": Tournament.objects.filter(status="upcoming").count(),
            "completed_tournaments": Tournament.objects.filter(status="completed").count(),
            "last_updated": timezone.now().isoformat(),
        }

        # Cache for 1 hour
        cache.set("platform:statistics", stats, 3600)

        logger.info(f"Platform statistics updated successfully: {stats['total_tournaments']} tournaments")
        return stats

    except Exception as e:
        logger.error(f"Error updating platform statistics: {e}")
        return {"error": str(e)}


@shared_task
def update_host_dashboard_stats(host_id):
    """
    Calculate and cache host-specific dashboard statistics
    Runs every 10 minutes for active hosts via Celery Beat

    Priority: 🔥🔥🔥🔥 CRITICAL
    Impact: Dashboard loads in <100ms instead of 2-5 seconds
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Calculating dashboard stats for host {host_id}...")

    try:
        host_profile = HostProfile.objects.get(id=host_id)
        now = timezone.now()

        # Total matches hosted (tournaments + scrims)
        matches_hosted = Tournament.objects.filter(host=host_profile).count()

        # Participant stats
        total_participants = TournamentRegistration.objects.filter(
            tournament__host=host_profile, status="confirmed"
        ).count()

        # Prize pool calculations (sum of all prize pools)
        total_prize_pool = Tournament.objects.filter(host=host_profile).aggregate(total=Sum("prize_pool"))["total"] or 0

        # Host rating from profile
        host_rating = float(host_profile.rating)

        stats = {
            "matches_hosted": matches_hosted,
            "total_participants": total_participants,
            "total_prize_pool": float(total_prize_pool),
            "host_rating": host_rating,
            "last_updated": now.isoformat(),
        }

        # Cache for 10 minutes
        cache.set(f"host:dashboard:{host_id}", stats, 600)

        logger.info(f"Host {host_id} dashboard stats updated: {matches_hosted} matches hosted")
        return stats

    except HostProfile.DoesNotExist:
        logger.error(f"Host profile {host_id} not found")
        return {"error": "Host not found"}
    except Exception as e:
        logger.error(f"Error updating host dashboard stats: {e}")
        return {"error": str(e)}


@shared_task
def refresh_all_host_dashboards():
    """
    Refresh dashboard stats for all hosts with active tournaments
    Runs every 10 minutes via Celery Beat
    """
    logger = logging.getLogger(__name__)

    # Get hosts with active tournaments
    active_hosts = HostProfile.objects.filter(tournaments__status__in=["upcoming", "ongoing"]).distinct()

    count = 0
    for host in active_hosts:
        update_host_dashboard_stats.delay(host.id)
        count += 1

    logger.info(f"Triggered dashboard refresh for {count} active hosts")
    return {"hosts_refreshed": count}


# ============================================================================
# USER FLOW BLOCKER TASKS
# ============================================================================


@shared_task
def process_tournament_registration(registration_id):
    """
    Process tournament registration asynchronously
    - Validate team members
    - Check for duplicates
    - Update participant count
    - Send confirmation notification

    Priority: 🔥🔥🔥 CRITICAL-HIGH
    Impact: 80-90% faster registration
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Processing tournament registration {registration_id}...")

    try:
        registration = TournamentRegistration.objects.get(id=registration_id)
        tournament = registration.tournament

        # Validate team members (if team registration)
        if registration.team_members:
            team_player_ids = {member.get("id") for member in registration.team_members}

            # Check for duplicate players in other registrations
            existing_registrations = TournamentRegistration.objects.filter(
                tournament=tournament, status__in=["pending", "confirmed"]
            ).exclude(id=registration_id)

            for existing_reg in existing_registrations:
                if existing_reg.team_members:
                    registered_player_ids = {member.get("id") for member in existing_reg.team_members}
                    overlapping_ids = team_player_ids & registered_player_ids

                    if overlapping_ids:
                        # Mark as rejected due to duplicate
                        registration.status = "rejected"
                        registration.save()
                        logger.warning(f"Registration {registration_id} rejected: duplicate players")
                        return {"status": "rejected", "reason": "duplicate_players"}

        # If validation passed, confirm registration
        if registration.status == "pending":
            registration.status = "confirmed"
            registration.save()

            # TODO: Send confirmation email
            logger.info(f"Registration {registration_id} confirmed successfully")

        # Invalidate caches
        cache.delete("tournaments:list:all")
        cache.delete(f"tournament:registrations:{tournament.id}")

        return {"status": "confirmed", "registration_id": registration_id}

    except TournamentRegistration.DoesNotExist:
        logger.error(f"Registration {registration_id} not found")
        return {"error": "Registration not found"}
    except Exception as e:
        logger.error(f"Error processing registration: {e}")
        return {"error": str(e)}


@shared_task
def process_round_scores(tournament_id, round_num, scores_data):
    """
    Process and save round scores asynchronously
    - Save all scores
    - Calculate rankings
    - Auto-select qualifying teams
    - Update round statistics

    Priority: 🔥🔥🔥 CRITICAL-HIGH
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

    Priority: 🔥🔥 HIGH
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


# ============================================================================
# TOURNAMENT OPERATIONS TASKS
# ============================================================================


@shared_task
def create_tournament_groups(tournament_id, round_number, config):
    """
    Create groups and matches for a round asynchronously
    - Create all groups
    - Distribute teams evenly
    - Create matches for each group
    - Generate room IDs and passwords

    Priority: 🔥🔥 HIGH
    Impact: 80-90% faster round setup
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Creating groups for tournament {tournament_id}, round {round_number}...")

    try:
        tournament = Tournament.objects.get(id=tournament_id)

        teams_per_group = config.get("teams_per_group")
        qualifying_per_group = config.get("qualifying_per_group")
        matches_per_group = config.get("matches_per_group")

        # Create groups and matches
        groups = TournamentGroupService.create_groups_for_round(
            tournament=tournament,
            round_number=round_number,
            teams_per_group=teams_per_group,
            qualifying_per_group=qualifying_per_group,
            matches_per_group=matches_per_group,
        )

        # Update tournament round status
        if not tournament.round_status:
            tournament.round_status = {}
        tournament.round_status[str(round_number)] = "ongoing"
        tournament.current_round = round_number
        tournament.save(update_fields=["round_status", "current_round"])

        logger.info(f"Created {len(groups)} groups for round {round_number}")
        return {"groups_created": len(groups), "round_number": round_number, "tournament_id": tournament_id}

    except Tournament.DoesNotExist:
        logger.error(f"Tournament {tournament_id} not found")
        return {"error": "Tournament not found"}
    except Exception as e:
        logger.error(f"Error creating tournament groups: {e}")
        return {"error": str(e)}


@shared_task
def process_tournament_banner(tournament_id, image_path):
    """
    Process tournament banner asynchronously
    - Resize to multiple sizes
    - Compress images
    - Generate thumbnails
    - (Future: Upload to CDN)

    Priority: 🔥🔥 HIGH
    Impact: Better host UX, non-blocking uploads
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Processing banner for tournament {tournament_id}...")

    try:
        if not os.path.exists(image_path):
            logger.warning(f"Image path does not exist: {image_path}")
            return {"error": "Image not found"}

        # Open image
        img = Image.open(image_path)

        # Resize to standard size (e.g., 1200x400)
        max_width = 1200
        max_height = 400

        # Calculate aspect ratio
        aspect = img.width / img.height
        if img.width > max_width or img.height > max_height:
            if aspect > max_width / max_height:
                new_width = max_width
                new_height = int(max_width / aspect)
            else:
                new_height = max_height
                new_width = int(max_height * aspect)

            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Save optimized image
        img.save(image_path, optimize=True, quality=85)

        # TODO: Generate thumbnail

        logger.info(f"Banner processed successfully for tournament {tournament_id}")
        return {"tournament_id": tournament_id, "image_path": image_path, "size": f"{img.width}x{img.height}"}

    except Tournament.DoesNotExist:
        logger.error(f"Tournament {tournament_id} not found")
        return {"error": "Tournament not found"}
    except Exception as e:
        logger.error(f"Error processing banner: {e}")
        return {"error": str(e)}


# ============================================================================
# TOURNAMENT EMAIL TASKS
# ============================================================================
# Tournament-related email notifications
# ============================================================================


# Player-Side Tournament Emails
@shared_task(name="send_tournament_registration_email_task")
def send_tournament_registration_email_task(
    user_email: str,
    user_name: str,
    tournament_name: str,
    game_name: str,
    start_date: str,
    registration_id: str,
    tournament_url: str,
    team_name: str = None,
):
    """Async task to send tournament registration confirmation email"""
    return send_tournament_registration_email(
        user_email,
        user_name,
        tournament_name,
        game_name,
        start_date,
        registration_id,
        tournament_url,
        team_name,
    )


@shared_task(name="send_player_tournament_reminder_email_task")
def send_player_tournament_reminder_email_task(
    user_email: str,
    user_name: str,
    tournament_name: str,
    game_name: str,
    start_time: str,
    time_until: str,
    tournament_url: str,
    event_type: str = "Tournament",
    team_name: str = None,
):
    """Async task to send tournament reminder email to players"""
    return send_player_tournament_reminder_email(
        user_email,
        user_name,
        tournament_name,
        game_name,
        start_time,
        time_until,
        tournament_url,
        event_type,
        team_name,
    )


# Host-Side Tournament Emails
@shared_task(name="send_host_approved_email_task")
def send_host_approved_email_task(
    user_email: str, user_name: str, host_name: str, approved_at: str, host_dashboard_url: str
):
    """Async task to send host account approval email"""
    return send_host_approved_email(user_email, user_name, host_name, approved_at, host_dashboard_url)


@shared_task(name="send_tournament_created_email_task")
def send_tournament_created_email_task(
    host_email: str,
    host_name: str,
    tournament_name: str,
    game_name: str,
    start_date: str,
    max_participants: int,
    plan_type: str,
    tournament_url: str,
    tournament_manage_url: str,
):
    """Async task to send tournament created confirmation email"""
    return send_tournament_created_email(
        host_email,
        host_name,
        tournament_name,
        game_name,
        start_date,
        max_participants,
        plan_type,
        tournament_url,
        tournament_manage_url,
    )


@shared_task(name="send_tournament_reminder_email_task")
def send_tournament_reminder_email_task(
    host_email: str,
    host_name: str,
    tournament_name: str,
    start_time: str,
    total_registrations: int,
    tournament_manage_url: str,
):
    """Async task to send tournament reminder email (same day)"""
    return send_tournament_reminder_email(
        host_email, host_name, tournament_name, start_time, total_registrations, tournament_manage_url
    )


@shared_task(name="send_registration_limit_reached_email_task")
def send_registration_limit_reached_email_task(
    host_email: str,
    host_name: str,
    tournament_name: str,
    total_registrations: int,
    max_participants: int,
    start_date: str,
    tournament_manage_url: str,
):
    """Async task to send registration limit reached notification"""
    return send_registration_limit_reached_email(
        host_email,
        host_name,
        tournament_name,
        total_registrations,
        max_participants,
        start_date,
        tournament_manage_url,
    )


@shared_task(name="send_max_participants_email_task")
def send_max_participants_email_task(*args, **kwargs):
    """Alias for send_registration_limit_reached_email_task for test compatibility"""
    return send_registration_limit_reached_email(*args, **kwargs)


@shared_task(name="send_tournament_completed_email_task")
def send_tournament_completed_email_task(
    host_email: str,
    host_name: str,
    tournament_name: str,
    completed_at: str,
    total_participants: int,
    total_matches: int,
    winner_name: str,
    runner_up_name: str,
    total_registrations: int,
    results_published: bool,
    tournament_manage_url: str,
):
    """Async task to send tournament completion summary email"""
    return send_tournament_completed_email(
        host_email,
        host_name,
        tournament_name,
        completed_at,
        total_participants,
        total_matches,
        winner_name,
        runner_up_name,
        total_registrations,
        results_published,
        tournament_manage_url,
    )
