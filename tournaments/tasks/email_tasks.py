"""
Email notification tasks for tournaments.
Includes reminder scheduling tasks and thin wrappers around scrimverse.email_utils functions.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from celery import shared_task

from accounts.models import Notification, Team, TeamJoinRequest
from scrimverse.email_utils import (
    send_host_approved_email,
    send_host_rejected_email,
    send_player_tournament_reminder_email,
    send_registration_limit_reached_email,
    send_team_invite_email,
    send_tournament_completed_email,
    send_tournament_created_email,
    send_tournament_registration_email,
    send_tournament_reminder_email,
)
from tournaments.models import Tournament, TournamentRegistration

logger = logging.getLogger(__name__)


# ============================================================================
# TEAM INVITE EMAILS
# ============================================================================


@shared_task
def send_team_invite_emails_task(team_id):
    """
    Send invite emails to all pending team join requests for a team.
    Triggered when a team is created with invited members.
    """
    logger.info(f"Sending team invite emails for team {team_id}...")

    try:
        team = Team.objects.get(id=team_id)
        pending_requests = TeamJoinRequest.objects.filter(team=team, status="pending")

        emails_sent = 0
        frontend_url = settings.CORS_ALLOWED_ORIGINS[0]

        for join_request in pending_requests:
            try:
                invite_url = f"{frontend_url}/teams/invite/{join_request.invite_token}"
                send_team_invite_email(
                    invitee_email=join_request.invitee_email,
                    invitee_name=join_request.invitee_name or join_request.invitee_email.split("@")[0],
                    team_name=team.name,
                    captain_name=team.captain.username,
                    invite_url=invite_url,
                )
                emails_sent += 1
                logger.info(f"Team invite email sent to {join_request.invitee_email}")
            except Exception as e:
                logger.error(f"Failed to send invite email to {join_request.invitee_email}: {e}")

        logger.info(f"Sent {emails_sent} team invite emails for team {team_id}")
        return {"emails_sent": emails_sent, "team_id": team_id}

    except Team.DoesNotExist:
        logger.error(f"Team {team_id} not found")
        return {"error": "Team not found"}
    except Exception as e:
        logger.error(f"Error sending team invite emails: {e}")
        return {"error": str(e)}


# ============================================================================
# TOURNAMENT REMINDER SCHEDULING TASKS
# ============================================================================


@shared_task
def send_tournament_reminders_24h():
    """
    Send 24-hour reminder emails to hosts and registered players.
    Runs every hour via Celery Beat; finds tournaments starting in ~24h.
    """
    now = timezone.now()
    window_start = now + timedelta(hours=23)
    window_end = now + timedelta(hours=25)

    tournaments = Tournament.objects.filter(
        tournament_start__gte=window_start,
        tournament_start__lte=window_end,
        status="upcoming",
    )

    reminders_sent = 0
    frontend_url = settings.CORS_ALLOWED_ORIGINS[0]

    for tournament in tournaments:
        try:
            # Host reminder
            host = tournament.host
            tournament_manage_url = f"{frontend_url}/host/tournaments/{tournament.id}/manage"
            total_registrations = TournamentRegistration.objects.filter(
                tournament=tournament, status="confirmed"
            ).count()
            start_time = tournament.tournament_start.strftime("%B %d, %Y at %I:%M %p")

            send_tournament_reminder_email(
                host_email=host.user.email,
                host_name=host.user.username,
                tournament_name=tournament.title,
                start_time=start_time,
                total_registrations=total_registrations,
                tournament_manage_url=tournament_manage_url,
            )
            reminders_sent += 1

            # Player reminders
            tournament_url = f"{frontend_url}/tournaments/{tournament.id}"
            registrations = TournamentRegistration.objects.filter(tournament=tournament, status="confirmed")
            event_type = "Scrim" if tournament.event_mode == "SCRIM" else "Tournament"

            for reg in registrations:
                try:
                    player = reg.player
                    send_player_tournament_reminder_email(
                        user_email=player.user.email,
                        user_name=player.user.username,
                        tournament_name=tournament.title,
                        game_name=tournament.game_name,
                        start_time=start_time,
                        time_until="24 hours",
                        tournament_url=tournament_url,
                        event_type=event_type,
                        team_name=reg.team_name,
                    )
                    reminders_sent += 1
                except Exception as e:
                    logger.error(f"Failed to send player reminder for reg {reg.id}: {e}")

        except Exception as e:
            logger.error(f"Error sending 24h reminders for tournament {tournament.id}: {e}")

    logger.info(f"Sent {reminders_sent} 24h reminder emails")
    return {"reminders_sent": reminders_sent}


@shared_task
def send_tournament_reminders_1h():
    """
    Send 1-hour reminder emails to registered players.
    Runs every 15 minutes via Celery Beat; finds tournaments starting in ~1h.
    """
    now = timezone.now()
    window_start = now + timedelta(minutes=45)
    window_end = now + timedelta(minutes=75)

    tournaments = Tournament.objects.filter(
        tournament_start__gte=window_start,
        tournament_start__lte=window_end,
        status="upcoming",
    )

    reminders_sent = 0
    frontend_url = settings.CORS_ALLOWED_ORIGINS[0]

    for tournament in tournaments:
        try:
            tournament_url = f"{frontend_url}/tournaments/{tournament.id}"
            registrations = TournamentRegistration.objects.filter(tournament=tournament, status="confirmed")
            event_type = "Scrim" if tournament.event_mode == "SCRIM" else "Tournament"
            start_time = tournament.tournament_start.strftime("%B %d, %Y at %I:%M %p")

            for reg in registrations:
                try:
                    player = reg.player
                    send_player_tournament_reminder_email(
                        user_email=player.user.email,
                        user_name=player.user.username,
                        tournament_name=tournament.title,
                        game_name=tournament.game_name,
                        start_time=start_time,
                        time_until="1 hour",
                        tournament_url=tournament_url,
                        event_type=event_type,
                        team_name=reg.team_name,
                    )
                    reminders_sent += 1
                except Exception as e:
                    logger.error(f"Failed to send 1h player reminder for reg {reg.id}: {e}")

        except Exception as e:
            logger.error(f"Error sending 1h reminders for tournament {tournament.id}: {e}")

    logger.info(f"Sent {reminders_sent} 1h reminder emails")

    # Notify each host that their tournament starts in ~1h (send once per tournament)
    host_notif_count = 0
    for tournament in tournaments:
        cache_key = f"host_start_notif_1h:{tournament.id}"
        try:
            from django.core.cache import cache as django_cache
            if not django_cache.get(cache_key) and hasattr(tournament, 'host') and tournament.host:
                Notification.objects.get_or_create(
                    user=tournament.host.user,
                    type='tournament_start_reminder',
                    related_id=tournament.id,
                    related_type='tournament',
                    defaults={
                        'title': 'Tournament Starting in 1 Hour',
                        'message': f'Your tournament "{tournament.title}" starts at {tournament.tournament_start.strftime("%I:%M %p")}. Make sure everything is set up.',
                        'is_read': False,
                    },
                )
                django_cache.set(cache_key, True, 7200)
                host_notif_count += 1
        except Exception as e:
            logger.warning(f"Failed to send host start reminder for tournament {tournament.id}: {e}")

    if host_notif_count:
        logger.info(f"Sent {host_notif_count} host tournament start notifications")

    return {"reminders_sent": reminders_sent}


# ============================================================================
# PLAYER-SIDE TOURNAMENT EMAIL TASK WRAPPERS
# ============================================================================


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


# ============================================================================
# HOST-SIDE TOURNAMENT EMAIL TASK WRAPPERS
# ============================================================================


@shared_task(name="send_host_approved_email_task")
def send_host_approved_email_task(
    user_email: str, user_name: str, host_name: str, approved_at: str, host_dashboard_url: str
):
    """Async task to send host account approval email"""
    return send_host_approved_email(user_email, user_name, host_name, approved_at, host_dashboard_url)


@shared_task(name="send_host_rejected_email_task")
def send_host_rejected_email_task(
    user_email: str, user_name: str, host_name: str, rejection_reason: str, login_url: str
):
    """Async task to send host account rejection email with reason"""
    return send_host_rejected_email(user_email, user_name, host_name, rejection_reason, login_url)


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
